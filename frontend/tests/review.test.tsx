import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { CaseRecord } from '@/lib/api';
import { renderAppAt } from './testUtils';

const readyCase: CaseRecord = {
  image_id: 'ready',
  display_name: 'IMG13',
  filename: 'img13_L1.jpg',
  source_type: 'PUBLIC',
  source: 'WORKSPACE_INPUT',
  modality: 'CFP',
  width: 640,
  height: 480,
  image_url: null,
  state: 'PENDING',
  revision: 0,
  global: {
    model_id: 'retfound-aptos5',
    model_version: 'fixture',
    modality: 'CFP',
    state: 'AI_SUGGESTION',
    grade: 2,
    probabilities: [],
    confidence: 0.8,
    warnings: [],
  },
  lesion: {
    model_id: 'prism-dr-5fold',
    model_version: 'fixture',
    modality: 'CFP',
    state: 'AI_SUGGESTION',
    width: 640,
    height: 480,
    lesions: [{ detection_id: 'ai-aaaaaaaaaaaaaaaaaaaa', source_label: 'HE', canonical_label: 'HEMORRHAGE', rectangle: [10, 20, 30, 40], score: 0.9, state: 'AI_SUGGESTION' }],
    warnings: [],
  },
  lesion_review: {
    raw_count: 1,
    suggestion_count: 1,
    filtered_count: 0,
    lesions: [{ detection_id: 'ai-aaaaaaaaaaaaaaaaaaaa', source_label: 'HE', canonical_label: 'HEMORRHAGE', rectangle: [10, 20, 30, 40], score: 0.9, state: 'AI_SUGGESTION' }],
    policy: { thresholds: {}, max_per_class: 25, max_total: 80 },
  },
  human_annotations: [],
  clinician_review: null,
  admission: {
    image_id: 'ready',
    source_reference: 'WORKSPACE_INPUT/img13_L1.jpg',
    filename: 'img13_L1.jpg',
    file_extension: '.jpg',
    file_size_bytes: 1200,
    width: 640,
    height: 480,
    channels_or_mode: 'RGB',
    modality_admission: 'FUNDUS_ACCEPTED',
    quality_state: 'NOT_EVALUATED',
    admission_method: 'AUTOMATIC',
    admission_reason_code: 'FUNDUS_CONFIDENT',
    quality_reason_code: null,
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-01T00:00:00+00:00',
    reviewed_by: null,
    reviewed_at: null,
    review_note: null,
  },
  admission_ui: {
    label: 'Ready for analysis',
    note: 'This image can be analyzed.',
    tone: 'success',
    action_required: false,
  },
  patient_key: 'IMG13',
  laterality: 'LEFT',
  resolver_state: 'RESOLVED',
};

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

function mockReviewApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = requestPath(input);
    if (path === '/v1/cases/ready') return jsonResponse(readyCase);
    if (path === '/v1/cases/ready/review') {
      expect(init?.method).toBe('POST');
      return jsonResponse({
        ...readyCase,
        revision: 1,
        state: 'REVIEWED',
        clinician_review: {
          reviewer: 'Review clinician',
          final_grade: 2,
          review_action: 'ACCEPT',
          remark: '',
          timestamp: '2026-01-01T00:00:00+00:00',
          revision: 1,
        },
      });
    }
    if (path === '/v1/models') return jsonResponse([]);
    return jsonResponse({ detail: `Unexpected test request: ${path}` }, 404);
  });
}

describe('AI Review responsibility boundary', () => {
  it('keeps eligible analysis available while showing compact read-only context and downstream actions', async () => {
    const user = userEvent.setup();
    mockReviewApi();
    renderAppAt('/review/ready');

    expect(await screen.findByText('IMG13 · Left')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeEnabled();
    expect(screen.queryByLabelText('Pseudonymous patient key')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Image admission' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Accept as retinal fundus image/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edit annotations' })).toHaveAttribute('href', '/edit/ready');
    expect(screen.getByRole('link', { name: 'Clinician review' })).toHaveAttribute('href', '/clinician-review/ready');

    await user.click(screen.getByRole('link', { name: 'Clinician review' }));
    expect(await screen.findByRole('heading', { name: 'Clinician sign-off' })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('Enter reviewer name'), 'Review clinician');
    await user.click(screen.getByRole('button', { name: 'Accept AI grade' }));
    expect(await screen.findByText('AI grade accepted for IMG13.')).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: 'Back to AI Review' }));
    await user.click(await screen.findByRole('link', { name: 'Edit annotations' }));
    expect(await screen.findByRole('heading', { name: 'Editor tools' })).toBeInTheDocument();
  });
});
