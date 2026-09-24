import { ChakraProvider } from '@chakra-ui/react';
import { createEvent, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AnnotationEditorPage } from '@/pages/AnnotationEditorPage';
import type { CaseRecord } from '@/lib/api';
import { theme } from '@/theme';

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
  revision: 0,
  global: null,
  lesion: null,
  lesion_review: null,
  human_annotations: [{
    shape_id: 'human-1',
    type: 'rectangle',
    label: 'MICROANEURYSM',
    geometry: { x: 100, y: 100, width: 100, height: 80 },
    locked: false,
    source: 'HUMAN',
    reviewer: 'Fixture',
    created_at: '',
  }],
  clinician_review: { reviewer: 'Fixture', final_grade: 2, review_action: 'CORRECT_GRADE', remark: '', timestamp: '2026-01-01T00:00:00Z', revision: 1 },
};

function dispatchPointer(target: Element, eventName: 'pointerDown' | 'pointerMove' | 'pointerUp', values: Record<string, number>) {
  const event = createEvent[eventName](target);
  Object.entries(values).forEach(([key, value]) => Object.defineProperty(event, key, { configurable: true, value }));
  fireEvent(target, event);
}

function renderEditor(currentItem: CaseRecord = item, onRequest?: (input: RequestInfo | URL, init?: RequestInit) => unknown) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const body = onRequest?.(input, init) ?? currentItem;
    return { ok: true, json: async () => body } as Response;
  });
  render(
    <ChakraProvider theme={theme}>
      <MemoryRouter initialEntries={['/edit/CASE-001']}>
        <Routes><Route path="/edit/:imageId" element={<AnnotationEditorPage />} /></Routes>
      </MemoryRouter>
    </ChakraProvider>,
  );
}

async function setupStage() {
  await waitFor(() => expect(screen.getByText('1 human annotation')).toBeInTheDocument());
  const stage = screen.getByLabelText('Retinal image viewer stage');
  const viewport = stage.parentElement as HTMLDivElement;
  Object.defineProperty(viewport, 'clientWidth', { configurable: true, value: 640 });
  Object.defineProperty(viewport, 'clientHeight', { configurable: true, value: 480 });
  const svg = stage.querySelector('svg')!;
  svg.getBoundingClientRect = () => ({
    bottom: 480, height: 480, left: 0, right: 640, top: 0, width: 640, x: 0, y: 0, toJSON: () => ({}),
  });
  return { stage, viewport, svg };
}

describe('AnnotationEditorPage human movement', () => {
  it('updates the selected human annotation class and persists its canonical value', async () => {
    let annotationBody: Record<string, unknown> | undefined;
    const softExudateItem = {
      ...item,
      human_annotations: [{ ...item.human_annotations[0], label: 'SOFT_EXUDATE' as const }],
    };
    renderEditor(softExudateItem, (_input, init) => {
      if (init?.body) annotationBody = JSON.parse(String(init.body));
    });
    const { svg } = await setupStage();
    fireEvent.click(svg.querySelector('[data-human-shape-id="human-1"] rect'));

    expect(screen.getByLabelText('Selected annotation class')).toHaveValue('SOFT_EXUDATE');
    fireEvent.change(screen.getByLabelText('Selected annotation class'), { target: { value: 'HEMORRHAGE' } });
    fireEvent.change(screen.getByPlaceholderText('Reviewer name'), { target: { value: 'Clinician' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(annotationBody).toBeDefined());
    expect(annotationBody).toMatchObject({ annotations: [{ label: 'HEMORRHAGE' }] });
  });

  it('opens the AI ROI action panel without starting a pan and supports keyboard selection', async () => {
    const detectionId = 'ai-aaaaaaaaaaaaaaaaaaaa';
    const aiCase: CaseRecord = {
      ...item,
      lesion: {
        model_id: 'prism-dr-5fold', model_version: 'fixture', modality: 'CFP', state: 'AI_SUGGESTION', width: 800, height: 600,
        lesions: [{ detection_id: detectionId, source_label: 'MA', canonical_label: 'MICROANEURYSM', rectangle: [300, 200, 360, 260], score: 0.9, state: 'AI_SUGGESTION' }], warnings: [],
      },
      lesion_review: {
        raw_count: 1, suggestion_count: 1, filtered_count: 0,
        lesions: [{ detection_id: detectionId, source_label: 'MA', canonical_label: 'MICROANEURYSM', rectangle: [300, 200, 360, 260], score: 0.9, state: 'AI_SUGGESTION' }],
        policy: { thresholds: {}, max_per_class: 10, max_total: 10 },
      },
    };
    renderEditor(aiCase);
    const { svg } = await setupStage();
    const setPointerCapture = vi.fn();
    svg.setPointerCapture = setPointerCapture;
    const group = svg.querySelector(`[data-ai-detection-id="${detectionId}"]`)!;
    const hitTarget = group.querySelector('rect')!;

    dispatchPointer(hitTarget, 'pointerDown', { button: 0, pointerId: 11, clientX: 330, clientY: 230 });
    expect(setPointerCapture).not.toHaveBeenCalled();
    fireEvent.click(hitTarget);
    expect(await screen.findByRole('button', { name: 'Confirm' })).toBeInTheDocument();

    const popover = screen.getByRole('dialog', { name: 'AI suggestion' });
    expect(within(popover).getAllByRole('button').map((button) => button.textContent || button.getAttribute('aria-label')))
      .toEqual(['Close AI suggestion', 'Confirm', 'Remove', 'Close']);
    await userEvent.setup().click(within(popover).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog', { name: 'AI suggestion' })).not.toBeInTheDocument();
    fireEvent.keyDown(group, { key: 'Enter' });
    expect(await screen.findByRole('button', { name: 'Confirm' })).toBeInTheDocument();
    expect(group).toHaveAttribute('aria-pressed', 'true');
  });

  it('creates an editable human copy from an AI ROI and autosaves a class correction without its score', async () => {
    const detectionId = 'ai-aaaaaaaaaaaaaaaaaaaa';
    const initial: CaseRecord = {
      ...item,
      clinician_review: { reviewer: 'Clinician', final_grade: 2, review_action: 'ACCEPT', remark: '', timestamp: '2026-01-01T00:00:00Z', revision: 1 },
      annotation_confirmation_status: 'DRAFT',
      lesion: {
        model_id: 'prism-dr-5fold', model_version: 'fixture', modality: 'CFP', state: 'AI_SUGGESTION', width: 800, height: 600,
        lesions: [{ detection_id: detectionId, source_label: 'MA', canonical_label: 'MICROANEURYSM', rectangle: [300, 200, 360, 260], score: 0.9, state: 'AI_SUGGESTION' }], warnings: [],
      },
      lesion_review: {
        raw_count: 1, suggestion_count: 1, filtered_count: 0,
        lesions: [{ detection_id: detectionId, source_label: 'MA', canonical_label: 'MICROANEURYSM', rectangle: [300, 200, 360, 260], score: 0.9, state: 'AI_SUGGESTION' }],
        policy: { thresholds: {}, max_per_class: 10, max_total: 10 },
      },
    };
    const derived: CaseRecord['human_annotations'][number] = {
      shape_id: 'human-derived-1', type: 'rectangle', label: 'MICROANEURYSM', geometry: { x: 300, y: 200, width: 60, height: 60 },
      locked: false, source_detection_id: detectionId, source: 'HUMAN', reviewer: 'Clinician', created_at: '2026-01-01T00:00:00Z',
    };
    let current = initial;
    let annotationRequest: Record<string, unknown> | undefined;
    let confirmationRequest: Record<string, unknown> | undefined;
    window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'Clinician');
    renderEditor(initial, (input, init) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path.endsWith('/annotations/from-ai')) {
        current = { ...current, revision: 1, human_annotations: [...current.human_annotations, derived] };
        return current;
      }
      if (path.endsWith('/annotations') && init?.method === 'PUT') {
        annotationRequest = JSON.parse(String(init.body));
        const request = annotationRequest as { annotations: Array<Record<string, unknown>> };
        current = {
          ...current,
          revision: 2,
          human_annotations: request.annotations.map((annotation) => ({
            ...derived,
            ...annotation,
            geometry: annotation.geometry as typeof derived.geometry,
          })) as CaseRecord['human_annotations'],
        };
        return current;
      }
      if (path.endsWith('/review') && init?.method === 'POST') {
        confirmationRequest = JSON.parse(String(init.body));
        current = { ...current, revision: 3, annotation_confirmation_status: 'CONFIRMED' };
        return current;
      }
      if (path === '/v1/cases') return [];
      return current;
    });
    const user = userEvent.setup();
    const { svg } = await setupStage();
    const aiHitTarget = svg.querySelector(`[data-ai-detection-id="${detectionId}"] rect`)!;
    fireEvent.click(aiHitTarget);
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    const humanGroup = await waitFor(() => {
      const group = svg.querySelector('[data-human-shape-id="human-derived-1"]');
      expect(group).toBeInTheDocument();
      return group;
    });
    expect(humanGroup).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'AI suggestion' })).not.toBeInTheDocument();
    fireEvent.click(humanGroup!.querySelector('rect')!);
    expect(screen.getByLabelText('Selected annotation class')).toHaveValue('MICROANEURYSM');
    await user.selectOptions(screen.getByLabelText('Selected annotation class'), 'HEMORRHAGE');

    await waitFor(() => expect(annotationRequest).toBeDefined(), { timeout: 4000 });
    const derivedRequest = (annotationRequest?.annotations as Array<Record<string, unknown>>)
      .find((entry) => entry.source_detection_id === detectionId);
    expect(derivedRequest).toMatchObject({ source_detection_id: detectionId, label: 'HEMORRHAGE' });
    expect(derivedRequest).not.toHaveProperty('score');
    expect(current.lesion?.lesions[0]).toMatchObject({ canonical_label: 'MICROANEURYSM', score: 0.9 });
    expect(await screen.findByText('Draft saved')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Confirm Annotation' }));
    await waitFor(() => expect(confirmationRequest).toMatchObject({ revision: 2, action: 'CONFIRM_ANNOTATIONS' }));
  });

  it('confirms an annotation-free case without writing an annotation draft', async () => {
    const unchanged: CaseRecord = {
      ...item,
      human_annotations: [],
      annotation_confirmation_status: 'DRAFT',
      clinician_review: { reviewer: 'Clinician', final_grade: 1, review_action: 'CORRECT_GRADE', remark: '', timestamp: '2026-01-01T00:00:00Z', revision: 1 },
    };
    window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'Clinician');
    const requests: string[] = [];
    renderEditor(unchanged, (input) => {
      requests.push(new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname);
      if (requests.at(-1) === '/v1/cases') return [];
      return unchanged;
    });
    await waitFor(() => expect(screen.getByText('0 human annotations')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Confirm Annotation' }));

    expect(requests).not.toContain('/v1/cases/CASE-001/annotations');
    expect(requests).toContain('/v1/cases/CASE-001/review');
  });

  it('moves editable human geometry, records undo, and respects lock state', async () => {
    renderEditor();
    const { svg } = await setupStage();
    const shape = svg.querySelector('[data-human-shape-id="human-1"] rect')!;

    dispatchPointer(shape, 'pointerDown', { button: 0, pointerId: 1, clientX: 80, clientY: 80 });
    dispatchPointer(svg, 'pointerMove', { pointerId: 1, clientX: 120, clientY: 110 });
    dispatchPointer(svg, 'pointerUp', { button: 0, pointerId: 1, clientX: 120, clientY: 110 });
    expect(shape).toHaveAttribute('x', '150');

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(svg.querySelector('[data-human-shape-id="human-1"] rect')).toHaveAttribute('x', '100');

    let restoredShape = svg.querySelector('[data-human-shape-id="human-1"] rect')!;
    dispatchPointer(restoredShape, 'pointerDown', { button: 0, pointerId: 2, clientX: 80, clientY: 80 });
    dispatchPointer(svg, 'pointerUp', { button: 0, pointerId: 2, clientX: 80, clientY: 80 });
    fireEvent.click(screen.getByRole('button', { name: 'Lock selected human annotation' }));
    expect(screen.getByRole('button', { name: 'Unlock selected human annotation' })).toBeInTheDocument();
    expect(svg.querySelectorAll('[data-human-resize-handle]')).toHaveLength(0);
    restoredShape = svg.querySelector('[data-human-shape-id="human-1"] rect')!;
    dispatchPointer(restoredShape, 'pointerDown', { button: 0, pointerId: 3, clientX: 80, clientY: 80 });
    dispatchPointer(svg, 'pointerMove', { pointerId: 3, clientX: 140, clientY: 140 });
    dispatchPointer(svg, 'pointerUp', { button: 0, pointerId: 3, clientX: 140, clientY: 140 });
    expect(svg.querySelector('[data-human-shape-id="human-1"] rect')).toHaveAttribute('x', '100');
    dispatchPointer(restoredShape, 'pointerDown', { button: 0, pointerId: 6, clientX: 160, clientY: 180 });
    dispatchPointer(svg, 'pointerMove', { pointerId: 6, clientX: 240, clientY: 240 });
    dispatchPointer(svg, 'pointerUp', { button: 0, pointerId: 6, clientX: 240, clientY: 240 });
    expect(svg.querySelector('[data-human-shape-id="human-1"] rect')).toHaveAttribute('width', '100');
  });

  it('resizes an unlocked rectangle in original pixels and records one undo step', async () => {
    renderEditor();
    const { svg } = await setupStage();
    const shape = svg.querySelector('[data-human-shape-id="human-1"] rect')!;
    expect(shape).toHaveAttribute('stroke-width', '1.5');
    fireEvent.click(shape);
    expect(svg.querySelector('[data-human-shape-id="human-1"] rect')).toHaveAttribute('stroke-width', '2.5');
    expect(svg.querySelectorAll('[data-human-resize-handle]')).toHaveLength(8);
    const handle = svg.querySelector('[data-human-resize-handle="se"]')!;

    dispatchPointer(handle, 'pointerDown', { button: 0, pointerId: 4, clientX: 160, clientY: 144 });
    dispatchPointer(svg, 'pointerMove', { pointerId: 4, clientX: 240, clientY: 192 });
    dispatchPointer(svg, 'pointerUp', { button: 0, pointerId: 4, clientX: 240, clientY: 192 });

    const resized = svg.querySelector('[data-human-shape-id="human-1"] rect')!;
    expect(resized).toHaveAttribute('x', '100');
    expect(resized).toHaveAttribute('y', '100');
    expect(resized).toHaveAttribute('width', '200');
    expect(resized).toHaveAttribute('height', '140');
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    const restored = svg.querySelector('[data-human-shape-id="human-1"] rect')!;
    expect(restored).toHaveAttribute('width', '100');
    expect(restored).toHaveAttribute('height', '80');
  });

  it('keeps AI rectangles immutable because only Human rectangles receive handles', async () => {
    renderEditor({
      ...item,
      lesion_review: {
        raw_count: 1,
        suggestion_count: 1,
        filtered_count: 1,
        lesions: [{ source_label: 'MA', canonical_label: 'MICROANEURYSM', rectangle: [300, 200, 360, 260], score: 0.9, state: 'SUGGESTION' }],
        policy: { thresholds: {}, max_per_class: 10, max_total: 10 },
      },
    });
    const { svg } = await setupStage();
    fireEvent.click(svg.querySelector('[data-human-shape-id="human-1"] rect')!);
    expect(svg.querySelector('[data-human-resize-handle]')).toBeInTheDocument();
    const aiShape = svg.querySelector('g > title')?.parentElement;
    expect(aiShape?.querySelector('[data-human-resize-handle]')).not.toBeInTheDocument();
    expect(svg.querySelector('title')?.textContent).toMatch(/AI suggestion/);
    const aiRectangle = svg.querySelectorAll('rect')[0];
    const aiX = aiRectangle.getAttribute('x');
    dispatchPointer(aiRectangle, 'pointerDown', { button: 0, pointerId: 8, clientX: 300, clientY: 200 });
    dispatchPointer(svg, 'pointerMove', { pointerId: 8, clientX: 400, clientY: 300 });
    dispatchPointer(svg, 'pointerUp', { button: 0, pointerId: 8, clientX: 400, clientY: 300 });
    expect(aiRectangle).toHaveAttribute('x', aiX);
  });

  it('makes Coordinate Inspector exclusive and returns to Select on exit', async () => {
    renderEditor();
    const { svg, viewport } = await setupStage();
    const selectedShape = svg.querySelector('[data-human-shape-id="human-1"] rect')!;
    fireEvent.click(selectedShape);
    fireEvent.click(screen.getByRole('button', { name: 'Box' }));
    fireEvent.click(screen.getByRole('button', { name: 'Enable coordinate inspector' }));

    expect(screen.getByRole('button', { name: 'Disable coordinate inspector' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Box' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Select' })).toBeDisabled();
    fireEvent.pointerDown(svg, { button: 0, pointerId: 5, clientX: 320, clientY: 240 });
    fireEvent.pointerMove(svg, { pointerId: 5, clientX: 400, clientY: 300 });
    fireEvent.pointerUp(svg, { button: 0, pointerId: 5, clientX: 400, clientY: 300 });
    expect(screen.getByText('1 human annotation')).toBeInTheDocument();
    expect(svg.querySelectorAll('[data-human-resize-handle]')).toHaveLength(0);
    expect(selectedShape).toHaveAttribute('x', '100');

    fireEvent.pointerEnter(viewport);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByRole('button', { name: 'Enable coordinate inspector' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Select' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Box' })).not.toBeDisabled();
  });
});
