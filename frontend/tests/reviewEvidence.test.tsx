import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReviewEvidencePanel } from '@/components/review/ReviewEvidencePanel';
import type { CaseRecord } from '@/lib/api';
import { withProviders } from './testUtils';

const item: CaseRecord = {
  image_id: 'CASE-001',
  display_name: 'Case 001',
  filename: 'case-001.jpg',
  source_type: 'SYNTHETIC',
  source: 'fixture',
  modality: 'CFP',
  width: 800,
  height: 600,
  image_url: '/case-001.jpg',
  state: 'PENDING',
  revision: 2,
  global: null,
  lesion: {
    model_id: 'prism-dr-5fold',
    model_version: 'fixture',
    modality: 'CFP',
    state: 'AI_SUGGESTION',
    width: 800,
    height: 600,
    lesions: [{ source_label: 'MA', canonical_label: 'MICROANEURYSM', rectangle: [10, 20, 30, 40], score: 0.82, state: 'AI_SUGGESTION' }],
    warnings: [],
  },
  lesion_review: {
    raw_count: 1,
    suggestion_count: 1,
    filtered_count: 0,
    lesions: [{ detection_id: 'ai-aaaaaaaaaaaaaaaaaaaa', source_label: 'MA', canonical_label: 'MICROANEURYSM', rectangle: [10, 20, 30, 40], score: 0.82, state: 'AI_SUGGESTION' }],
    policy: { thresholds: {}, max_per_class: 25, max_total: 80 },
  },
  review_evidence: {
    status: 'Pending review',
    reviewer: null,
    timestamp: null,
    summary: { confirmed: 0, added: 0, removed: 0, corrected: 0 },
    unresolved_count: 1,
    items: [{
      annotation_id: 'ai-aaaaaaaaaaaaaaaaaaaa',
      source: 'AI',
      label: 'MICROANEURYSM',
      score: 0.82,
      original_score: 0.82,
      status: 'AI_SUGGESTED',
      model_id: 'prism-dr-5fold',
      model_version: 'fixture',
      reviewer: null,
      timestamp: null,
      original_label: 'MICROANEURYSM',
      original_rectangle: [10, 20, 30, 40],
      corrected_label: null,
      corrected_rectangle: null,
    }],
    model_id: 'prism-dr-5fold',
    model_version: 'fixture',
    source_sha256: 'a'.repeat(64),
    analysis_sha256: null,
    note: 'Counts describe review actions, not model accuracy or clinical outcomes.',
  },
  human_annotations: [],
  clinician_review: null,
};

describe('review evidence', () => {
  it('shows the numeric AI score and records a confirmation without changing the score', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    let requestBody: Record<string, unknown> | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      requestBody = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({
        ...item,
        revision: 3,
        review_evidence: {
          ...item.review_evidence,
          summary: { confirmed: 1, added: 0, removed: 0, corrected: 0 },
          unresolved_count: 0,
          items: [{ ...item.review_evidence!.items[0], status: 'CLINICIAN_CONFIRMED', reviewer: 'Clinician' }],
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    withProviders(<ReviewEvidencePanel item={item} onSaved={onSaved} />, '/review/CASE-001');

    expect(screen.getByText('MA · 0.82')).toBeInTheDocument();
    expect(screen.getByText('Microaneurysm · AI visual evidence')).toBeInTheDocument();
    expect(screen.queryByText(/unresolved/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /MA · 0\.82/ }));
    await user.type(screen.getByPlaceholderText('Enter reviewer name'), 'Clinician');
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    expect(requestBody).toMatchObject({
      revision: 2,
      reviewer: 'Clinician',
      detection_id: 'ai-aaaaaaaaaaaaaaaaaaaa',
      action: 'CONFIRM',
    });
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ revision: 3 }));
  });
});
