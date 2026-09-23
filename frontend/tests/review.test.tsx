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

function mockReviewApi(onReview?: (request: Record<string, unknown>) => void) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = requestPath(input);
    if (path === '/v1/cases/ready') return jsonResponse(readyCase);
    if (path === '/v1/cases') return jsonResponse([readyCase]);
    if (path === '/v1/cases/ready/review') {
      expect(init?.method).toBe('POST');
      const request = JSON.parse(String(init?.body)) as Record<string, unknown>;
      onReview?.(request);
      return jsonResponse({
        ...readyCase,
        revision: 1,
        state: request.action === 'ESCALATE' ? 'ESCALATED' : 'REVIEWED',
        clinician_review: {
          reviewer: 'Review clinician',
          final_grade: request.action === 'ESCALATE' ? null : 2,
          review_action: request.action,
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

describe('Review responsibility boundary', () => {
  it('keeps eligible analysis available while showing compact read-only context and downstream actions', async () => {
    const user = userEvent.setup();
    let reviewRequest: Record<string, unknown> | undefined;
    mockReviewApi((request) => { reviewRequest = request; });
    renderAppAt('/review/ready');

    expect(await screen.findByText('IMG13 · Left')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeEnabled();
    expect(screen.queryByLabelText('Pseudonymous patient key')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Image admission' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Accept as retinal fundus image/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edit annotations' })).toHaveAttribute('href', '/edit/ready');
    expect(screen.getByRole('link', { name: 'Continue to clinician review' })).toHaveAttribute('href', '/clinician-review/ready');

    await user.click(screen.getByRole('link', { name: 'Continue to clinician review' }));
    expect(await screen.findByRole('heading', { name: 'Clinician decision' })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('Reviewer name'), 'Review clinician');
    await user.selectOptions(screen.getByLabelText('Final DR grade'), '2');
    expect(screen.getByRole('radio', { name: 'Confirm final DR grade' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Send for senior review' })).not.toBeChecked();
    expect(screen.queryByRole('button', { name: 'Escalate' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirm final DR grade' }));
    expect(reviewRequest).toMatchObject({ action: 'ACCEPT', grade: null, reviewer: 'Review clinician' });
    expect(await screen.findByRole('button', { name: 'Scan input folder' })).toBeInTheDocument();
  });

  it('sends a mutually exclusive senior-review decision without recording a final grade', async () => {
    const user = userEvent.setup();
    let reviewRequest: Record<string, unknown> | undefined;
    mockReviewApi((request) => { reviewRequest = request; });
    renderAppAt('/clinician-review/ready');

    expect(await screen.findByRole('heading', { name: 'Clinician decision' })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('Reviewer name'), 'Review clinician');
    await user.click(screen.getByRole('radio', { name: 'Send for senior review' }));
    expect(screen.getByRole('radio', { name: 'Send for senior review' })).toBeChecked();
    expect(screen.queryByLabelText('Final DR grade')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Send for senior review' }));

    expect(reviewRequest).toMatchObject({ action: 'ESCALATE', grade: null, reviewer: 'Review clinician' });
    expect(await screen.findByRole('button', { name: 'Scan input folder' })).toBeInTheDocument();
  });
});
