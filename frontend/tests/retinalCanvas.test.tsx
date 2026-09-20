import { ChakraProvider } from '@chakra-ui/react';
import { createEvent, fireEvent, render, screen } from '@testing-library/react';
import { RetinalCanvas } from '@/components/review/RetinalCanvas';
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
  human_annotations: [],
  clinician_review: null,
};

function renderCanvas(currentItem = item) {
  return render(
    <ChakraProvider theme={theme}>
      <RetinalCanvas item={currentItem} />
    </ChakraProvider>,
  );
}

function setViewportSize() {
  const stage = screen.getByLabelText('Retinal image viewer stage');
  const viewport = stage.parentElement as HTMLDivElement;
  Object.defineProperty(viewport, 'clientWidth', { configurable: true, value: 640 });
  Object.defineProperty(viewport, 'clientHeight', { configurable: true, value: 480 });
  viewport.getBoundingClientRect = () => ({
    bottom: 480,
    height: 480,
    left: 0,
    right: 640,
    top: 0,
    width: 640,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  fireEvent(window, new Event('resize'));
  return { stage, viewport };
}

function dispatchPointer(target: Element, eventName: 'pointerDown' | 'pointerMove' | 'pointerUp', values: Record<string, number>) {
  const event = createEvent[eventName](target);
  Object.entries(values).forEach(([key, value]) => {
    Object.defineProperty(event, key, { configurable: true, value });
  });
  fireEvent(target, event);
}

describe('RetinalCanvas navigation', () => {
  it('keeps the image and SVG overlays inside one transformed stage', () => {
    renderCanvas();
    const stage = screen.getByLabelText('Retinal image viewer stage');

    expect(stage.querySelector('img')).toBeInTheDocument();
    expect(stage.querySelector('svg')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zoom out' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set zoom to 100 percent' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fit' })).toBeInTheDocument();
  });

  it('supports bounded zoom, cursor-wheel zoom, pan, and fit reset', () => {
    renderCanvas();
    const { stage, viewport } = setViewportSize();

    expect(screen.getByText('Viewer 80%')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(screen.getByText('Viewer 96%')).toBeInTheDocument();

    fireEvent.wheel(viewport, { deltaY: -100, clientX: 320, clientY: 240 });
    expect(screen.getByText('Viewer 115%')).toBeInTheDocument();

    fireEvent.pointerDown(stage.querySelector('svg'), { button: 0, pointerId: 1, clientX: 100, clientY: 100 });
    const transformBeforePan = getComputedStyle(stage).transform;
    fireEvent.pointerMove(stage.querySelector('svg'), { pointerId: 1, clientX: 150, clientY: 140 });
    fireEvent.pointerUp(stage.querySelector('svg'), { pointerId: 1, clientX: 150, clientY: 140 });
    expect(getComputedStyle(stage).transform).not.toBe(transformBeforePan);

    fireEvent.click(screen.getByRole('button', { name: 'Fit' }));
    expect(screen.getByText('Viewer 80%')).toBeInTheDocument();
  });

  it('supports right-drag and Space plus left-drag without entering an annotation tool', () => {
    renderCanvas();
    const { stage, viewport } = setViewportSize();
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    const svg = stage.querySelector('svg')!;

    const beforeRightDrag = getComputedStyle(stage).transform;
    dispatchPointer(svg, 'pointerDown', { button: 2, buttons: 2, pointerId: 2, clientX: 100, clientY: 100 });
    dispatchPointer(svg, 'pointerMove', { buttons: 2, pointerId: 2, clientX: 150, clientY: 140 });
    dispatchPointer(svg, 'pointerUp', { button: 2, buttons: 0, pointerId: 2, clientX: 150, clientY: 140 });
    expect(getComputedStyle(stage).transform).not.toBe(beforeRightDrag);

    const beforeSpaceDrag = getComputedStyle(stage).transform;
    fireEvent.keyDown(window, { code: 'Space', key: ' ' });
    dispatchPointer(svg, 'pointerDown', { button: 0, buttons: 1, pointerId: 3, clientX: 200, clientY: 200 });
    dispatchPointer(svg, 'pointerMove', { buttons: 1, pointerId: 3, clientX: 240, clientY: 230 });
    dispatchPointer(svg, 'pointerUp', { button: 0, buttons: 0, pointerId: 3, clientX: 240, clientY: 230 });
    fireEvent.keyUp(window, { code: 'Space', key: ' ' });
    expect(getComputedStyle(stage).transform).not.toBe(beforeSpaceDrag);

    const contextMenu = createEvent.contextMenu(viewport);
    fireEvent(viewport, contextMenu);
    expect(contextMenu.defaultPrevented).toBe(true);
  });

  it('reports original-image coordinates in the fixed status area', () => {
    renderCanvas();
    const { stage } = setViewportSize();
    const svg = stage.querySelector('svg')!;
    svg.getBoundingClientRect = () => ({
      bottom: 480,
      height: 480,
      left: 0,
      right: 640,
      top: 0,
      width: 640,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    fireEvent.click(screen.getByRole('button', { name: 'Enable coordinate inspector' }));
    dispatchPointer(svg, 'pointerMove', { buttons: 0, clientX: 320, clientY: 240 });

    expect(screen.getByText('Original pixels: X 400.0 - Y 300.0 px')).toBeInTheDocument();
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('resets navigation when the active case changes', () => {
    const { rerender } = renderCanvas();
    setViewportSize();
    fireEvent.click(screen.getByRole('button', { name: 'Set zoom to 100 percent' }));
    expect(screen.getByText('Viewer 100%')).toBeInTheDocument();

    rerender(
      <ChakraProvider theme={theme}>
        <RetinalCanvas item={{ ...item, image_id: 'CASE-002', display_name: 'Case 002' }} />
      </ChakraProvider>,
    );

    expect(screen.getByText('Viewer 80%')).toBeInTheDocument();
  });

  it('opens a full-screen review surface with the same image, overlays, and controls', () => {
    render(
      <ChakraProvider theme={theme}>
        <RetinalCanvas item={item} fullScreenControls={<button type="button">Box tool</button>}>
          <rect data-testid="review-overlay" x="100" y="100" width="80" height="60" />
        </RetinalCanvas>
      </ChakraProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Open full-screen review' }));

    expect(screen.getByText('Full-screen retinal review')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Exit full-screen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Box tool' })).toBeInTheDocument();
    const stage = screen.getByLabelText('Retinal image viewer stage');
    expect(stage.querySelector('img')).toHaveAttribute('src', item.image_url);
    expect(stage.querySelector('[data-testid="review-overlay"]')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Exit full-screen' }));
    expect(screen.getByRole('button', { name: 'Open full-screen review' })).toBeInTheDocument();
  });
});
