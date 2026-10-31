import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthGate } from '@/components/shell/AuthGate';
import { AdminPage } from '@/pages/AdminPage';

const users = [{ username: 'admin', role: 'admin', disabled: false, must_change: false },
  { username: 'doctor1', role: 'user', disabled: false, must_change: true }];

function serve(role: 'admin' | 'user') {
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? 'GET'} ${input}`);
    const body = input === '/v1/auth/me' ? { username: role === 'admin' ? 'admin' : 'doctor1', role, must_change: false, short_password: false }
      : input === '/v1/admin/users' ? { users }
        : input === '/v1/admin/db/summary' ? { storage: 'PostgreSQL', workspace: { id: 'ws', name: 'TEST_ONLY pilot' }, cases: 1,
          with_ai_grade: 1, with_prism: 0, grade_confirmed: 1, grade_corrected: 1, annotations: 2, batches: 1 }
          : input.startsWith('/v1/admin/db/cases?') ? { total: 1, rows: [{ image_id: 'abc123', revision: 4, modality: 'UWF',
            source_origin: 'PUBLIC', ai_grade: 2, prism_saved: false, clinician_grade: 3, grade_status: 'CONFIRMED',
            grade_source: 'AI_CORRECTED', lesion_review: null, annotations: 2, ai_runs: 1 }] }
            : input === '/v1/admin/db/cases/abc123' ? { image_id: 'abc123', record: { revision: 4, reviewed_grade: 3 } }
              : null;
    return { ok: body !== null, status: body !== null ? 200 : 404, headers: new Headers(), json: async () => body ?? { detail: 'Not Found' } };
  }));
  return calls;
}

function mount() {
  return render(<ChakraProvider><MemoryRouter initialEntries={['/admin']}><AuthGate><AdminPage /></AuthGate></MemoryRouter></ChakraProvider>);
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('admin page', () => {
  it('lists accounts with plain status words', async () => {
    serve('admin');
    mount();
    expect(await screen.findByText('doctor1')).toBeInTheDocument();
    expect(screen.getByText('Must set password')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Disable' })).toHaveLength(1);  // Never for yourself.
  });

  it('shows the read-only database view with AI and clinician grades apart', async () => {
    const calls = serve('admin');
    mount();
    fireEvent.click(await screen.findByRole('tab', { name: 'Database' }));
    expect(await screen.findByText('TEST_ONLY pilot')).toBeInTheDocument();
    expect(screen.getByText('Corrected')).toBeInTheDocument();
    fireEvent.click(screen.getByText('abc123'));
    expect(await screen.findByText(/"reviewed_grade": 3/)).toBeInTheDocument();
    expect(calls.filter((call) => call.startsWith('POST') && call.includes('/v1/admin/db'))).toEqual([]);
  });

  it('tells a physician the page is for administrators', async () => {
    serve('user');
    mount();
    await waitFor(() => expect(screen.getByText('Only an administrator can open this page.')).toBeInTheDocument());
    expect(screen.queryByRole('tab', { name: 'Users' })).toBeNull();
  });
});
