import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { RetinalCanvas } from '@/components/review/RetinalCanvas';
import { placeRoiPopover } from '@/components/review/AiRoiPopover';
import { displayedLesions } from '@/components/review/lesionPresentation';
import { editRoiRectangle } from '@/pages/AnnotationEditorPage';
import type { CaseRecord, ReviewEvidenceItem } from '@/lib/api';
import { renderAppAt, withProviders } from './testUtils';

const lesions = [
  { detection_id: 'ai-aaaaaaaaaaaaaaaaaaaa', source_label: 'HE', canonical_label: 'HEMORRHAGE' as const, rectangle: [10, 20, 30, 40] as [number, number, number, number], score: 0.55, state: 'AI_SUGGESTION' },
  { detection_id: 'ai-bbbbbbbbbbbbbbbbbbbb', source_label: 'MA', canonical_label: 'MICROANEURYSM' as const, rectangle: [50, 60, 80, 90] as [number, number, number, number], score: 0.82, state: 'AI_SUGGESTION' },
];

function evidence(overrides: Partial<ReviewEvidenceItem> = {}): ReviewEvidenceItem {
  return {
    annotation_id: lesions[0].detection_id, source: 'AI', label: 'HEMORRHAGE', score: 0.55, original_score: 0.55,
    status: 'AI_SUGGESTED', model_id: 'prism-dr-5fold', model_version: 'revision', reviewer: null, timestamp: null,
    original_label: 'HEMORRHAGE', original_rectangle: lesions[0].rectangle, corrected_label: null, corrected_rectangle: null,
    ...overrides,
  };
}

const item: CaseRecord = {
  image_id: 'CASE-001', display_name: 'Case 001', filename: 'case-001.jpg', source_type: 'SYNTHETIC', source: 'fixture', modality: 'CFP', width: 800, height: 600,
  image_url: null, state: 'PENDING', revision: 2, global: null,
  lesion: { model_id: 'prism-dr-5fold', model_version: 'revision', modality: 'CFP', state: 'AI_SUGGESTION', width: 800, height: 600, lesions, warnings: [] },
  lesion_review: { raw_count: 2, suggestion_count: 2, filtered_count: 0, lesions, policy: { thresholds: {}, max_per_class: 25, max_total: 80 } },
  review_evidence: {
    status: 'Pending review', reviewer: null, timestamp: null,
    summary: { confirmed: 0, added: 0, removed: 0, corrected: 0 }, unresolved_count: 2,
    items: [evidence(), evidence({ annotation_id: lesions[1].detection_id, label: 'MICROANEURYSM', score: 0.82, original_score: 0.82, original_label: 'MICROANEURYSM', original_rectangle: lesions[1].rectangle })],
    model_id: 'prism-dr-5fold', model_version: 'revision', source_sha256: 'a'.repeat(64), analysis_sha256: null,
    note: 'Model evidence remains optional.',
  },
  human_annotations: [], clinician_review: null,
  admission: null, admission_ui: null,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('AI ROI evidence presentation', () => {
  beforeEach(() => window.localStorage.clear());

  it('renders an untouched AI ROI with its class and model score', () => {
    withProviders(<RetinalCanvas item={{ ...item, image_url: '/case-001.jpg' }} />, '/review/CASE-001');
    expect(screen.getByText('HE · 0.55')).toBeInTheDocument();
  });

  it('keeps review image-first without a per-detection queue', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/cases/CASE-001') return jsonResponse(item);
      if (path === '/v1/models') return jsonResponse([]);
      return jsonResponse({ detail: 'Unexpected request' }, 404);
    });
    renderAppAt('/review/CASE-001');
    expect(await screen.findByText('AI lesion suggestions')).toBeInTheDocument();
    expect(screen.queryByText(/unresolved/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Edit annotations/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Edit annotations/i })).not.toBeInTheDocument();
  });

  it('never shows the AI score on a clinician class correction', () => {
    const corrected = { ...item, review_evidence: { ...item.review_evidence!, items: [evidence({ status: 'LABEL_CHANGED', corrected_label: 'HARD_EXUDATE' }), item.review_evidence!.items[1]] } };
    const [first] = displayedLesions(corrected);
    expect(first).toMatchObject({ canonical_label: 'HARD_EXUDATE', displayScore: null, reviewState: 'CLINICIAN_CORRECTED', originalLabel: 'HEMORRHAGE', originalScore: 0.55 });
    withProviders(<RetinalCanvas item={{ ...corrected, image_url: '/case-001.jpg' }} />, '/edit/CASE-001');
    expect(screen.queryByText(/EX · 0\.55/)).not.toBeInTheDocument();
    expect(screen.getByText('EX · clinician corrected')).toBeInTheDocument();
  });

  it('treats a geometry-only correction as clinician corrected and keeps the raw AI box', () => {
    const moved = { ...item, review_evidence: { ...item.review_evidence!, items: [evidence({ status: 'GEOMETRY_CHANGED', corrected_label: 'HEMORRHAGE', corrected_rectangle: [12, 22, 40, 44] }), item.review_evidence!.items[1]] } };
    const [first, second] = displayedLesions(moved);
    expect(first).toMatchObject({ rectangle: [12, 22, 40, 44], displayScore: null, originalRectangle: [10, 20, 30, 40] });
    expect(second).toMatchObject({ displayScore: 0.82, reviewState: 'AI_SUGGESTION' });
    expect(moved.lesion!.lesions[0]).toMatchObject({ rectangle: [10, 20, 30, 40], score: 0.55 });
  });

  it('removes only the rejected ROI from the active overlay', () => {
    const removed = { ...item, review_evidence: { ...item.review_evidence!, items: [evidence({ status: 'CLINICIAN_REMOVED' }), item.review_evidence!.items[1]] } };
    expect(displayedLesions(removed).map((entry) => entry.detection_id)).toEqual([lesions[1].detection_id]);
  });
});

describe('in-place ROI correction geometry', () => {
  it('moves and resizes the correction box inside original image bounds', () => {
    const bounds = { width: 800, height: 600 };
    expect(editRoiRectangle([10, 20, 30, 40], null, [15, 25], [25, 45], bounds)).toEqual([20, 40, 40, 60]);
    expect(editRoiRectangle([10, 20, 30, 40], 'se', [30, 40], [60, 90], bounds)).toEqual([10, 20, 60, 90]);
    expect(editRoiRectangle([10, 20, 30, 40], null, [15, 25], [-500, -500], bounds)).toEqual([0, 0, 20, 20]);
  });
});

describe('ROI popover collision placement', () => {
  const viewport = { width: 1000, height: 700 };
  const card = { width: 290, height: 260 };

  it('places the card beside the ROI without covering it', () => {
    const roi = { left: 200, top: 200, width: 40, height: 40 };
    const position = placeRoiPopover(roi, viewport, card);
    expect(position.placement).toBe('right');
    expect(position.left).toBeGreaterThanOrEqual(roi.left + roi.width);
  });

  it('flips to the left near the right edge', () => {
    expect(placeRoiPopover({ left: 900, top: 300, width: 40, height: 40 }, viewport, card).placement).toBe('left');
  });

  it('docks to the farthest corner when no side fits', () => {
    const position = placeRoiPopover({ left: 100, top: 50, width: 800, height: 600 }, viewport, card);
    expect(position.placement).toBe('docked');
  });
});
