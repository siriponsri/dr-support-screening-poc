import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { CaseRecord } from '@/lib/api';
import { renderAppAt } from './testUtils';

function makeCase(overrides: Partial<CaseRecord> = {}): CaseRecord {
  return {
    image_id: 'case-1', display_name: 'image_01', filename: 'image_01.jpg', source_type: 'PUBLIC', source: 'WORKSPACE_INPUT', modality: 'CFP', width: 640, height: 480,
    image_url: null, state: 'PENDING', revision: 0, global: null, lesion: null, lesion_review: null, human_annotations: [], clinician_review: null, admission: null,
    admission_ui: { label: 'Ready for analysis', note: 'Ready.', tone: 'success', action_required: false }, patient_key: null, laterality: 'UNKNOWN', queue_state: 'INCLUDED',
    resolver_ui: { label: 'Patient information needs review', note: 'Confirm patient and eye.', tone: 'warning', action_required: true, patient: { label: 'Patient not linked', note: 'Link patient.', tone: 'warning', action_required: true }, laterality: { label: 'Eye not confirmed', note: 'Confirm eye.', tone: 'warning', action_required: true, value: 'UNKNOWN' } },
    ...overrides,
  };
}

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('S3 Worklist views and actions', () => {
  it('switches to Patients without duplicating cases and keeps five columns', async () => {
    const user = userEvent.setup();
    const cases = [
      makeCase({ image_id: 'left', display_name: 'left', filename: 'left.jpg', patient_key: 'PAT0001', laterality: 'LEFT', resolver_ui: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false, patient: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false }, laterality: { label: 'Left eye', note: 'Left.', tone: 'success', action_required: false, value: 'LEFT' } } }),
      makeCase({ image_id: 'right', display_name: 'right', filename: 'right.jpg', patient_key: 'PAT0001', laterality: 'RIGHT', resolver_ui: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false, patient: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false }, laterality: { label: 'Right eye', note: 'Right.', tone: 'success', action_required: false, value: 'RIGHT' } } }),
      makeCase({ image_id: 'unknown', display_name: 'unknown', filename: 'unknown.jpg', patient_key: 'PAT0001', laterality: 'UNKNOWN' }),
      makeCase({ image_id: 'unlinked', display_name: 'unlinked', filename: 'unlinked.jpg' }),
    ];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      return path === '/v1/cases' ? response(cases) : response({ detail: 'Unexpected request' }, 404);
    });

    renderAppAt('/worklist');
    await user.click(await screen.findByRole('button', { name: 'Patients' }));

    expect(screen.getByTestId('patient-group-PAT0001')).toHaveTextContent('PAT0001');
    expect(screen.getByTestId('patient-group-unlinked')).toHaveTextContent('Patient not linked');
    expect(screen.getAllByTestId(/^case-row-/)).toHaveLength(4);
    expect(screen.getAllByRole('columnheader')).toHaveLength(5);
    expect(screen.getAllByText('Eye not confirmed').length).toBeGreaterThan(0);
  });

  it('searches by filename and opens the focused readiness action', async () => {
    const user = userEvent.setup();
    const item = makeCase({
      image_id: 'needs-review', display_name: 'quality-check', filename: 'quality-check.jpg', revision: 4,
      admission: { image_id: 'needs-review', source_reference: 'WORKSPACE_INPUT/quality-check.jpg', filename: 'quality-check.jpg', file_extension: '.jpg', file_size_bytes: 10, width: 640, height: 480, channels_or_mode: 'RGB', modality_admission: 'NEEDS_REVIEW', quality_state: 'NOT_EVALUATED', admission_method: 'AUTOMATIC', admission_reason_code: 'FUNDUS_UNCERTAIN', quality_reason_code: null, created_at: '2026-01-01', updated_at: '2026-01-01', reviewed_by: null, reviewed_at: null, review_note: null },
      admission_ui: { label: 'Needs review', note: 'Please confirm this image before analysis.', tone: 'warning', action_required: true },
    });
    const saved = { ...item, revision: 5, admission_ui: { label: 'Ready for analysis', note: 'Ready.', tone: 'success' as const, action_required: false } };
    let requestBody: Record<string, unknown> | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/cases') return response([item]);
      if (path.endsWith('/admission')) { requestBody = JSON.parse(String(init?.body)); return response(saved); }
      return response({ detail: 'Unexpected request' }, 404);
    });

    renderAppAt('/worklist');
    const search = await screen.findByRole('textbox', { name: 'Search worklist' });
    await user.type(search, 'quality-check');
    expect(screen.getByTestId('case-row-quality-check')).toBeInTheDocument();
    await user.click(within(screen.getByTestId('case-row-quality-check')).getByRole('button', { name: /More actions/i }));
    await user.click(await screen.findByRole('menuitem', { name: 'Resolve image readiness' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Resolve image readiness');
    await user.type(screen.getByPlaceholderText('Reviewer name'), 'Clinician');
    await user.click(screen.getByRole('button', { name: 'Accept as retinal image' }));

    expect(requestBody).toMatchObject({ revision: 4, reviewer: 'Clinician', action: 'ACCEPT_RETINAL' });
    expect(screen.queryByText('Needs review')).not.toBeInTheDocument();
  });
});
