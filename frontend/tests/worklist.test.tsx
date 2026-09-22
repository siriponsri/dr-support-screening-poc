import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorklistPage } from '@/pages/WorklistPage';
import type { CaseRecord } from '@/lib/api';
import { withProviders } from './testUtils';

const baseCase: CaseRecord = {
  image_id: 'internal-case-001',
  display_name: 'fundus_with_a_very_long_filename_that_must_not_expand_the_table.jpg',
  filename: 'fundus_with_a_very_long_filename_that_must_not_expand_the_table.jpg',
  source_type: 'PUBLIC', source: 'WORKSPACE_INPUT', modality: 'CFP', width: 400, height: 300,
  image_url: '/v1/images/internal-case-001', state: 'PENDING', revision: 2, global: null, lesion: null,
  lesion_review: null, human_annotations: [], clinician_review: null, admission: null,
  admission_ui: { label: 'Ready for analysis', note: 'This image can be analyzed.', tone: 'success', action_required: false },
  patient_key: null, patient_candidate: null, laterality: 'UNKNOWN',
  resolver_ui: {
    label: 'Patient information needs review', note: 'Confirm patient and eye.', tone: 'warning', action_required: true,
    patient: { label: 'Patient not linked', note: 'Link patient.', tone: 'warning', action_required: true, candidate: null },
    laterality: { label: 'Eye not confirmed', note: 'Confirm eye.', tone: 'warning', action_required: true, value: 'UNKNOWN' },
  },
  queue_state: 'INCLUDED', queue_history: [],
};

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('PRE-S3 Worklist', () => {
  it('keeps the primary queue to five columns and hides internal ids', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/cases') return response([baseCase]);
      if (path === '/v1/cases/internal-case-001/queue') return response(baseCase, 200);
      return response({ detail: `Unexpected request ${init?.method ?? 'GET'} ${path}` }, 404);
    });
    withProviders(<WorklistPage />, '/worklist');

    expect(await screen.findByText(baseCase.display_name)).toHaveAttribute('title', baseCase.display_name);
    expect(screen.getAllByRole('columnheader')).toHaveLength(5);
    expect(screen.getByRole('columnheader', { name: 'Action' })).toBeInTheDocument();
    expect(screen.queryByText(baseCase.image_id)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Link patient and confirm eye' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit patient and eye assignment' })).not.toBeInTheDocument();
  });

  it('opens the resolver dialog and sends the frozen resolver request', async () => {
    const user = userEvent.setup();
    let resolverBody: unknown;
    const saved = { ...baseCase, revision: 3, patient_key: 'PAT0001', laterality: 'LEFT' as const };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/cases') return response([baseCase]);
      if (path.endsWith('/resolver')) {
        resolverBody = JSON.parse(String(init?.body));
        return response(saved);
      }
      return response({ detail: `Unexpected request ${path}` }, 404);
    });
    withProviders(<WorklistPage />, '/worklist');

    await user.click(await screen.findByRole('button', { name: 'Link patient and confirm eye' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Resolve patient and eye');
    await user.clear(screen.getByLabelText('Pseudonymous patient key'));
    await user.type(screen.getByLabelText('Pseudonymous patient key'), 'PAT0001');
    await user.selectOptions(screen.getByLabelText('Eye'), 'LEFT');
    await user.type(screen.getByRole('textbox', { name: 'Reviewer name' }), 'Clinician');
    await user.click(screen.getByRole('button', { name: 'Save patient / eye' }));

    expect(resolverBody).toMatchObject({ revision: 2, patient_action: 'SET', patient_key: 'PAT0001', laterality_action: 'SET', laterality: 'LEFT' });
  });

  it('keeps automatic assignments editable, preloads current values, and preserves manual correction through the resolver API', async () => {
    const user = userEvent.setup();
    const automatic = {
      ...baseCase,
      patient_key: 'PAT0001',
      patient_resolution_state: 'RESOLVED' as const,
      patient_resolution_method: 'FILENAME',
      laterality: 'LEFT' as const,
      laterality_resolution_state: 'RESOLVED' as const,
      laterality_resolution_method: 'FILENAME',
      resolver_state: 'RESOLVED' as const,
      resolver_ui: {
        ...baseCase.resolver_ui!,
        label: 'Patient matched',
        note: 'Patient information was matched for this image.',
        tone: 'success' as const,
        action_required: false,
        patient: { ...baseCase.resolver_ui!.patient, label: 'Patient matched', action_required: false, patient_key: 'PAT0001' },
        laterality: { ...baseCase.resolver_ui!.laterality, label: 'Left eye', action_required: false, value: 'LEFT' as const },
      },
    };
    const corrected = {
      ...automatic,
      revision: 3,
      patient_key: 'PAT0002',
      patient_resolution_method: 'MANUAL',
      laterality: 'RIGHT' as const,
      laterality_resolution_method: 'MANUAL',
      resolution_history: [{ action: 'MANUAL_RESOLUTION', reviewer: 'Clinician', previous: { patient_key: 'PAT0001', laterality: 'LEFT' }, new: { patient_key: 'PAT0002', laterality: 'RIGHT' } }],
      resolver_ui: {
        ...automatic.resolver_ui,
        patient: { ...automatic.resolver_ui.patient, label: 'Patient matched', patient_key: 'PAT0002' },
        laterality: { ...automatic.resolver_ui.laterality, label: 'Right eye', value: 'RIGHT' as const },
      },
    };
    let resolverBody: Record<string, unknown> | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/cases') return response([automatic]);
      if (path.endsWith('/resolver')) {
        resolverBody = JSON.parse(String(init?.body));
        return response(corrected);
      }
      return response({ detail: `Unexpected request ${path}` }, 404);
    });
    withProviders(<WorklistPage />, '/worklist');

    const row = await screen.findByTestId(`case-row-${automatic.display_name}`);
    expect(within(row).getByText('PAT0001 · Left')).toBeInTheDocument();
    expect(within(row).getByText('Auto-linked')).toBeInTheDocument();
    await user.click(within(row).getByRole('button', { name: 'Edit patient and eye assignment' }));
    expect(screen.getByLabelText('Pseudonymous patient key')).toHaveValue('PAT0001');
    expect(screen.getByLabelText('Eye')).toHaveValue('LEFT');

    await user.clear(screen.getByLabelText('Pseudonymous patient key'));
    await user.type(screen.getByLabelText('Pseudonymous patient key'), 'PAT0002');
    await user.selectOptions(screen.getByLabelText('Eye'), 'RIGHT');
    await user.type(screen.getByRole('textbox', { name: 'Reviewer name' }), 'Clinician');
    await user.click(screen.getByRole('button', { name: 'Save patient / eye' }));

    expect(resolverBody).toMatchObject({ revision: 2, patient_action: 'SET', patient_key: 'PAT0002', laterality_action: 'SET', laterality: 'RIGHT' });
    expect(within(await screen.findByTestId(`case-row-${automatic.display_name}`)).getByText('PAT0002 · Right')).toBeInTheDocument();
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
    expect(corrected.resolution_history?.[0]).toMatchObject({ action: 'MANUAL_RESOLUTION' });
  });

  it('offers reversible exclusion through the action menu', async () => {
    const user = userEvent.setup();
    const excluded = { ...baseCase, revision: 3, queue_state: 'EXCLUDED' as const };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/cases') return response([baseCase]);
      if (path.endsWith('/queue')) {
        expect(JSON.parse(String(init?.body))).toMatchObject({ revision: 2, action: 'EXCLUDE' });
        return response(excluded);
      }
      return response({ detail: `Unexpected request ${path}` }, 404);
    });
    withProviders(<WorklistPage />, '/worklist');

    const row = await screen.findByTestId(`case-row-${baseCase.display_name}`);
    await user.click(within(row).getByRole('button', { name: /More actions/i }));
    await user.click(await screen.findByRole('menuitem', { name: 'Exclude from queue' }));
    expect(within(row).getByRole('link', { name: 'Excluded' })).toHaveAttribute('disabled');
    expect(within(row).getByTitle('Restore to queue')).toBeInTheDocument();
  });
});
