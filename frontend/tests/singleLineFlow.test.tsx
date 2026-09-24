import { describe, expect, it, vi, beforeEach } from 'vitest';
import { createEvent, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { CaseRecord, HumanAnnotation, Lesion } from '@/lib/api';
import { renderAppAt } from './testUtils';

/**
 * Single-line clinician flow against a small stateful fake of the existing
 * review API. The fake mirrors backend semantics that matter for the UI:
 * revisions, append-only AI decisions, derived human annotations without a
 * score, and annotation confirmation invalidated by later changes.
 */

const DET_A = 'ai-aaaaaaaaaaaaaaaaaaaa';
const DET_B = 'ai-bbbbbbbbbbbbbbbbbbbb';

function lesion(detection_id: string, canonical_label: Lesion['canonical_label'], rectangle: Lesion['rectangle'], score: number): Lesion {
  return { detection_id, source_label: canonical_label.slice(0, 2), canonical_label, rectangle, score, state: 'AI_SUGGESTION' };
}

function baseCase(id: string, filename: string, overrides: Partial<CaseRecord> = {}): CaseRecord {
  const lesions = [lesion(DET_A, 'HEMORRHAGE', [300, 200, 360, 260], 0.55), lesion(DET_B, 'MICROANEURYSM', [500, 300, 530, 330], 0.8)];
  return {
    image_id: id, display_name: filename.replace('.jpg', ''), filename, source_type: 'PUBLIC', source: 'WORKSPACE_INPUT', modality: 'CFP',
    width: 800, height: 600, image_url: `/${id}.jpg`, state: 'PENDING', revision: 0,
    global: { model_id: 'retfound-aptos5', model_version: 'fixture', modality: 'CFP', state: 'AI_SUGGESTION', grade: 2, probabilities: [], confidence: 0.8, warnings: [] },
    lesion: { model_id: 'prism-dr-5fold', model_version: 'fixture', modality: 'CFP', state: 'AI_SUGGESTION', width: 800, height: 600, lesions, warnings: [] },
    lesion_review: { raw_count: 2, suggestion_count: 2, filtered_count: 0, lesions, policy: { thresholds: {}, max_per_class: 25, max_total: 80 } },
    review_evidence: {
      status: 'Pending', reviewer: null, timestamp: null, summary: { confirmed: 0, added: 0, removed: 0, corrected: 0 }, unresolved_count: 2,
      items: lesions.map((entry) => ({
        annotation_id: entry.detection_id!, source: 'AI' as const, label: entry.canonical_label, score: entry.score, original_score: entry.score,
        status: 'AI_SUGGESTED' as const, model_id: 'prism-dr-5fold', model_version: 'fixture', reviewer: null, timestamp: null,
        original_label: entry.canonical_label, original_rectangle: entry.rectangle, corrected_label: null, corrected_rectangle: null,
      })),
      model_id: 'prism-dr-5fold', model_version: 'fixture', source_sha256: null, analysis_sha256: null, note: '',
    },
    human_annotations: [], clinician_review: null, annotation_confirmation_status: 'DRAFT',
    admission: null, admission_ui: { label: 'Ready', note: '', tone: 'success', action_required: false },
    admission_history: [{ action: 'CONFIRM_IMAGE' }], patient_key: 'PAT01', laterality: 'LEFT', resolver_state: 'RESOLVED',
    queue_state: 'INCLUDED',
    ...overrides,
  };
}

const confirmedGrade = { reviewer: 'Dr. Example', final_grade: 2, review_action: 'ACCEPT' as const, remark: '', timestamp: '2026-01-01T00:00:00Z', revision: 1 };

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

interface FakeLog { method: string; path: string; body?: Record<string, unknown> }

function fakeBackend(initial: CaseRecord[], options: { failAnnotationSave?: boolean } = {}) {
  const cases = new Map(initial.map((entry) => [entry.image_id, structuredClone(entry)]));
  const log: FakeLog[] = [];
  const hash = (entry: CaseRecord) => JSON.stringify([entry.human_annotations, entry.review_evidence?.items.map((i) => [i.status, i.corrected_label, i.corrected_rectangle])]);
  const confirmedHash = new Map<string, string>();
  const refresh = (entry: CaseRecord) => {
    entry.annotation_confirmation_status = confirmedHash.get(entry.image_id) === hash(entry) ? 'CONFIRMED' : 'DRAFT';
    return entry;
  };
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : (input as Request).url, window.location.origin);
    const path = url.pathname;
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : undefined;
    log.push({ method, path, body });
    if (path === '/v1/cases') return json([...cases.values()].map(refresh));
    if (path === '/v1/models') return json([]);
    const match = path.match(/^\/v1\/cases\/([^/]+)(?:\/(.*))?$/);
    if (!match) return json({ detail: 'not found' }, 404);
    const entry = cases.get(decodeURIComponent(match[1]));
    if (!entry) return json({ detail: 'not found' }, 404);
    const action = match[2];
    if (!action) return json(refresh(entry));
    if (action === 'annotations' && options.failAnnotationSave) return json({ detail: 'save failed' }, 500);
    entry.revision += 1;
    if (action === 'review') {
      if (body?.action === 'CONFIRM_ANNOTATIONS') {
        confirmedHash.set(entry.image_id, hash(entry));
        entry.annotation_confirmation = { status: 'CONFIRMED', reviewer: String(body.reviewer), timestamp: '2026-01-02T00:00:00Z', annotation_set_hash: 'h' };
      } else {
        entry.state = 'REVIEWED';
        entry.clinician_review = { reviewer: String(body?.reviewer), final_grade: Number(body?.grade), review_action: body?.action as 'ACCEPT', remark: String(body?.comment ?? ''), timestamp: '2026-01-02T00:00:00Z', revision: entry.revision };
      }
    } else if (action === 'lesion-review') {
      const item = entry.review_evidence!.items.find((candidate) => candidate.annotation_id === body?.detection_id)!;
      if (body?.action === 'REJECT') item.status = 'CLINICIAN_REMOVED';
      if (body?.action === 'CONFIRM') item.status = 'CLINICIAN_CONFIRMED';
      if (body?.action === 'CORRECT') {
        item.status = 'CORRECTED';
        item.corrected_label = String(body.label);
        item.corrected_rectangle = body.rectangle as [number, number, number, number];
      }
    } else if (action === 'annotations/from-ai') {
      const item = entry.review_evidence!.items.find((candidate) => candidate.annotation_id === body?.detection_id)!;
      const rect = item.corrected_rectangle ?? item.original_rectangle!;
      const derived: HumanAnnotation = {
        shape_id: `human-${String(body?.detection_id)}`, type: 'rectangle', label: (item.corrected_label ?? item.original_label) as HumanAnnotation['label'],
        geometry: { x: rect[0], y: rect[1], width: rect[2] - rect[0], height: rect[3] - rect[1] }, locked: false,
        source_detection_id: String(body?.detection_id), source: 'HUMAN', reviewer: String(body?.reviewer), created_at: '2026-01-02T00:00:00Z',
      };
      entry.human_annotations = [...entry.human_annotations, derived];
    } else if (action === 'annotations') {
      entry.human_annotations = (body?.annotations as HumanAnnotation[]).map((annotation) => ({ ...annotation, source: 'HUMAN', reviewer: String(body?.reviewer), created_at: '' }));
    }
    return json(refresh(entry));
  });
  return { cases, log };
}

async function stageSvg() {
  const stage = await screen.findByLabelText('Retinal image viewer stage');
  const viewport = stage.parentElement as HTMLDivElement;
  Object.defineProperty(viewport, 'clientWidth', { configurable: true, value: 800 });
  Object.defineProperty(viewport, 'clientHeight', { configurable: true, value: 600 });
  const svg = stage.querySelector('svg')!;
  svg.getBoundingClientRect = () => ({ bottom: 600, height: 600, left: 0, right: 800, top: 0, width: 800, x: 0, y: 0, toJSON: () => ({}) });
  return svg;
}

function pointer(target: Element, name: 'pointerDown' | 'pointerMove' | 'pointerUp', clientX: number, clientY: number) {
  const event = createEvent[name](target);
  Object.entries({ button: 0, pointerId: 1, clientX, clientY }).forEach(([key, value]) => Object.defineProperty(event, key, { configurable: true, value }));
  fireEvent(target, event);
}

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'Dr. Example');
});

describe('Review page', () => {
  it('offers exactly one forward action and no direct annotation entry', async () => {
    fakeBackend([baseCase('case-1', 'a.jpg')]);
    renderAppAt('/review/case-1');
    const cta = await screen.findByRole('link', { name: 'Continue to clinician review' });
    expect(cta).toHaveAttribute('href', '/clinician-review/case-1');
    expect(screen.queryByRole('link', { name: /edit annotation/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit annotation/i })).not.toBeInTheDocument();
  });

});

describe('Clinician Review grade decision', () => {
  it('requires an explicit grade, has no senior-review or Not Confirm action, and continues to annotation', async () => {
    const user = userEvent.setup();
    const backend = fakeBackend([baseCase('case-1', 'a.jpg')]);
    renderAppAt('/clinician-review/case-1');
    expect(await screen.findByText('Not confirmed', { selector: 'span' })).toBeInTheDocument();
    expect(screen.queryByText(/senior review/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /not confirm/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Final DR grade')).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Confirm DR Grade' })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('Final DR grade'), '3');
    await user.click(screen.getByRole('button', { name: 'Confirm DR Grade' }));
    expect(backend.log.find((entry) => entry.path.endsWith('/review'))?.body).toMatchObject({ action: 'CORRECT_GRADE', grade: 3 });
    expect((await screen.findAllByRole('heading', { name: 'Annotation Editor' })).length).toBeGreaterThan(0);
    expect(screen.getByText('DR grade confirmed · Grade 3')).toBeInTheDocument();
    expect(screen.getAllByText(/Grading complete/).length).toBeGreaterThan(0);
  });

  it('shows a confirmed grade read-only and warns once per edit session', async () => {
    const user = userEvent.setup();
    fakeBackend([baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade })]);
    renderAppAt('/clinician-review/case-1');
    expect(await screen.findByRole('heading', { name: 'DR grade confirmed' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Final DR grade')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Edit confirmed grade' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Edit confirmed DR grade?');
    await user.click(within(dialog).getByRole('button', { name: 'Continue editing' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('Final DR grade'), '1');
    await user.type(screen.getByLabelText('Remark (optional)'), 'revised');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it.each([
    ['2', 'ACCEPT'],
    ['3', 'CORRECT_GRADE'],
  ])('reconfirms a reopened grade %s with %s provenance action', async (selectedGrade, action) => {
    const user = userEvent.setup();
    const backend = fakeBackend([baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade })]);
    renderAppAt('/clinician-review/case-1');
    await user.click(await screen.findByRole('button', { name: 'Edit confirmed grade' }));
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Continue editing' }));
    await user.selectOptions(screen.getByLabelText('Final DR grade'), selectedGrade);
    await user.click(screen.getByRole('button', { name: 'Confirm DR Grade' }));
    await waitFor(() => expect(backend.log.find((entry) => entry.path.endsWith('/review') && entry.body?.grade === Number(selectedGrade))?.body).toMatchObject({ action }));
  });

  it('sends a no-AI grade through the manual-compatible correction path', async () => {
    const user = userEvent.setup();
    const backend = fakeBackend([baseCase('case-1', 'a.jpg', { global: null })]);
    renderAppAt('/clinician-review/case-1');
    await user.selectOptions(await screen.findByLabelText('Final DR grade'), '1');
    await user.click(screen.getByRole('button', { name: 'Confirm DR Grade' }));
    await waitFor(() => expect(backend.log.find((entry) => entry.path.endsWith('/review'))?.body).toMatchObject({ action: 'CORRECT_GRADE', grade: 1 }));
  });

  it('guards Back to Review while a confirmed grade is reopened', async () => {
    const user = userEvent.setup();
    fakeBackend([baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade, annotation_confirmation_status: 'CONFIRMED' })]);
    renderAppAt('/clinician-review/case-1');
    await user.click(await screen.findByRole('button', { name: 'Edit confirmed grade' }));
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Continue editing' }));
    await user.selectOptions(screen.getByLabelText('Final DR grade'), '1');
    await user.click(screen.getByRole('button', { name: 'Back to Review' }));
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('Leave this image?');
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Stay on this image' }));
    expect(screen.getByLabelText('Final DR grade')).toHaveValue('1');
  });

  it('loads a legacy escalated record read-only without restoring the retired action', async () => {
    fakeBackend([baseCase('case-1', 'a.jpg', {
      state: 'ESCALATED',
      clinician_review: { reviewer: 'Legacy', final_grade: null, review_action: 'ESCALATE', remark: 'old', timestamp: '2026-01-01T00:00:00Z', revision: 3 },
    })]);
    renderAppAt('/clinician-review/case-1');
    expect(await screen.findByText(/Legacy senior-review record\./)).toBeInTheDocument();
    expect(screen.getByLabelText('Final DR grade')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /senior review/i })).not.toBeInTheDocument();
  });
});

describe('Annotation Editor single-line completion', () => {
  it('corrects an AI ROI class and geometry in place while preserving AI provenance and never inheriting the score', async () => {
    const user = userEvent.setup();
    const backend = fakeBackend([baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade })]);
    renderAppAt('/edit/case-1');
    const svg = await stageSvg();
    fireEvent.click(svg.querySelector(`[data-ai-detection-id="${DET_A}"] rect`)!);
    const popover = await screen.findByRole('dialog', { name: 'AI suggestion' });
    expect(within(popover).getByTestId('roi-score-line')).toHaveTextContent('Model score: 0.55');
    expect(popover).toHaveTextContent('PRISM-DR');
    expect(within(popover).queryByText(/Use as human annotation|Correct annotation/)).not.toBeInTheDocument();

    await user.selectOptions(within(popover).getByLabelText('Lesion class'), 'HARD_EXUDATE');
    expect(within(popover).getByTestId('roi-score-line')).toHaveTextContent('for AI class Hemorrhage');

    const body = svg.querySelector('[data-roi-edit="body"]')!;
    pointer(body, 'pointerDown', 330, 230);
    pointer(svg, 'pointerMove', 340, 240);
    pointer(svg, 'pointerUp', 340, 240);
    const handle = svg.querySelector('[data-roi-handle="se"]')!;
    pointer(handle, 'pointerDown', 370, 270);
    pointer(svg, 'pointerMove', 380, 280);
    pointer(svg, 'pointerUp', 380, 280);

    await user.click(within(popover).getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'AI suggestion' })).not.toBeInTheDocument());
    const review = backend.log.find((entry) => entry.path.endsWith('/lesion-review'))!;
    expect(review.body).toMatchObject({ action: 'CORRECT', label: 'HARD_EXUDATE', detection_id: DET_A });
    (review.body!.rectangle as number[]).forEach((value, index) => expect(value).toBeCloseTo([310, 210, 380, 280][index], 6));
    expect(backend.log.find((entry) => entry.path.endsWith('/from-ai'))?.body).toMatchObject({ intent: 'CORRECT_AS_HUMAN' });
    const stored = backend.cases.get('case-1')!;
    expect(stored.lesion!.lesions[0]).toMatchObject({ canonical_label: 'HEMORRHAGE', rectangle: [300, 200, 360, 260], score: 0.55 });
    expect(stored.human_annotations[0]).toMatchObject({ label: 'HARD_EXUDATE', source_detection_id: DET_A });
    expect(stored.human_annotations[0]).not.toHaveProperty('score');
    expect(await screen.findByText('EX · clinician corrected')).toBeInTheDocument();
    expect(screen.queryByText('EX · 0.55')).not.toBeInTheDocument();
    expect(await screen.findByText('Annotation confirmed')).toBeInTheDocument();
  });

  it('removes a suggestion, confirms the case without per-ROI review, and opens Confirm Image for an unconfirmed next case', async () => {
    const user = userEvent.setup();
    const backend = fakeBackend([
      baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade }),
      baseCase('case-2', 'b.jpg', { admission_history: [] }),
    ]);
    renderAppAt('/edit/case-1');
    const svg = await stageSvg();
    fireEvent.click(svg.querySelector(`[data-ai-detection-id="${DET_B}"] rect`)!);
    await user.click(within(await screen.findByRole('dialog', { name: 'AI suggestion' })).getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(svg.querySelector(`[data-ai-detection-id="${DET_B}"]`)).not.toBeInTheDocument());
    expect(backend.log.find((entry) => entry.path.endsWith('/lesion-review'))?.body).toMatchObject({ action: 'REJECT', detection_id: DET_B });
    expect(backend.cases.get('case-1')!.lesion!.lesions).toHaveLength(2);

    // DET_A was never inspected: case-level confirmation does not require it.
    await user.click(screen.getByRole('button', { name: 'Confirm Annotation' }));
    expect(await screen.findByText(/Case complete/, { selector: 'div' })).toBeInTheDocument();
    const dialog = await screen.findByRole('dialog', { name: 'Confirm Image' });
    expect(dialog).toHaveTextContent('b.jpg');
    expect(backend.log.some((entry) => entry.body?.action === 'CONFIRM_ANNOTATIONS')).toBe(true);
  });

  it('opens Review directly when the next incomplete case already confirmed its image', async () => {
    const user = userEvent.setup();
    const backend = fakeBackend([
      baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade }),
      baseCase('case-2', 'b.jpg'),
    ]);
    renderAppAt('/edit/case-1');
    await user.click(await screen.findByRole('button', { name: 'Confirm Annotation' }));
    expect(await screen.findByRole('link', { name: 'Continue to clinician review' })).toHaveAttribute('href', '/clinician-review/case-2');
    expect(screen.queryByRole('dialog', { name: 'Confirm Image' })).not.toBeInTheDocument();
    expect(backend.log.some((entry) => entry.body?.action === 'CONFIRM_ANNOTATIONS')).toBe(true);
  });

  it('guards Back to Review while confirmed annotations are reopened and leaves a clean complete case without warning', async () => {
    const user = userEvent.setup();
    fakeBackend([baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade })]);
    await fetch('/v1/cases/case-1/review', { method: 'POST', body: JSON.stringify({ action: 'CONFIRM_ANNOTATIONS', reviewer: 'Dr. Example' }) });
    renderAppAt('/edit/case-1');
    await user.click(await screen.findByRole('button', { name: 'Edit confirmed annotations' }));
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Continue editing' }));
    await user.click(screen.getByRole('button', { name: 'Back to Review' }));
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('Leave this image?');
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Stay on this image' }));
    expect(screen.getByRole('button', { name: 'Confirm Annotation' })).toBeInTheDocument();
  });

  it('keeps a pre-grade deep link read-only without deleting a saved annotation draft', async () => {
    const user = userEvent.setup();
    const draft: HumanAnnotation = { shape_id: 'existing', type: 'rectangle', label: 'HEMORRHAGE', geometry: { x: 40, y: 40, width: 20, height: 20 }, locked: false, source: 'HUMAN', reviewer: 'Dr. Example', created_at: '2026-01-01T00:00:00Z' };
    const backend = fakeBackend([baseCase('case-1', 'a.jpg', { human_annotations: [draft] })]);
    renderAppAt('/edit/case-1');
    expect(await screen.findByText(/Confirm the DR grade first/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Clinician Review' })).toHaveAttribute('href', '/clinician-review/case-1');
    expect(screen.getByRole('button', { name: 'Box', exact: true })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Delete selected' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Confirm Annotation' })).toBeDisabled();
    const svg = await stageSvg();
    fireEvent.click(svg.querySelector(`[data-ai-detection-id="${DET_A}"] rect`)!);
    expect(screen.queryByRole('dialog', { name: 'AI suggestion' })).not.toBeInTheDocument();
    expect(screen.getByText('1 human annotation')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Back to Review' }));
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Leave image' }));
    expect(backend.cases.get('case-1')!.human_annotations).toEqual([draft]);
    expect(backend.log.some((entry) => entry.method !== 'GET')).toBe(false);
  });

  it('keeps the editor and unsaved annotation when a leave-time save fails', async () => {
    const user = userEvent.setup();
    const backend = fakeBackend([baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade })], { failAnnotationSave: true });
    renderAppAt('/edit/case-1');
    await user.click(await screen.findByRole('button', { name: 'Point', exact: true }));
    const svg = await stageSvg();
    pointer(svg, 'pointerDown', 100, 100);
    expect(screen.getByText('1 human annotation')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Back to Review' }));
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Leave image' }));
    expect(await screen.findByText('Save failed')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { name: 'Annotation Editor' }).length).toBeGreaterThan(0);
    expect(screen.getByText('1 human annotation')).toBeInTheDocument();
    expect(backend.log.some((entry) => entry.method === 'PUT' && entry.path.endsWith('/annotations'))).toBe(true);
  });

  it('keeps confirmed annotations read-only and warns once before reopening', async () => {
    const user = userEvent.setup();
    fakeBackend([baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade })]);
    await fetch('/v1/cases/case-1/review', { method: 'POST', body: JSON.stringify({ action: 'CONFIRM_ANNOTATIONS', reviewer: 'Dr. Example' }) });
    renderAppAt('/edit/case-1');
    const svg = await stageSvg();
    expect(await screen.findByText('Annotations confirmed')).toBeInTheDocument();
    expect(screen.getByText('Reviewer: Dr. Example')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm Annotation' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Edit confirmed annotations' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Edit confirmed annotations?');
    await user.click(within(dialog).getByRole('button', { name: 'Continue editing' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    fireEvent.click(svg.querySelector(`[data-ai-detection-id="${DET_A}"] rect`)!);
    expect(await screen.findByRole('dialog', { name: 'AI suggestion' })).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm Annotation' })).toBeInTheDocument();
  });
});

describe('Previous / Next guard', () => {
  it('warns before switching away from an incomplete image and switches on acceptance', async () => {
    const user = userEvent.setup();
    fakeBackend([baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade }), baseCase('case-2', 'b.jpg')]);
    renderAppAt('/edit/case-1');
    const next = await screen.findByRole('button', { name: 'Next case' });
    await waitFor(() => expect(next).toBeEnabled());
    await user.click(next);
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Switch to another image?');
    expect(dialog).toHaveTextContent('Your autosaved draft will be kept. Unconfirmed work will still need your attention.');
    await user.click(within(dialog).getByRole('button', { name: 'Stay on this image' }));
    expect(screen.getAllByRole('heading', { name: 'Annotation Editor' }).length).toBeGreaterThan(0);
    await user.click(next);
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Switch image' }));
    await waitFor(() => expect(screen.getByRole('link', { name: 'Continue to clinician review' })).toHaveAttribute('href', '/clinician-review/case-2'));
  });

  it('navigates a completed image without a warning', async () => {
    const user = userEvent.setup();
    const complete = baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade });
    const backend = fakeBackend([complete, baseCase('case-2', 'b.jpg')]);
    // Mark case-1 complete via the fake confirmation path.
    await fetch('/v1/cases/case-1/review', { method: 'POST', body: JSON.stringify({ action: 'CONFIRM_ANNOTATIONS', reviewer: 'Dr. Example' }) });
    expect(backend.cases.get('case-1')!.annotation_confirmation?.status).toBe('CONFIRMED');
    renderAppAt('/review/case-1');
    const next = await screen.findByRole('button', { name: 'Next case' });
    await waitFor(() => expect(next).toBeEnabled());
    await user.click(next);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await waitFor(() => expect(backend.log.some((entry) => entry.path === '/v1/cases/case-2')).toBe(true));
  });

  it.each([
    ['Next', 'case-1', 'case-2', 'b.jpg'],
    ['Previous', 'case-2', 'case-1', 'a.jpg'],
  ])('routes %s through Confirm Image when the target has no confirmation history', async (direction, currentId, targetId, filename) => {
    const user = userEvent.setup();
    fakeBackend([
      baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade, admission_history: targetId === 'case-1' ? [] : [{ action: 'CONFIRM_IMAGE' }] }),
      baseCase('case-2', 'b.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade, admission_history: targetId === 'case-2' ? [] : [{ action: 'CONFIRM_IMAGE' }] }),
    ]);
    renderAppAt(`/review/${currentId}`);
    const target = await screen.findByRole('button', { name: `${direction} case` });
    await waitFor(() => expect(target).toBeEnabled());
    await user.click(target);
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Switch image' }));
    expect(await screen.findByRole('dialog', { name: 'Confirm Image' })).toHaveTextContent(filename);
  });

  it('leaves a clean complete annotation case through Back to Review without warning', async () => {
    const user = userEvent.setup();
    fakeBackend([baseCase('case-1', 'a.jpg', { state: 'REVIEWED', clinician_review: confirmedGrade })]);
    await fetch('/v1/cases/case-1/review', { method: 'POST', body: JSON.stringify({ action: 'CONFIRM_ANNOTATIONS', reviewer: 'Dr. Example' }) });
    renderAppAt('/edit/case-1');
    await user.click(await screen.findByRole('button', { name: 'Back to Review' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Continue to clinician review' })).toBeInTheDocument();
  });
});

describe('Worklist admission gate', () => {
  it('offers Confirm Image but no Review bypass for an unconfirmed image', async () => {
    const user = userEvent.setup();
    fakeBackend([baseCase('case-1', 'a.jpg', { admission_history: [] })]);
    renderAppAt('/worklist');
    expect(await screen.findByRole('button', { name: 'Confirm Image' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /More actions for/ }));
    expect(screen.queryByText('Open Review without confirming')).not.toBeInTheDocument();
    expect(document.querySelector('a[href="/review/case-1"]')).not.toBeInTheDocument();
  });
});
