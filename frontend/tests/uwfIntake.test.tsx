import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderAppAt } from './testUtils';
import type { CaseRecord, RetinalModality } from '@/lib/api';

function sample(modality: RetinalModality = 'UNKNOWN'): CaseRecord {
  return {
    image_id: 'synthetic-uwf', display_name: 'synthetic-uwf', filename: 'synthetic-uwf.png',
    source_type: 'PUBLIC', source: 'WORKSPACE_INPUT', modality,
    width: 512, height: 384, image_url: '/v1/images/synthetic-uwf/display',
    state: 'PENDING', revision: 1, global: null, lesion: null, lesion_review: null,
    human_annotations: [], clinician_review: null, patient_key: 'PAT001', laterality: 'LEFT',
    admission: {
      image_id: 'synthetic-uwf', source_reference: 'WORKSPACE_INPUT/synthetic-uwf.png',
      filename: 'synthetic-uwf.png', file_extension: '.png', file_size_bytes: 1200,
      width: 512, height: 384, channels_or_mode: 'RGB', modality_admission: 'FUNDUS_ACCEPTED',
      quality_state: 'NOT_EVALUATED', retinal_modality: modality,
      retinal_modality_state: modality === 'UNKNOWN' ? 'NEEDS_CONFIRMATION' : 'RESOLVED',
      retinal_modality_method: 'NONE', admission_method: 'AUTOMATIC',
      admission_reason_code: 'FUNDUS_PLAUSIBLE', quality_reason_code: null,
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      reviewed_by: null, reviewed_at: null, review_note: null,
    },
    admission_ui: { label: 'Image type needs confirmation', note: 'Confirm the image type.', tone: 'warning', action_required: true },
    admission_history: [],
  };
}

function reply(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function workspaceReply(path: string) {
  if (path === '/v1/workspaces') return reply({ workspaces: [], active_workspace_id: null, active_workspace: null, warnings: [] });
  if (path === '/v1/workspaces/active') return reply({ workspace: null, database: { path: '', status: 'fallback' }, warnings: [] });
  return null;
}

describe('UWF intake and clinical review', () => {
  it('shows unknown in Worklist and sends the clinician-selected image type at confirmation', async () => {
    const original = sample();
    const sent: Record<string, unknown>[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      const workspace = workspaceReply(path);
      if (workspace) return workspace;
      if (path === '/v1/cases') return reply([original]);
      if (path.endsWith('/confirm-image')) {
        sent.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return reply({ ...original, modality: 'UWF', admission: { ...original.admission, retinal_modality: 'UWF' },
          admission_history: [{ action: 'CONFIRM_IMAGE' }] });
      }
      if (path === '/v1/models') return reply([]);
      if (path === '/v1/cases/synthetic-uwf') return reply(original);
      return reply([]);
    });
    renderAppAt('/worklist');
    const row = await screen.findByTestId('case-row-synthetic-uwf');
    expect(within(row).getByText('Image type needs confirmation')).toBeInTheDocument();
    await userEvent.setup().click(within(row).getByRole('button', { name: 'Confirm Image' }));
    const type = await screen.findByLabelText('Image type');
    expect(type).toHaveValue('UNKNOWN');
    await userEvent.setup().selectOptions(type, 'UWF');
    await userEvent.setup().type(screen.getByPlaceholderText('Reviewer name'), 'Synthetic Reviewer');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Confirm image & continue' }));
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ retinal_modality: 'UWF', reviewer: expect.any(String) });
  });

  it('shows the prepared same-canvas analysis area while keeping UWF AI unavailable', async () => {
    const uwf = {
      ...sample('UWF'),
      admission_history: [{ action: 'CONFIRM_IMAGE' }],
      analysis_preparation: { status: 'READY' as const },
    };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      const workspace = workspaceReply(path);
      if (workspace) return workspace;
      if (path === '/v1/cases/synthetic-uwf') return reply(uwf);
      if (path === '/v1/cases') return reply([uwf]);
      if (path === '/v1/models') return reply([{ model_id: 'retfound-aptos5', task: 'global', modalities: ['CFP'], status: 'LOADED' }]);
      return reply([]);
    });
    renderAppAt('/review/synthetic-uwf');
    expect(await screen.findByText('Analysis area prepared')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeDisabled();
    expect(screen.getByText('AI evidence unavailable for this image type. Clinical review can continue.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Continue to clinician review' })).toHaveAttribute('href', '/clinician-review/synthetic-uwf');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Analysis area' }));
    expect(screen.getByRole('button', { name: 'Analysis area' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('img', { name: /retinal/i })).toHaveAttribute('src', '/v1/images/synthetic-uwf/analysis-area');
  });
});
