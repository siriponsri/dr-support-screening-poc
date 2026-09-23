import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ReviewerPreference } from '@/components/settings/ReviewerPreference';
import { ClinicianReviewPage } from '@/pages/ClinicianReviewPage';
import type { CaseRecord } from '@/lib/api';
import { theme } from '@/theme';
import { withProviders } from './testUtils';

const item: CaseRecord = {
  image_id: 'CASE-002', display_name: 'Case 002', filename: 'case-002.jpg', source_type: 'SYNTHETIC', source: 'fixture', modality: 'CFP', width: 640, height: 480,
  image_url: null, state: 'PENDING', revision: 1, global: null, lesion: null, lesion_review: null, human_annotations: [], clinician_review: null,
  admission: null, admission_ui: null,
};

function response(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('default reviewer preference', () => {
  beforeEach(() => window.localStorage.clear());

  it('persists an editable default and permits clearing it', async () => {
    const user = userEvent.setup();
    withProviders(<ReviewerPreference />, '/settings');
    const input = screen.getByLabelText('Default reviewer');
    await user.type(input, 'Shared workstation clinician');
    expect(window.localStorage.getItem('dr-support-screening.default-reviewer.v1')).toBe('Shared workstation clinician');
    await user.clear(input);
    expect(window.localStorage.getItem('dr-support-screening.default-reviewer.v1')).toBeNull();
  });

  it('prefills a new review and keeps historical review records read-only', async () => {
    window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'New reviewer');
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/workspaces') return response({ workspaces: [], active_workspace_id: null, active_workspace: null, warnings: [] });
      if (path === '/v1/workspaces/active') return response({ workspace: null, database: { path: '', status: 'unavailable' }, warnings: [] });
      if (path === '/health') return response({ status: 'ok' });
      return response(item);
    });
    render(
      <ChakraProvider theme={theme}>
        <MemoryRouter initialEntries={['/clinician-review/CASE-002']}>
          <Routes><Route path="/clinician-review/:imageId" element={<ClinicianReviewPage />} /></Routes>
        </MemoryRouter>
      </ChakraProvider>,
    );
    expect(await screen.findByPlaceholderText('Reviewer name')).toHaveValue('New reviewer');
    expect(fetchSpy).toHaveBeenCalled();

    cleanup();
    window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'Later reviewer');
    const historical = { ...item, clinician_review: { reviewer: 'Recorded reviewer', final_grade: 2, review_action: 'ACCEPT' as const, remark: '', timestamp: '2026-01-01T00:00:00Z', revision: 2 } };
    vi.restoreAllMocks();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/workspaces') return response({ workspaces: [], active_workspace_id: null, active_workspace: null, warnings: [] });
      if (path === '/v1/workspaces/active') return response({ workspace: null, database: { path: '', status: 'unavailable' }, warnings: [] });
      if (path === '/health') return response({ status: 'ok' });
      return response(historical);
    });
    render(
      <ChakraProvider theme={theme}>
        <MemoryRouter initialEntries={['/clinician-review/CASE-002']}>
          <Routes><Route path="/clinician-review/:imageId" element={<ClinicianReviewPage />} /></Routes>
        </MemoryRouter>
      </ChakraProvider>,
    );
    expect(await screen.findByRole('heading', { name: 'DR grade confirmed' })).toBeInTheDocument();
    expect(screen.getByText(/Recorded reviewer/, { selector: 'p' })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Reviewer name')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit confirmed grade' })).toBeInTheDocument();
  });
});
