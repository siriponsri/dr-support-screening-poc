import { ChakraProvider } from '@chakra-ui/react';
import { createEvent, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  clinician_review: null,
};

function dispatchPointer(target: Element, eventName: 'pointerDown' | 'pointerMove' | 'pointerUp', values: Record<string, number>) {
  const event = createEvent[eventName](target);
  Object.entries(values).forEach(([key, value]) => Object.defineProperty(event, key, { configurable: true, value }));
  fireEvent(target, event);
}

function renderEditor(currentItem: CaseRecord = item, onRequest?: (input: RequestInfo | URL, init?: RequestInit) => void) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    onRequest?.(input, init);
    return { ok: true, json: async () => currentItem } as Response;
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
  it('displays Soft exudate while saving the canonical SOFT_EXUDATE value', async () => {
    let annotationBody: Record<string, unknown> | undefined;
    const softExudateItem = {
      ...item,
      human_annotations: [{ ...item.human_annotations[0], label: 'SOFT_EXUDATE' as const }],
    };
    renderEditor(softExudateItem, (_input, init) => {
      if (init?.body) annotationBody = JSON.parse(String(init.body));
    });
    await setupStage();

    expect(screen.getByRole('option', { name: 'Soft exudate' })).toHaveValue('SOFT_EXUDATE');
    fireEvent.change(screen.getByPlaceholderText('Reviewer name'), { target: { value: 'Clinician' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(annotationBody).toBeDefined());
    expect(annotationBody).toMatchObject({ annotations: [{ label: 'SOFT_EXUDATE' }] });
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
