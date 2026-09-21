import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorklistPage } from '@/pages/WorklistPage';
import type { CaseRecord } from '@/lib/api';
import { renderAppAt, withProviders } from './testUtils';

const admissionCase = {
  image_id: 'ambiguous',
  display_name: 'ambiguous',
  filename: 'ambiguous.png',
  source_type: 'PUBLIC',
  source: 'WORKSPACE_INPUT',
  modality: 'CFP',
  width: 400,
  height: 300,
  image_url: '/v1/images/ambiguous',
  state: 'PENDING',
  revision: 0,
  global: null,
  lesion: null,
  lesion_review: null,
  human_annotations: [],
  clinician_review: null,
  admission: {
    image_id: 'ambiguous',
    source_reference: 'WORKSPACE_INPUT/ambiguous.png',
    filename: 'ambiguous.png',
    file_extension: '.png',
    file_size_bytes: 1200,
    width: 400,
    height: 300,
    channels_or_mode: 'RGB',
    modality_admission: 'NEEDS_REVIEW',
    quality_state: 'NOT_EVALUATED',
    admission_method: 'AUTOMATIC',
    admission_reason_code: 'FUNDUS_UNCERTAIN',
    quality_reason_code: null,
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-01T00:00:00+00:00',
    reviewed_by: null,
    reviewed_at: null,
    review_note: null,
  },
  admission_ui: {
    label: 'Needs review',
    note: 'Please confirm this image before analysis.',
    tone: 'warning',
    action_required: true,
  },
  admission_history: [],
} as CaseRecord;

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestPath(input: RequestInfo | URL) {
  if (typeof input === 'string') return new URL(input, window.location.origin).pathname;
  if (input instanceof URL) return input.pathname;
  return new URL(input.url, window.location.origin).pathname;
}

function mockAdmissionApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = requestPath(input);
    if (path === '/v1/cases') return jsonResponse([admissionCase]);
    if (path === '/v1/cases/ambiguous') return jsonResponse(admissionCase);
    if (path === '/v1/models') return jsonResponse([]);
    if (path === '/v1/admissions/scan') {
      return jsonResponse({ records: [admissionCase.admission], warnings: [], scanned: true });
    }
    return jsonResponse({ detail: `Unexpected test request: ${path}` }, 404);
  });
}

describe('image admission UI', () => {
  it('shows plain-language admission status and scans the input folder', async () => {
    mockAdmissionApi();
    const user = userEvent.setup();
    withProviders(<WorklistPage />, '/worklist');

    expect(await screen.findByText('Needs review')).toBeInTheDocument();
    expect(screen.getByText('Please confirm this image before analysis.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Scan input folder/i }));
    expect(await screen.findByText('Scanned 1 input files.')).toBeInTheDocument();
  });

  it('keeps blocked analysis guarded and routes admission work to the Worklist', async () => {
    mockAdmissionApi();
    renderAppAt('/review/ambiguous');

    expect(await screen.findByText('Needs image review')).toBeInTheDocument();
    expect(screen.getByText('ambiguous · Eye not confirmed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeDisabled();
    expect(screen.getByText('Resolve this case from the Worklist before analysis.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Worklist' })).toHaveAttribute('href', '/worklist');
    expect(screen.queryByRole('button', { name: /Accept as retinal fundus image/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Mark as non-fundus/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Pseudonymous patient key')).not.toBeInTheDocument();
  });

  it('disables analysis when the remote endpoint is not configured', async () => {
    const readyCase: CaseRecord = {
      ...admissionCase,
      admission: {
        ...admissionCase.admission!,
        modality_admission: 'FUNDUS_ACCEPTED',
        quality_state: 'NOT_EVALUATED',
      },
      admission_ui: {
        ...admissionCase.admission_ui!,
        label: 'Ready for analysis',
        note: 'This image can be analyzed.',
        tone: 'success',
        action_required: false,
      },
    };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = requestPath(input);
      if (path === '/v1/cases/ambiguous') return jsonResponse(readyCase);
      if (path === '/v1/models') {
        return jsonResponse([
          { model_id: 'retfound-aptos5', task: 'global', runtime: 'remote', status: 'REMOTE_NOT_CONFIGURED' },
          { model_id: 'prism-dr-5fold', task: 'lesion-roi', runtime: 'remote', status: 'REMOTE_NOT_CONFIGURED' },
        ]);
      }
      return jsonResponse({ detail: `Unexpected test request: ${path}` }, 404);
    });

    renderAppAt('/review/ambiguous');

    expect(await screen.findByRole('button', { name: 'Analyze' })).toBeDisabled();
    expect(screen.getByText('AI analysis is not available.')).toBeInTheDocument();
  });
});
