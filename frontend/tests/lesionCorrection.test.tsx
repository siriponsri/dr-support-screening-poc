import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReviewPage } from '@/pages/ReviewPage';
import { LesionActionPopover } from '@/components/review/LesionActionPopover';
import { RetinalCanvas } from '@/components/review/RetinalCanvas';
import { displayedLesions } from '@/components/review/lesionPresentation';
import type { CaseRecord } from '@/lib/api';
import { renderAppAt, withProviders } from './testUtils';

const lesions = [
  { detection_id: 'ai-aaaaaaaaaaaaaaaaaaaa', source_label: 'HE', canonical_label: 'HEMORRHAGE' as const, rectangle: [10, 20, 30, 40] as [number, number, number, number], score: 0.9, state: 'AI_SUGGESTION' },
  { detection_id: 'ai-bbbbbbbbbbbbbbbbbbbb', source_label: 'MA', canonical_label: 'MICROANEURYSM' as const, rectangle: [50, 60, 80, 90] as [number, number, number, number], score: 0.82, state: 'AI_SUGGESTION' },
];

const item: CaseRecord = {
  image_id: 'CASE-001', display_name: 'Case 001', filename: 'case-001.jpg', source_type: 'SYNTHETIC', source: 'fixture', modality: 'CFP', width: 800, height: 600,
  image_url: null, state: 'PENDING', revision: 2, global: null,
  lesion: { model_id: 'prism-dr-5fold', model_version: 'revision', modality: 'CFP', state: 'AI_SUGGESTION', width: 800, height: 600, lesions, warnings: [] },
  lesion_review: { raw_count: 2, suggestion_count: 2, filtered_count: 0, lesions, policy: { thresholds: {}, max_per_class: 25, max_total: 80 } },
  review_evidence: {
    status: 'Pending review', reviewer: null, timestamp: null,
    summary: { confirmed: 0, added: 0, removed: 0, corrected: 0 }, unresolved_count: 2,
    items: lesions.map((lesion) => ({
      annotation_id: lesion.detection_id, source: 'AI' as const, label: lesion.canonical_label, score: lesion.score, original_score: lesion.score,
      status: 'AI_SUGGESTED' as const, model_id: 'prism-dr-5fold', model_version: 'revision', reviewer: null, timestamp: null,
      original_label: lesion.canonical_label, original_rectangle: lesion.rectangle, corrected_label: null, corrected_rectangle: null,
    })),
    model_id: 'prism-dr-5fold', model_version: 'revision', source_sha256: 'a'.repeat(64), analysis_sha256: null,
    note: 'Model evidence remains optional.',
  },
  human_annotations: [], clinician_review: null,
  admission: null, admission_ui: null,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('lightweight AI ROI correction', () => {
  beforeEach(() => window.localStorage.clear());

  it('renders an untouched AI ROI with its class and model score', () => {
    withProviders(
      <RetinalCanvas item={{ ...item, image_url: '/case-001.jpg' }} />,
      '/review/CASE-001',
    );

    expect(screen.getByText('HE · 0.90')).toBeInTheDocument();
  });

  it('keeps review image-first without the detailed evidence queue', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/cases/CASE-001') return jsonResponse(item);
      if (path === '/v1/models') return jsonResponse([]);
      return jsonResponse({ detail: 'Unexpected request' }, 404);
    });

    renderAppAt('/review/CASE-001');

    expect(await screen.findByText('AI lesion suggestions')).toBeInTheDocument();
    expect(screen.queryByText('PRISM evidence')).not.toBeInTheDocument();
    expect(screen.queryByText('Evidence status')).not.toBeInTheDocument();
    expect(screen.queryByText('Confirmed')).not.toBeInTheDocument();
    expect(screen.queryByText(/unresolved/i)).not.toBeInTheDocument();
  });

  it('creates a human correction copy while retaining the original AI evidence and score', async () => {
    const user = userEvent.setup();
    let requestBody: Record<string, unknown> | undefined;
    const humanAnnotation = {
      shape_id: 'human-derived-1',
      type: 'rectangle' as const,
      label: 'HEMORRHAGE' as const,
      geometry: { x: 10, y: 20, width: 20, height: 20 },
      locked: false,
      source_detection_id: lesions[0].detection_id,
      source: 'HUMAN' as const,
      reviewer: 'Clinician',
      created_at: '2026-01-01T00:00:00Z',
    };
    const corrected = {
      ...item,
      revision: 3,
      human_annotations: [humanAnnotation],
      review_evidence: {
        ...item.review_evidence!,
        items: [...item.review_evidence!.items, {
          annotation_id: humanAnnotation.shape_id,
          source: 'HUMAN' as const,
          label: humanAnnotation.label,
          score: null,
          original_score: null,
          status: 'CLINICIAN_ADDED' as const,
          model_id: null,
          model_version: null,
          reviewer: 'Clinician',
          timestamp: humanAnnotation.created_at,
          original_label: null,
          original_rectangle: null,
          corrected_label: null,
          corrected_rectangle: null,
          source_detection_id: lesions[0].detection_id,
        }],
      },
    };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      expect(new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname).toBe('/v1/cases/CASE-001/annotations/from-ai');
      requestBody = JSON.parse(String(init?.body));
      return jsonResponse(corrected);
    });
    const onDerived = vi.fn();

    withProviders(
      <LesionActionPopover item={item} selectedLesionId={lesions[0].detection_id} onSaved={vi.fn()} onDerived={onDerived} onClose={vi.fn()} />,
      '/review/CASE-001',
    );
    await user.click(screen.getByRole('button', { name: /Selected AI suggestion: HE/i }));
    expect(screen.getByRole('dialog')).toHaveTextContent(/Model score: 0\.90/);
    expect(screen.getByText(/not a clinical probability/)).toBeInTheDocument();
    await user.type(await screen.findByPlaceholderText('Reviewer name'), 'Clinician');
    await user.click(screen.getByRole('button', { name: 'Correct annotation' }));

    expect(requestBody).toMatchObject({
      revision: 2,
      detection_id: lesions[0].detection_id,
      intent: 'CORRECT_AS_HUMAN',
      reviewer: 'Clinician',
    });
    expect(onDerived).toHaveBeenCalledWith(corrected, humanAnnotation, 'CORRECT_AS_HUMAN');
    expect(corrected.lesion.lesions[0]).toMatchObject({ canonical_label: 'HEMORRHAGE', score: 0.9 });
    expect(corrected.human_annotations[0]).toMatchObject({ source_detection_id: lesions[0].detection_id, label: 'HEMORRHAGE' });
    expect(corrected.human_annotations[0]).not.toHaveProperty('score');
    expect(displayedLesions(corrected)[0]).toMatchObject({ canonical_label: 'HEMORRHAGE', displayScore: 0.9 });
  });

  it('removes only the selected active overlay while preserving other detections', async () => {
    const user = userEvent.setup();
    let requestBody: Record<string, unknown> | undefined;
    const removed = { ...item, revision: 3, review_evidence: { ...item.review_evidence!, items: [{ ...item.review_evidence!.items[0], status: 'CLINICIAN_REMOVED' as const }] } };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      requestBody = JSON.parse(String(init?.body));
      return jsonResponse(removed);
    });
    const onSaved = vi.fn();

    withProviders(<LesionActionPopover item={item} selectedLesionId={lesions[0].detection_id} onSaved={onSaved} onDerived={vi.fn()} onClose={vi.fn()} />, '/review/CASE-001');
    await user.click(screen.getByRole('button', { name: /Selected AI suggestion: HE/i }));
    await user.type(await screen.findByPlaceholderText('Reviewer name'), 'Clinician');
    await user.click(screen.getByRole('button', { name: 'Remove from reviewed result' }));

    expect(requestBody).toMatchObject({ action: 'REJECT', detection_id: lesions[0].detection_id });
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ revision: 3 }));
    expect(removed.review_evidence.items[0]).toMatchObject({
      annotation_id: lesions[0].detection_id,
      original_label: 'HEMORRHAGE',
      original_score: 0.9,
      status: 'CLINICIAN_REMOVED',
    });
    expect(displayedLesions(removed)).toEqual([
      expect.objectContaining({ detection_id: lesions[1].detection_id, canonical_label: 'MICROANEURYSM', displayScore: 0.82 }),
    ]);
    expect(lesions[1]).toMatchObject({ canonical_label: 'MICROANEURYSM', score: 0.82 });
  });
});
