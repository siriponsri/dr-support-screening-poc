import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { Box, Button, HStack, IconButton, Image, Modal, ModalBody, ModalCloseButton, ModalContent, ModalHeader, ModalOverlay, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord, HumanAnnotation, Lesion, LesionLabel } from '@/lib/api';
import { Maximize2, Target, ZoomIn, ZoomOut } from '@/lib/icons';
import { displayedLesions, type DisplayedLesion } from './lesionPresentation';

export const LESION_COLORS: Record<LesionLabel, string> = {
  MICROANEURYSM: '#06B6D4',
  HEMORRHAGE: '#84CC16',
  HARD_EXUDATE: '#E879F9',
  SOFT_EXUDATE: '#6366F1',
};

export const LESION_SHORT_LABELS: Record<LesionLabel, string> = {
  MICROANEURYSM: 'MA',
  HEMORRHAGE: 'HE',
  HARD_EXUDATE: 'EX',
  SOFT_EXUDATE: 'SE',
};

export type RectangleResizeHandle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

export function lesionDetectionId(lesion: Lesion, index: number): string {
  return lesion.detection_id ?? `ai-fallback-${index}`;
}

interface RetinalCanvasProps {
  item: CaseRecord;
  showAi?: boolean;
  visibleLesionLabels?: LesionLabel[];
  showHuman?: boolean;
  humanAnnotations?: HumanAnnotation[];
  selectedShapeId?: string | null;
  selectedLesionId?: string | null;
  onSelectLesion?: (detectionId: string) => void;
  onSelectHuman?: (shapeId: string) => void;
  onHumanPointerDown?: (shapeId: string, event: ReactPointerEvent<SVGSVGElement>) => void;
  onHumanResizeStart?: (shapeId: string, handle: RectangleResizeHandle, event: ReactPointerEvent<SVGSVGElement>) => void;
  onCoordinateInspectorChange?: (active: boolean) => void;
  onShortcut?: (shortcut: string) => void;
  onPointerDown?: (event: ReactPointerEvent<SVGSVGElement>) => void;
  onPointerMove?: (event: ReactPointerEvent<SVGSVGElement>) => void;
  onPointerUp?: (event: ReactPointerEvent<SVGSVGElement>) => void;
  onPointerCancel?: (event: ReactPointerEvent<SVGSVGElement>) => void;
  onDoubleClick?: (event: ReactMouseEvent<SVGSVGElement>) => void;
  fullScreenControls?: ReactNode;
  /**
   * Viewport-level overlay (for example the selected AI ROI card). Rendered
   * inside the inline and full-screen viewer so it follows the active surface.
   */
  renderOverlay?: (context: ViewerOverlayContext) => ReactNode;
  /** SVG content in original-image space that needs the current viewer scale. */
  renderInStage?: (scale: number) => ReactNode;
  children?: ReactNode;
}

export interface ViewerRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface ViewerOverlayContext {
  /** Project an original-image rectangle [x1, y1, x2, y2] into viewport pixels. */
  toViewport: (rectangle: [number, number, number, number]) => ViewerRect;
  viewport: { width: number; height: number };
  fullScreen: boolean;
}

interface ViewerView {
  scale: number;
  panX: number;
  panY: number;
}

interface ViewportSize {
  width: number;
  height: number;
}

const MIN_SCALE = 0.5;
const MAX_SCALE = 4;
const ZOOM_FACTOR = 1.2;

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function centeredView(scale: number, viewport: ViewportSize, item: CaseRecord): ViewerView {
  return {
    scale,
    panX: (viewport.width - item.width * scale) / 2,
    panY: (viewport.height - item.height * scale) / 2,
  };
}

function constrainView(view: ViewerView, viewport: ViewportSize, item: CaseRecord): ViewerView {
  const scaledWidth = item.width * view.scale;
  const scaledHeight = item.height * view.scale;
  const centeredX = (viewport.width - scaledWidth) / 2;
  const centeredY = (viewport.height - scaledHeight) / 2;
  const panX = scaledWidth <= viewport.width ? centeredX : clamp(view.panX, viewport.width - scaledWidth, 0);
  const panY = scaledHeight <= viewport.height ? centeredY : clamp(view.panY, viewport.height - scaledHeight, 0);
  return { ...view, panX, panY };
}

function prettyLabel(label: string) {
  return label.replace(/_/g, ' ');
}

function labelPoint(lesion: Lesion) {
  return { x: lesion.rectangle[0], y: Math.max(14, lesion.rectangle[1] - 4) };
}

function annotationLabelPoint(annotation: HumanAnnotation) {
  const geometry = annotation.geometry;
  if ('points' in geometry) return { x: geometry.points[0][0], y: Math.max(14, geometry.points[0][1] - 4) };
  if ('cx' in geometry) return { x: geometry.cx - geometry.radius, y: Math.max(14, geometry.cy - geometry.radius - 4) };
  return { x: geometry.x, y: Math.max(14, geometry.y - 4) };
}

function isEditableTarget(target: EventTarget | null) {
  const element = target instanceof HTMLElement ? target : null;
  return Boolean(element?.closest('input, textarea, select, button, [contenteditable="true"]'));
}

function originalPointFromEvent(event: ReactPointerEvent<SVGSVGElement>, item: CaseRecord) {
  const bounds = event.currentTarget.getBoundingClientRect();
  const clientX = Number.isFinite(event.clientX) ? event.clientX : bounds.left;
  const clientY = Number.isFinite(event.clientY) ? event.clientY : bounds.top;
  return {
    x: clamp(((clientX - bounds.left) / Math.max(bounds.width, 1)) * item.width, 0, item.width),
    y: clamp(((clientY - bounds.top) / Math.max(bounds.height, 1)) * item.height, 0, item.height),
  };
}

function AiShape({
  lesion,
  detectionId,
  selected,
  dimmed = false,
  modelId,
  modelVersion,
  onSelect,
}: {
  lesion: DisplayedLesion;
  detectionId: string;
  selected: boolean;
  dimmed?: boolean;
  modelId?: string;
  modelVersion?: string;
  onSelect?: (detectionId: string) => void;
}) {
  const [x1, y1, x2, y2] = lesion.rectangle;
  const color = LESION_COLORS[lesion.canonical_label as LesionLabel] ?? LESION_COLORS.MICROANEURYSM;
  const label = prettyLabel(lesion.canonical_label);
  const shortLabel = lesion.canonical_label === 'MICROANEURYSM' ? 'MA'
    : lesion.canonical_label === 'HEMORRHAGE' ? 'HE'
      : lesion.canonical_label === 'HARD_EXUDATE' ? 'EX' : 'SE';
  const textPoint = labelPoint(lesion);
  const corrected = lesion.reviewState === 'CLINICIAN_CORRECTED';
  const displayScore = lesion.displayScore;
  return (
    <g
      pointerEvents="auto"
      data-ai-detection-id={detectionId}
      role={onSelect ? 'button' : undefined}
      tabIndex={onSelect ? 0 : undefined}
      aria-label={onSelect ? (corrected
        ? `Clinician-corrected ROI: ${label}. Original AI suggestion ${prettyLabel(lesion.originalLabel ?? lesion.canonical_label)}, model score ${(lesion.originalScore ?? lesion.score).toFixed(2)}`
        : `AI suggestion: ${label}, model score ${lesion.score.toFixed(2)}`) : undefined}
      aria-pressed={onSelect ? selected : undefined}
      onClick={(event) => {
        event.stopPropagation();
        onSelect?.(detectionId);
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        event.stopPropagation();
        onSelect?.(detectionId);
      }}
      style={{ cursor: onSelect ? 'pointer' : undefined, opacity: dimmed ? 0.45 : 1 }}
    >
      <title>{corrected
        ? `Clinician corrected: ${label}. Original AI suggestion: ${prettyLabel(lesion.originalLabel ?? lesion.canonical_label)} - detection confidence ${(lesion.originalScore ?? lesion.score).toFixed(2)}${modelId ? ` - ${modelId}${modelVersion ? ` ${modelVersion}` : ''}` : ''}`
        : `AI suggestion: ${label} - detection confidence ${lesion.score.toFixed(2)}${modelId ? ` - ${modelId}${modelVersion ? ` ${modelVersion}` : ''}` : ''}`}</title>
      <rect
        x={x1}
        y={y1}
        width={x2 - x1}
        height={y2 - y1}
        fill="transparent"
        stroke="transparent"
        strokeWidth={18}
        vectorEffect="non-scaling-stroke"
        pointerEvents="all"
        aria-hidden="true"
      />
      {selected && (
        <rect
          data-ai-selected-halo="true"
          x={x1}
          y={y1}
          width={x2 - x1}
          height={y2 - y1}
          fill="none"
          stroke="#FFFFFF"
          strokeWidth={7}
          strokeOpacity={0.9}
          vectorEffect="non-scaling-stroke"
          pointerEvents="none"
        />
      )}
      <rect
        x={x1}
        y={y1}
        width={x2 - x1}
        height={y2 - y1}
        fill={color}
        fillOpacity={selected ? 0.2 : 0.12}
        stroke={color}
        strokeWidth={selected ? 3.5 : Math.max(2, (x2 - x1) / 120)}
        strokeDasharray={corrected ? undefined : '10 6'}
        vectorEffect="non-scaling-stroke"
      />
      <text x={textPoint.x} y={textPoint.y} fill={color} fontSize={Math.max(10, Math.min(18, (x2 - x1) / 8))} fontWeight="700">
        {corrected ? `${shortLabel} · clinician corrected` : `${shortLabel} · ${displayScore?.toFixed(2) ?? ''}`}
      </text>
    </g>
  );
}

function HumanShape({
  annotation,
  selected,
  scale,
  inspectorActive,
  onSelect,
}: {
  annotation: HumanAnnotation;
  selected: boolean;
  scale: number;
  inspectorActive: boolean;
  onSelect?: (shapeId: string) => void;
}) {
  const color = LESION_COLORS[annotation.label];
  const locked = annotation.locked !== false;
  const common = {
    fill: color,
    fillOpacity: 0.3,
    stroke: selected ? 'var(--chakra-colors-text-primary)' : color,
    strokeWidth: selected ? 2.5 : 1.5,
    vectorEffect: 'non-scaling-stroke' as const,
    onClick: (event: React.MouseEvent) => {
      if (inspectorActive) return;
      event.stopPropagation();
      onSelect?.(annotation.shape_id);
    },
  };
  const geometry = annotation.geometry;
  const handleSize = 10 / Math.max(scale, 0.01);
  const handlePositions: Array<[RectangleResizeHandle, number, number, string]> = [];
  if (annotation.type === 'rectangle' && 'width' in geometry) {
    const x2 = geometry.x + geometry.width;
    const y2 = geometry.y + geometry.height;
    handlePositions.splice(0, handlePositions.length,
      ['nw', geometry.x, geometry.y, 'nwse-resize'],
      ['n', geometry.x + geometry.width / 2, geometry.y, 'ns-resize'],
      ['ne', x2, geometry.y, 'nesw-resize'],
      ['e', x2, geometry.y + geometry.height / 2, 'ew-resize'],
      ['se', x2, y2, 'nwse-resize'],
      ['s', geometry.x + geometry.width / 2, y2, 'ns-resize'],
      ['sw', geometry.x, y2, 'nesw-resize'],
      ['w', geometry.x, geometry.y + geometry.height / 2, 'ew-resize'],
    );
  }
  return (
    <g data-human-shape-id={annotation.shape_id}>
      <title>{`HUMAN annotation: ${prettyLabel(annotation.label)}${locked ? ' (locked)' : ''}`}</title>
      {annotation.type === 'rectangle' && 'width' in geometry && <rect {...common} x={geometry.x} y={geometry.y} width={geometry.width} height={geometry.height} />}
      {annotation.type === 'polygon' && 'points' in geometry && <polygon {...common} points={geometry.points.map((point) => point.join(',')).join(' ')} />}
      {annotation.type === 'point' && 'x' in geometry && !('width' in geometry) && <circle {...common} cx={geometry.x} cy={geometry.y} r={Math.max(6, Math.min(18, Math.min(geometry.x, geometry.y) / 10))} />}
      {annotation.type === 'circle' && 'radius' in geometry && <circle {...common} cx={geometry.cx} cy={geometry.cy} r={geometry.radius} />}
      {selected && !locked && !inspectorActive && annotation.type === 'rectangle' && handlePositions.map(([handle, x, y, cursor]) => (
        <rect
          key={handle}
          data-human-resize-handle={handle}
          x={x - handleSize / 2}
          y={y - handleSize / 2}
          width={handleSize}
          height={handleSize}
          fill="var(--chakra-colors-text-inverse)"
          stroke="var(--chakra-colors-text-primary)"
          strokeWidth={1.5}
          vectorEffect="non-scaling-stroke"
          style={{ cursor }}
        />
      ))}
      <text
        x={annotationLabelPoint(annotation).x}
        y={annotationLabelPoint(annotation).y}
        fill="var(--chakra-colors-text-primary)"
        fontSize="14"
        fontWeight="700"
        pointerEvents="none"
      >
        HUMAN - {LESION_SHORT_LABELS[annotation.label]}
      </text>
    </g>
  );
}

export function RetinalCanvas({
  item,
  showAi = true,
  visibleLesionLabels,
  showHuman = true,
  humanAnnotations = item.human_annotations,
  selectedShapeId,
  selectedLesionId,
  onSelectLesion,
  onSelectHuman,
  onHumanPointerDown,
  onHumanResizeStart,
  onCoordinateInspectorChange,
  onShortcut,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onDoubleClick,
  fullScreenControls,
  renderOverlay,
  renderInStage,
  children,
}: RetinalCanvasProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const panRef = useRef<{ pointerId: number; startX: number; startY: number; panX: number; panY: number; scale: number } | null>(null);
  const spacePressedRef = useRef(false);
  const pointerOverViewerRef = useRef(false);
  const shortcutRef = useRef(onShortcut);
  shortcutRef.current = onShortcut;
  const [viewport, setViewport] = useState<ViewportSize>({ width: 0, height: 0 });
  const [view, setView] = useState<ViewerView>({ scale: 1, panX: 0, panY: 0 });
  const [isFit, setIsFit] = useState(true);
  const [isPanning, setIsPanning] = useState(false);
  const [isSpacePressed, setIsSpacePressed] = useState(false);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [isCoordinateInspector, setIsCoordinateInspector] = useState(false);
  const [pointerCoordinate, setPointerCoordinate] = useState<{ x: number; y: number } | null>(null);
  const [imageLoadError, setImageLoadError] = useState(false);

  const setCoordinateInspector = useCallback((active: boolean) => {
    setIsCoordinateInspector(active);
    onCoordinateInspectorChange?.(active);
    if (!onCoordinateInspectorChange) shortcutRef.current?.('v');
  }, [onCoordinateInspectorChange]);

  const fitScale = viewport.width > 0 && viewport.height > 0
    ? Math.min(viewport.width / item.width, viewport.height / item.height)
    : 1;
  const minScale = Math.min(MIN_SCALE, fitScale);
  const maxScale = Math.max(MAX_SCALE, fitScale);
  const fitView = useMemo(() => centeredView(fitScale, viewport, item), [fitScale, item, viewport]);
  const displayView = useMemo(() => {
    const bounded = { ...view, scale: clamp(view.scale, minScale, maxScale) };
    return isFit ? fitView : constrainView(bounded, viewport, item);
  }, [fitView, isFit, item, maxScale, minScale, view, viewport]);

  useEffect(() => {
    setImageLoadError(false);
  }, [item.image_url]);

  useEffect(() => {
    setIsFit(true);
    setView({ scale: 1, panX: 0, panY: 0 });
    panRef.current = null;
    setIsPanning(false);
  }, [isFullScreen, item.image_id]);

  useEffect(() => {
    let observer: ResizeObserver | null = null;
    const measure = () => {
      const node = viewportRef.current;
      if (!node) return;
      const bounds = node.getBoundingClientRect();
      const width = node.clientWidth || bounds.width;
      const height = node.clientHeight || bounds.height;
      if (width > 0 && height > 0) setViewport({ width, height });
    };
    const observeViewport = () => {
      const node = viewportRef.current;
      if (!node) return;
      measure();
      if (typeof ResizeObserver !== 'undefined' && !observer) {
        observer = new ResizeObserver(measure);
        observer.observe(node);
      }
    };
    // Chakra's modal content is portaled after this component's first effect.
    const frame = window.requestAnimationFrame(observeViewport);
    const retry = window.setTimeout(observeViewport, 50);
    window.addEventListener('resize', measure);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(retry);
      observer?.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [isFullScreen, item.height, item.image_id, item.width]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return;
      const viewerHasFocus = isFullScreen || pointerOverViewerRef.current || viewportRef.current?.contains(document.activeElement);
      if (event.code === 'Space') {
        if (!viewerHasFocus) return;
        spacePressedRef.current = true;
        setIsSpacePressed(true);
        event.preventDefault();
        return;
      }
      const shortcut = event.key.toLowerCase();
      if (!viewerHasFocus && !(isCoordinateInspector && shortcut === 'escape')) return;
      if (shortcut === 'f') {
        panRef.current = null;
        setIsPanning(false);
        setIsFit(true);
        event.preventDefault();
      } else if (shortcut === 'x') {
        setCoordinateInspector(!isCoordinateInspector);
        if (isCoordinateInspector) setPointerCoordinate(null);
        event.preventDefault();
      } else if (shortcut === 'escape') {
        if (isCoordinateInspector) {
          setCoordinateInspector(false);
          setPointerCoordinate(null);
        }
        shortcutRef.current?.(shortcut);
        event.preventDefault();
      } else if (shortcut === 'v' || shortcut === 'b' || shortcut === 'l' || shortcut.startsWith('arrow')) {
        shortcutRef.current?.(shortcut);
        event.preventDefault();
      }
    };
    const handleKeyUp = (event: KeyboardEvent) => {
      if (event.code === 'Space') {
        spacePressedRef.current = false;
        setIsSpacePressed(false);
        setIsPanning(false);
      }
    };
    const handleBlur = () => {
      spacePressedRef.current = false;
      setIsSpacePressed(false);
      setIsPanning(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', handleBlur);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', handleBlur);
    };
  }, [isCoordinateInspector, isFullScreen, setCoordinateInspector]);

  const setCenteredScale = useCallback((nextScale: number) => {
    const scale = clamp(nextScale, minScale, maxScale);
    setIsFit(false);
    setView(centeredView(scale, viewport, item));
  }, [item, maxScale, minScale, viewport]);

  const zoomAround = useCallback((nextScale: number, focalPoint?: { x: number; y: number }) => {
    const current = displayView;
    const scale = clamp(nextScale, minScale, maxScale);
    if (!focalPoint) {
      setCenteredScale(scale);
      return;
    }
    const ratio = scale / current.scale;
    const next = constrainView(
      {
        scale,
        panX: focalPoint.x - (focalPoint.x - current.panX) * ratio,
        panY: focalPoint.y - (focalPoint.y - current.panY) * ratio,
      },
      viewport,
      item,
    );
    setIsFit(false);
    setView(next);
  }, [displayView, item, maxScale, minScale, setCenteredScale, viewport]);

  const handleWheel = useCallback((event: React.WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const focalPoint = { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
    zoomAround(displayView.scale * (event.deltaY < 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR), focalPoint);
  }, [displayView.scale, zoomAround]);

  const handlePointerDown = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    viewportRef.current?.focus({ preventScroll: true });
    const isRightButton = event.button === 2;
    const isLeftButton = event.button === 0 || event.button === undefined;
    const isTemporaryPan = isLeftButton && spacePressedRef.current;
    const humanTarget = event.target instanceof Element
      ? event.target.closest<SVGGElement>('[data-human-shape-id]')
      : null;

    if (!isLeftButton && !isRightButton) return;
    if (isCoordinateInspector && isLeftButton && !isTemporaryPan) {
      setPointerCoordinate(originalPointFromEvent(event, item));
      event.preventDefault();
      return;
    }
    const aiTarget = event.target instanceof Element
      ? event.target.closest<SVGGElement>('[data-ai-detection-id]')
      : null;
    if (aiTarget && onSelectLesion && isLeftButton && !isTemporaryPan && !isRightButton) return;
    const resizeTarget = event.target instanceof Element
      ? event.target.closest<SVGRectElement>('[data-human-resize-handle]')
      : null;
    if (resizeTarget && !isTemporaryPan && !isRightButton) {
      const humanTarget = resizeTarget.closest<SVGGElement>('[data-human-shape-id]');
      const shapeId = humanTarget?.dataset.humanShapeId;
      const handle = resizeTarget.dataset.humanResizeHandle as RectangleResizeHandle | undefined;
      if (shapeId && handle) {
        onSelectHuman?.(shapeId);
        onHumanResizeStart?.(shapeId, handle, event);
        if (event.defaultPrevented) return;
      }
    }
    if (humanTarget && !isTemporaryPan && !isRightButton) {
      const shapeId = humanTarget.dataset.humanShapeId;
      if (shapeId) {
        onSelectHuman?.(shapeId);
        onHumanPointerDown?.(shapeId, event);
        if (event.defaultPrevented) return;
      }
    }

    if (isRightButton || isTemporaryPan) {
      event.preventDefault();
    } else {
      onPointerDown?.(event);
      if (event.defaultPrevented) return;
    }

    const current = displayView;
    panRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      panX: current.panX,
      panY: current.panY,
      scale: current.scale,
    };
    setIsFit(false);
    setView(current);
    setIsPanning(true);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }, [displayView, isCoordinateInspector, item, onHumanPointerDown, onHumanResizeStart, onPointerDown, onSelectHuman, onSelectLesion]);

  const handlePointerMove = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    if (isCoordinateInspector) setPointerCoordinate(originalPointFromEvent(event, item));
    const pan = panRef.current;
    if (!pan) {
      if (isCoordinateInspector) return;
      onPointerMove?.(event);
      return;
    }
    const next = constrainView(
      {
        scale: pan.scale,
        panX: pan.panX + (Number.isFinite(event.clientX) ? event.clientX : pan.startX) - pan.startX,
        panY: pan.panY + (Number.isFinite(event.clientY) ? event.clientY : pan.startY) - pan.startY,
      },
      viewport,
      item,
    );
    setView(next);
    event.preventDefault();
  }, [isCoordinateInspector, item, onPointerMove, viewport]);

  const handlePointerUp = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    if (panRef.current) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
      panRef.current = null;
      setIsPanning(false);
      event.preventDefault();
      return;
    }
    if (isCoordinateInspector) {
      event.preventDefault();
      return;
    }
    onPointerUp?.(event);
  }, [isCoordinateInspector, onPointerUp]);

  const handleDoubleClick = useCallback((event: ReactMouseEvent<SVGSVGElement>) => {
    if (isCoordinateInspector) {
      event.preventDefault();
      return;
    }
    onDoubleClick?.(event);
    if (event.defaultPrevented) return;
    panRef.current = null;
    setIsPanning(false);
    setIsFit(true);
  }, [isCoordinateInspector, onDoubleClick]);

  const handlePointerCancel = useCallback((event: ReactPointerEvent<SVGSVGElement>) => {
    panRef.current = null;
    setIsPanning(false);
    onPointerCancel?.(event);
  }, [onPointerCancel]);

  const handleContextMenu = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
  }, []);

  const handlePointerLeave = useCallback(() => {
    pointerOverViewerRef.current = false;
    setPointerCoordinate(null);
  }, []);

  const handlePointerEnter = useCallback(() => {
    pointerOverViewerRef.current = true;
  }, []);

  const transform = `translate(${displayView.panX}px, ${displayView.panY}px) scale(${displayView.scale})`;
  const zoomPercent = Math.round(displayView.scale * 100);
  const aiLesions = displayedLesions(item).filter((lesion) => (
    !visibleLesionLabels || visibleLesionLabels.includes(lesion.canonical_label as LesionLabel)
  ));
  const coordinateText = pointerCoordinate
    ? `X ${pointerCoordinate.x.toFixed(1)} - Y ${pointerCoordinate.y.toFixed(1)} px`
    : 'Move over the image to inspect original-image pixels';

  const viewerStatus = (fullScreen = false) => (
    <HStack
      spacing={3}
      flexWrap="wrap"
      minH="28px"
      fontSize="xs"
      color="text.secondary"
      sx={{ fontVariantNumeric: 'tabular-nums' }}
      aria-live="polite"
    >
      <Text fontWeight="semibold" color="text.primary">Viewer {zoomPercent}%</Text>
      <Text>{fullScreen ? 'Scroll to zoom - right-drag or Space + drag to pan - double-click to fit' : 'All overlay geometry remains in original image pixels.'}</Text>
      {isCoordinateInspector && <Text color="text.primary" fontWeight="semibold">Original pixels: {coordinateText}</Text>}
      {fullScreen && <Text>Geometry: original image pixels</Text>}
      <Text><Box as="span" display="inline-block" w="10px" h="10px" mr={1} bg="transparent" borderWidth="2px" borderStyle="dashed" borderColor={LESION_COLORS.MICROANEURYSM} />AI suggestion</Text>
      <Text><Box as="span" display="inline-block" w="10px" h="10px" mr={1} bg="text.primary" borderWidth="2px" borderColor="text.primary" opacity={0.3} />Human annotation</Text>
    </HStack>
  );

  const zoomControls = (fullScreen = false) => (
    <HStack spacing={1} flexWrap="wrap">
      <IconButton
        aria-label="Zoom out"
        title="Zoom out"
        icon={<ZoomOut size={15} />}
        size="sm"
        variant="outline"
        onClick={() => zoomAround(displayView.scale / ZOOM_FACTOR)}
        isDisabled={displayView.scale <= minScale + 0.001}
      />
      <Button size="sm" variant="outline" onClick={() => setCenteredScale(1)} aria-label="Set zoom to 100 percent">100%</Button>
      <IconButton
        aria-label="Zoom in"
        title="Zoom in"
        icon={<ZoomIn size={15} />}
        size="sm"
        variant="outline"
        onClick={() => zoomAround(displayView.scale * ZOOM_FACTOR)}
        isDisabled={displayView.scale >= maxScale - 0.001}
      />
      <Button size="sm" variant="outline" leftIcon={<Maximize2 size={14} />} onClick={() => setIsFit(true)}>Fit</Button>
      <IconButton
        aria-label={isCoordinateInspector ? 'Disable coordinate inspector' : 'Enable coordinate inspector'}
        title={isCoordinateInspector ? 'Disable coordinate inspector' : 'Show original-image coordinates'}
        icon={<Target size={15} />}
        size="sm"
        variant={isCoordinateInspector ? 'solid' : 'outline'}
        aria-pressed={isCoordinateInspector}
        onClick={() => {
          const nextEnabled = !isCoordinateInspector;
          setCoordinateInspector(nextEnabled);
          if (!nextEnabled) setPointerCoordinate(null);
        }}
      />
      {fullScreen ? (
        <Button size="sm" variant="secondary" onClick={() => setIsFullScreen(false)}>Exit full-screen</Button>
      ) : (
        <IconButton
          aria-label="Open full-screen review"
          title="Open full-screen review"
          icon={<Maximize2 size={15} />}
          size="sm"
          variant="outline"
          onClick={() => setIsFullScreen(true)}
        />
      )}
    </HStack>
  );

  const viewerViewport = (fullScreen = false) => (
    <Box
      ref={viewportRef}
      tabIndex={0}
      position="relative"
      w="100%"
      h={fullScreen ? '100%' : undefined}
      flex={fullScreen ? '1 1 auto' : undefined}
      minH={fullScreen ? 0 : undefined}
      aspectRatio={fullScreen ? undefined : `${item.width} / ${item.height}`}
      bg="viewer.background"
      borderRadius={fullScreen ? 'md' : 'md'}
      overflow="hidden"
      cursor={isCoordinateInspector ? 'crosshair' : isPanning ? 'grabbing' : 'grab'}
      sx={{ touchAction: 'none' }}
      onWheel={handleWheel}
      onContextMenu={handleContextMenu}
      onPointerEnter={handlePointerEnter}
    >
      {imageLoadError && (
        <Box
          role="alert"
          position="absolute"
          zIndex={2}
          top={2}
          left={2}
          right={2}
          maxW="480px"
          px={3}
          py={2}
          bg="blackAlpha.700"
          borderWidth="1px"
          borderColor="status.warning"
          borderRadius="md"
        >
          <Text fontSize="sm" color="white">Preview unavailable. This source could not be decoded for browser display.</Text>
        </Box>
      )}
      <Box
        position="absolute"
        top={0}
        left={0}
        width={`${item.width}px`}
        height={`${item.height}px`}
        transform={transform}
        transformOrigin="0 0"
        aria-label="Retinal image viewer stage"
      >
        <Image
          src={item.image_url ?? undefined}
          alt={`${item.display_name} retinal image`}
          position="absolute"
          inset={0}
          w="100%"
          h="100%"
          objectFit="fill"
          userSelect="none"
          pointerEvents="none"
          draggable={false}
          onError={() => setImageLoadError(true)}
        />
        <Box
          as="svg"
          position="absolute"
          inset={0}
          width={`${item.width}px`}
          height={`${item.height}px`}
          viewBox={`0 0 ${item.width} ${item.height}`}
          preserveAspectRatio="none"
          role="group"
          aria-label="Retinal image annotation canvas"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
          onDoubleClick={handleDoubleClick}
          onPointerLeave={handlePointerLeave}
        >
          {showAi && aiLesions.map((lesion, index) => {
            const detectionId = lesionDetectionId(lesion, index);
            return (
              <AiShape
                key={detectionId}
                lesion={lesion}
                detectionId={detectionId}
                selected={detectionId === selectedLesionId}
                dimmed={Boolean(selectedLesionId) && detectionId !== selectedLesionId}
                modelId={item.lesion?.model_id}
                modelVersion={item.lesion?.model_version}
                onSelect={onSelectLesion}
              />
            );
          })}
          {showHuman && humanAnnotations.map((annotation) => (
            <HumanShape
              key={annotation.shape_id}
              annotation={annotation}
              selected={annotation.shape_id === selectedShapeId}
              scale={displayView.scale}
              inspectorActive={isCoordinateInspector}
              onSelect={onSelectHuman}
            />
          ))}
          {children}
          {renderInStage?.(displayView.scale)}
        </Box>
      </Box>
      {renderOverlay?.({
        toViewport: ([x1, y1, x2, y2]) => ({
          left: displayView.panX + x1 * displayView.scale,
          top: displayView.panY + y1 * displayView.scale,
          width: (x2 - x1) * displayView.scale,
          height: (y2 - y1) * displayView.scale,
        }),
        viewport,
        fullScreen,
      })}
    </Box>
  );

  return (
    <Box>
      {!isFullScreen && (
        <>
          <HStack mb={2} justify="space-between" align="center" flexWrap="wrap" gap={2}>
            <Text fontSize="xs" color="text.secondary">Scroll to zoom - drag to pan - double-click to fit</Text>
            {zoomControls()}
          </HStack>
          {viewerViewport()}
          {viewerStatus()}
        </>
      )}
      {isFullScreen && (
        <Modal isOpen onClose={() => setIsFullScreen(false)} size="full" motionPreset="slideInBottom">
          <ModalOverlay bg="blackAlpha.800" />
          <ModalContent maxW="100vw" w="100vw" h="100vh" maxH="100vh" m={0} borderRadius={0}>
            <ModalHeader px={5} py={3}>
              <HStack justify="space-between" align="center" spacing={4} pr={8}>
                <Stack spacing={0} minW={0}>
                  <Text fontSize="md" noOfLines={1}>Full-screen retinal review</Text>
                  <Text fontSize="xs" color="text.secondary" noOfLines={1}>{item.display_name} - {item.width} x {item.height}px</Text>
                </Stack>
                {zoomControls(true)}
              </HStack>
            </ModalHeader>
            <ModalCloseButton aria-label="Close full-screen review" />
            <ModalBody p={4} pt={0} display="flex" flexDirection="column" gap={3} overflow="hidden">
              {fullScreenControls && (
                <Box p={2} flexShrink={0} bg="surface.panel" borderWidth="1px" borderColor="border.subtle" borderRadius="md" color="text.primary" maxH={{ base: '88px', tablet: '72px' }} overflowY="auto">
                  <Text fontSize="xs" color="text.secondary" mb={2}>Annotation controls</Text>
                  {fullScreenControls}
                </Box>
              )}
              {viewerViewport(true)}
              {viewerStatus(true)}
            </ModalBody>
          </ModalContent>
        </Modal>
      )}
    </Box>
  );
}
