import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthGate } from '@/components/shell/AuthGate';
import { AdminPage } from '@/pages/AdminPage';

const users = [{ username: 'admin', role: 'admin', disabled: false, must_change: false },
  { username: 'doctor1', role: 'physician', disabled: false, must_change: true }];

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

  it('offers the five roles in plain words', async () => {
    serve('admin');
    mount();
    const role = await screen.findByLabelText('Role');
    const options = Array.from((role as HTMLSelectElement).options).map((option) => option.textContent);
    expect(options).toEqual(['Physician', 'Nurse', 'Ophthalmologist (expert)', 'Researcher', 'Administrator']);
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

describe('sign-in policy panel', () => {
  it('shows the rules in plain words and saves a change', async () => {
    const calls: Array<{ path: string; body?: string }> = [];
    let policy = { min_length: 8, letters_and_numbers: true, first_sign_in_change: true, max_failures: 5, lockout_minutes: 5, idle_minutes: 30 };
    const bounds = { min_length: [6, 64], max_failures: [3, 10], lockout_minutes: [1, 60], idle_minutes: [5, 480] };
    vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
      calls.push({ path: input, body: init?.body as string | undefined });
      if (input === '/v1/auth/me') return { ok: true, status: 200, headers: new Headers(), json: async () => ({ username: 'admin', role: 'admin', must_change: false, short_password: false }) };
      if (input === '/v1/admin/users') return { ok: true, status: 200, headers: new Headers(), json: async () => ({ users }) };
      if (input === '/v1/admin/policy') {
        if (init?.method === 'POST') policy = JSON.parse(String(init.body));
        return { ok: true, status: 200, headers: new Headers(), json: async () => ({ policy, bounds }) };
      }
      return { ok: false, status: 404, headers: new Headers(), json: async () => ({ detail: 'Not Found' }) };
    }));
    mount();
    const length = await screen.findByLabelText('Minimum password length');
    expect(screen.getByText('Sign out when idle for')).toBeInTheDocument();
    fireEvent.change(length, { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }));
    expect(await screen.findByText('Saved')).toBeInTheDocument();
    expect(JSON.parse(calls.find((call) => call.path === '/v1/admin/policy' && call.body)!.body!).min_length).toBe(10);
  });
});
