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

describe('AnnotationEditorPage human movement', () => {
  it('moves editable human geometry, records undo, and respects lock state', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, json: async () => item } as Response);
    render(
      <ChakraProvider theme={theme}>
        <MemoryRouter initialEntries={['/edit/CASE-001']}>
          <Routes><Route path="/edit/:imageId" element={<AnnotationEditorPage />} /></Routes>
        </MemoryRouter>
      </ChakraProvider>,
    );

    await waitFor(() => expect(screen.getByText('1 human annotation')).toBeInTheDocument());
    const stage = screen.getByLabelText('Retinal image viewer stage');
    const viewport = stage.parentElement as HTMLDivElement;
    Object.defineProperty(viewport, 'clientWidth', { configurable: true, value: 640 });
    Object.defineProperty(viewport, 'clientHeight', { configurable: true, value: 480 });
    const svg = stage.querySelector('svg')!;
    svg.getBoundingClientRect = () => ({
      bottom: 480, height: 480, left: 0, right: 640, top: 0, width: 640, x: 0, y: 0, toJSON: () => ({}),
    });
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
    restoredShape = svg.querySelector('[data-human-shape-id="human-1"] rect')!;
    dispatchPointer(restoredShape, 'pointerDown', { button: 0, pointerId: 3, clientX: 80, clientY: 80 });
    dispatchPointer(svg, 'pointerMove', { pointerId: 3, clientX: 140, clientY: 140 });
    dispatchPointer(svg, 'pointerUp', { button: 0, pointerId: 3, clientX: 140, clientY: 140 });
    expect(svg.querySelector('[data-human-shape-id="human-1"] rect')).toHaveAttribute('x', '100');
  });
});
