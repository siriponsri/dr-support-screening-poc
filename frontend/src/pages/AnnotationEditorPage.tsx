import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type MouseEvent as ReactMouseEvent } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Center,
  FormControl,
  FormLabel,
  Grid,
  HStack,
  Input,
  Select,
  SimpleGrid,
  Spinner,
  Stack,
  Text,
  useToast,
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { CaseNavigation } from '@/components/common/CaseNavigation';
import { NextActionHint } from '@/components/common/NextActionHint';
import { ReviewerField } from '@/components/common/ReviewerField';
import { AiRoiPopover } from '@/components/review/AiRoiPopover';
import { displayedLesions } from '@/components/review/lesionPresentation';
import { RetinalCanvas, LESION_COLORS, LESION_SHORT_LABELS, type RectangleResizeHandle } from '@/components/review/RetinalCanvas';
import { EDIT_CONFIRMED_ANNOTATIONS_DIALOG, LEAVE_CASE_DIALOG, useConfirmDialog } from '@/components/common/ConfirmDialog';
import { annotationsConfirmed, caseComplete, formatTimestamp, gradeConfirmed } from '@/lib/caseProgress';
import { loadCaseList, nextIncompleteCaseId } from '@/lib/caseNavigation';
import {
  apiJson,
  humanAnnotationApi,
  lesionReviewApi,
  type AnnotationGeometry,
  type AnnotationType,
  type CaseRecord,
  type HumanAnnotation,
  type LesionLabel,
} from '@/lib/api';
import { ArrowLeft, CheckCircle2, Circle, Lock, MousePointer2, Pentagon, Save, Square, Trash2, Undo2, Unlock } from '@/lib/icons';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';

type Tool = 'select' | 'rectangle' | 'polygon' | 'point' | 'circle';
type Point = [number, number];

const MIN_RESIZE_SIZE = 4;

const LABEL_OPTIONS: Array<{ value: LesionLabel; label: string }> = [
  { value: 'MICROANEURYSM', label: 'Microaneurysm' },
  { value: 'HEMORRHAGE', label: 'Hemorrhage' },
  { value: 'HARD_EXUDATE', label: 'Hard exudate' },
  { value: 'SOFT_EXUDATE', label: 'Soft exudate' },
];

function errorText(err: unknown) {
  return err instanceof Error ? err.message : 'The request could not be completed.';
}

export function pointFromEvent(event: ReactPointerEvent<SVGSVGElement>, item: Pick<CaseRecord, 'width' | 'height'>): Point {
  const bounds = event.currentTarget.getBoundingClientRect();
  // The image and SVG share the transformed stage, so the transformed bounds
  // map pointer coordinates back to the original-image viewBox.
  const clientX = Number.isFinite(event.clientX) ? event.clientX : bounds.left;
  const clientY = Number.isFinite(event.clientY) ? event.clientY : bounds.top;
  return [
    Math.max(0, Math.min(item.width, ((clientX - bounds.left) / Math.max(bounds.width, 1)) * item.width)),
    Math.max(0, Math.min(item.height, ((clientY - bounds.top) / Math.max(bounds.height, 1)) * item.height)),
  ];
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function boundedDelta(delta: Point, minX: number, maxX: number, minY: number, maxY: number): Point {
  return [clamp(delta[0], minX, maxX), clamp(delta[1], minY, maxY)];
}

export function translateAnnotationGeometry(
  annotation: HumanAnnotation,
  delta: Point,
  item: Pick<CaseRecord, 'width' | 'height'>,
): AnnotationGeometry {
  const geometry = annotation.geometry;
  if (annotation.type === 'rectangle' && 'width' in geometry) {
    const [dx, dy] = boundedDelta(delta, -geometry.x, item.width - geometry.x - geometry.width, -geometry.y, item.height - geometry.y - geometry.height);
    return { ...geometry, x: geometry.x + dx, y: geometry.y + dy };
  }
  if (annotation.type === 'polygon' && 'points' in geometry) {
    const minX = Math.min(...geometry.points.map(([x]) => x));
    const maxX = Math.max(...geometry.points.map(([x]) => x));
    const minY = Math.min(...geometry.points.map(([, y]) => y));
    const maxY = Math.max(...geometry.points.map(([, y]) => y));
    const [dx, dy] = boundedDelta(delta, -minX, item.width - maxX, -minY, item.height - maxY);
    return { points: geometry.points.map(([x, y]) => [x + dx, y + dy]) };
  }
  if (annotation.type === 'point' && 'x' in geometry && !('width' in geometry)) {
    const [dx, dy] = boundedDelta(delta, -geometry.x, item.width - geometry.x, -geometry.y, item.height - geometry.y);
    return { x: geometry.x + dx, y: geometry.y + dy };
  }
  if (annotation.type === 'circle' && 'radius' in geometry) {
    const [dx, dy] = boundedDelta(delta, -geometry.cx + geometry.radius, item.width - geometry.cx - geometry.radius, -geometry.cy + geometry.radius, item.height - geometry.cy - geometry.radius);
    return { ...geometry, cx: geometry.cx + dx, cy: geometry.cy + dy };
  }
  return geometry;
}

export function resizeRectangleGeometry(
  annotation: HumanAnnotation,
  handle: RectangleResizeHandle,
  point: Point,
  item: Pick<CaseRecord, 'width' | 'height'>,
): AnnotationGeometry {
  const geometry = annotation.geometry;
  if (annotation.type !== 'rectangle' || !('width' in geometry)) return geometry;

  const minWidth = Math.min(MIN_RESIZE_SIZE, item.width);
  const minHeight = Math.min(MIN_RESIZE_SIZE, item.height);
  let x = geometry.x;
  let y = geometry.y;
  let width = geometry.width;
  let height = geometry.height;

  if (handle.includes('w')) {
    x = clamp(point[0], 0, geometry.x + geometry.width - minWidth);
    width = geometry.x + geometry.width - x;
  } else if (handle.includes('e')) {
    width = clamp(point[0] - geometry.x, minWidth, item.width - geometry.x);
  }
  if (handle.includes('n')) {
    y = clamp(point[1], 0, geometry.y + geometry.height - minHeight);
    height = geometry.y + geometry.height - y;
  } else if (handle.includes('s')) {
    height = clamp(point[1] - geometry.y, minHeight, item.height - geometry.y);
  }

  return { x, y, width, height };
}

type RoiRectangle = [number, number, number, number];

/** Move (handle = null) or resize the in-place ROI correction box in original pixels. */
export function editRoiRectangle(
  base: RoiRectangle,
  handle: RectangleResizeHandle | null,
  start: Point,
  point: Point,
  item: Pick<CaseRecord, 'width' | 'height'>,
): RoiRectangle {
  const asAnnotation = {
    shape_id: 'roi-edit', type: 'rectangle' as const, label: 'MICROANEURYSM' as const, source: 'HUMAN' as const, reviewer: '', created_at: '',
    geometry: { x: base[0], y: base[1], width: base[2] - base[0], height: base[3] - base[1] },
  };
  const geometry = handle
    ? resizeRectangleGeometry(asAnnotation, handle, point, item)
    : translateAnnotationGeometry(asAnnotation, [point[0] - start[0], point[1] - start[1]], item);
  if (!('width' in geometry)) return base;
  return [geometry.x, geometry.y, geometry.x + geometry.width, geometry.y + geometry.height];
}

const ROI_HANDLES: RectangleResizeHandle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
const HANDLE_CURSORS: Record<RectangleResizeHandle, string> = {
  nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize', n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize',
};

function handlePoint(rect: RoiRectangle, handle: RectangleResizeHandle): Point {
  const [x1, y1, x2, y2] = rect;
  const x = handle.includes('w') ? x1 : handle.includes('e') ? x2 : (x1 + x2) / 2;
  const y = handle.includes('n') ? y1 : handle.includes('s') ? y2 : (y1 + y2) / 2;
  return [x, y];
}

function RoiCorrectionBox({ rect, scale }: { rect: RoiRectangle; scale: number }) {
  const [x1, y1, x2, y2] = rect;
  const safeScale = Math.max(scale, 0.01);
  const screenSize = Math.min(x2 - x1, y2 - y1) * safeScale;
  // Small lesions keep only corner handles, sized so the lesion stays visible.
  const compact = screenSize < 44;
  const size = (compact ? 7 : 10) / safeScale;
  const handles = compact ? ROI_HANDLES.filter((handle) => handle.length === 2) : ROI_HANDLES;
  const offset = compact ? size / 2 : 0;
  return (
    <g data-roi-correction="true">
      <rect
        data-roi-edit="body"
        x={x1}
        y={y1}
        width={x2 - x1}
        height={y2 - y1}
        fill="var(--chakra-colors-text-primary)"
        fillOpacity={0.08}
        stroke="var(--chakra-colors-text-primary)"
        strokeWidth={2.5}
        vectorEffect="non-scaling-stroke"
        style={{ cursor: 'move' }}
      />
      {handles.map((handle) => {
        const [hx, hy] = handlePoint(rect, handle);
        // Compact corner handles sit just outside the box instead of over the lesion.
        const x = hx + (handle.includes('w') ? -offset : handle.includes('e') ? offset : 0);
        const y = hy + (handle.includes('n') ? -offset : handle.includes('s') ? offset : 0);
        return (
          <rect
            key={handle}
            data-roi-edit="handle"
            data-roi-handle={handle}
            x={x - size / 2}
            y={y - size / 2}
            width={size}
            height={size}
            fill="var(--chakra-colors-text-inverse)"
            stroke="var(--chakra-colors-text-primary)"
            strokeWidth={1.5}
            vectorEffect="non-scaling-stroke"
            style={{ cursor: HANDLE_CURSORS[handle] }}
          />
        );
      })}
    </g>
  );
}

function sameRectangle(left: RoiRectangle, right: RoiRectangle) {
  return left.every((value, index) => Math.abs(value - right[index]) < 0.01);
}

function annotationLocked(annotation: HumanAnnotation) {
  // Records written before lock persistence have no field and are protected by default.
  return annotation.locked !== false;
}

function makeId() {
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function annotation(type: AnnotationType, label: LesionLabel, geometry: AnnotationGeometry): HumanAnnotation {
  return { shape_id: makeId(), type, label, geometry, locked: false, source: 'HUMAN', reviewer: '', created_at: '' };
}

function previewShape(preview: { type: Tool; geometry: AnnotationGeometry } | null) {
  if (!preview) return null;
  const { type, geometry } = preview;
  const color = 'var(--chakra-colors-text-primary)';
  if (type === 'rectangle' && 'width' in geometry) {
    return <rect x={geometry.x} y={geometry.y} width={geometry.width} height={geometry.height} fill={color} fillOpacity={0.1} stroke={color} strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />;
  }
  if (type === 'circle' && 'radius' in geometry) {
    return <circle cx={geometry.cx} cy={geometry.cy} r={geometry.radius} fill={color} fillOpacity={0.1} stroke={color} strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />;
  }
  if (type === 'point' && 'x' in geometry) {
    return <circle cx={geometry.x} cy={geometry.y} r={8} fill={color} fillOpacity={0.2} stroke={color} strokeWidth={3} vectorEffect="non-scaling-stroke" />;
  }
  if (type === 'polygon' && 'points' in geometry) {
    return <polyline points={geometry.points.map((point) => point.join(',')).join(' ')} fill={color} fillOpacity={0.1} stroke={color} strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />;
  }
  return null;
}

function ToolButton({ tool, active, onClick, children, ariaLabel, isDisabled = false }: { tool?: Tool; active?: boolean; onClick: () => void; children: React.ReactNode; ariaLabel?: string; isDisabled?: boolean }) {
  return <Button size="sm" variant={active ? 'secondary' : 'outline'} onClick={onClick} aria-label={ariaLabel} aria-pressed={active} isDisabled={isDisabled}>{children}</Button>;
}

export function AnnotationEditorPage() {
  const location = useLocation();
  const { pathname } = location;
  const navigate = useNavigate();
  const { imageId } = useParams<{ imageId: string }>();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [draft, setDraft] = useState<HumanAnnotation[]>([]);
  const [history, setHistory] = useState<HumanAnnotation[][]>([]);
  const [tool, setTool] = useState<Tool>('select');
  const [isCoordinateInspector, setIsCoordinateInspector] = useState(false);
  const [label, setLabel] = useState<LesionLabel>('MICROANEURYSM');
  const [reviewer, setReviewer] = useState(() => getDefaultReviewer());
  const [selectedShapeId, setSelectedShapeId] = useState<string | null>(null);
  const [selectedLesionId, setSelectedLesionId] = useState<string | null>(null);
  const [polygonPoints, setPolygonPoints] = useState<Point[]>([]);
  const [dragStart, setDragStart] = useState<Point | null>(null);
  const [preview, setPreview] = useState<{ type: Tool; geometry: AnnotationGeometry } | null>(null);
  const [showAi, setShowAi] = useState(true);
  const [showHuman, setShowHuman] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [draftStatus, setDraftStatus] = useState<'saved' | 'unsaved' | 'saving' | 'failed'>('saved');
  const [useAsDefault, setUseAsDefault] = useState(() => Boolean(getDefaultReviewer()));
  const [editingConfirmed, setEditingConfirmed] = useState(false);
  const [roiEdit, setRoiEdit] = useState<{ detectionId: string; label: LesionLabel; rect: RoiRectangle } | null>(null);
  const [roiSaving, setRoiSaving] = useState(false);
  const [roiError, setRoiError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);
  const [confirmDialog, confirm] = useConfirmDialog();
  const toast = useToast();
  const roiDragRef = useRef<{ handle: RectangleResizeHandle | null; start: Point; base: RoiRectangle; moved: boolean } | null>(null);
  const interactionRef = useRef(false);
  const skipAutosaveRef = useRef(true);
  const draftRef = useRef<HumanAnnotation[]>(draft);
  const shapeDragRef = useRef<{
    shapeId: string;
    start: Point;
    beforeDraft: HumanAnnotation[];
    moved: boolean;
  } | null>(null);
  const resizeRef = useRef<{
    shapeId: string;
    handle: RectangleResizeHandle;
    beforeDraft: HumanAnnotation[];
    moved: boolean;
  } | null>(null);
  draftRef.current = draft;

  const loadCase = useCallback(async () => {
    if (!imageId) return;
    setLoading(true);
    setError(null);
    try {
      const loaded = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(imageId)}`);
      setItem(loaded);
      setDraft(loaded.human_annotations ?? []);
      setHistory([]);
      setDraftStatus('saved');
      setEditingConfirmed(false);
      setSelectedLesionId(null);
      setRoiEdit(null);
      setRoiError(null);
      skipAutosaveRef.current = true;
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [imageId]);

  useEffect(() => { void loadCase(); }, [loadCase]);

  const annotationConfirmed = annotationsConfirmed(item);
  const hasConfirmedGrade = gradeConfirmed(item);
  const readOnly = Boolean(annotationConfirmed && !editingConfirmed);

  const commit = (next: HumanAnnotation[], nextSelection: string | null = null) => {
    if (readOnly) return;
    setHistory((previous) => [...previous, draftRef.current]);
    draftRef.current = next;
    setDraft(next);
    setSelectedShapeId(nextSelection);
    setSaved(false);
    setDraftStatus('unsaved');
  };

  const activateTool = (nextTool: Tool) => {
    if (readOnly) return;
    if (tool === 'polygon' && polygonPoints.length >= 3) {
      commit([...draft, annotation('polygon', label, { points: polygonPoints })]);
      setPolygonPoints([]);
    }
    setDragStart(null);
    setPreview(null);
    setTool(nextTool);
  };

  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    const roiTarget = event.target instanceof Element ? event.target.closest('[data-roi-edit]') : null;
    if (roiTarget && roiEdit && item && !readOnly) {
      event.preventDefault();
      roiDragRef.current = {
        handle: (roiTarget.getAttribute('data-roi-handle') as RectangleResizeHandle | null) ?? null,
        start: pointFromEvent(event, item),
        base: roiEdit.rect,
        moved: false,
      };
      interactionRef.current = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      return;
    }
    if (readOnly || !item || tool === 'select') return;
    event.preventDefault();
    interactionRef.current = true;
    const point = pointFromEvent(event, item);
    if (tool === 'point') {
      commit([...draft, annotation('point', label, { x: point[0], y: point[1] })]);
      return;
    }
    if (tool === 'polygon') {
      setPolygonPoints((points) => [...points, point]);
      return;
    }
    setDragStart(point);
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const onHumanPointerDown = (shapeId: string, event: ReactPointerEvent<SVGSVGElement>) => {
    if (readOnly || !item) return;
    const selected = draftRef.current.find((entry) => entry.shape_id === shapeId);
    event.preventDefault();
    if (!selected || annotationLocked(selected)) return;
    shapeDragRef.current = {
      shapeId,
      start: pointFromEvent(event, item),
      beforeDraft: draftRef.current,
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const onHumanResizeStart = (shapeId: string, handle: RectangleResizeHandle, event: ReactPointerEvent<SVGSVGElement>) => {
    event.preventDefault();
    if (readOnly || !item) return;
    const selected = draftRef.current.find((entry) => entry.shape_id === shapeId);
    if (!selected || selected.type !== 'rectangle' || annotationLocked(selected)) return;
    resizeRef.current = {
      shapeId,
      handle,
      beforeDraft: draftRef.current,
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (readOnly || !item) return;
    const roiDrag = roiDragRef.current;
    if (roiDrag) {
      const next = editRoiRectangle(roiDrag.base, roiDrag.handle, roiDrag.start, pointFromEvent(event, item), item);
      roiDrag.moved = roiDrag.moved || !sameRectangle(next, roiDrag.base);
      setRoiEdit((current) => current ? { ...current, rect: next } : current);
      event.preventDefault();
      return;
    }
    const resize = resizeRef.current;
    if (resize) {
      const point = pointFromEvent(event, item);
      const base = resize.beforeDraft.find((entry) => entry.shape_id === resize.shapeId);
      if (base) {
        const next = draftRef.current.map((entry) => entry.shape_id === resize.shapeId
          ? { ...entry, geometry: resizeRectangleGeometry(base, resize.handle, point, item) }
          : entry);
        resize.moved = JSON.stringify(next) !== JSON.stringify(draftRef.current);
        draftRef.current = next;
        setDraft(next);
        setSaved(false);
        setDraftStatus('unsaved');
        event.preventDefault();
      }
      return;
    }
    const shapeDrag = shapeDragRef.current;
    if (shapeDrag) {
      const point = pointFromEvent(event, item);
      const delta: Point = [point[0] - shapeDrag.start[0], point[1] - shapeDrag.start[1]];
      const current = draftRef.current;
      const next = current.map((entry) => entry.shape_id === shapeDrag.shapeId
        ? { ...entry, geometry: translateAnnotationGeometry(shapeDrag.beforeDraft.find((candidate) => candidate.shape_id === shapeDrag.shapeId) ?? entry, delta, item) }
        : entry);
      shapeDrag.moved = JSON.stringify(next) !== JSON.stringify(current);
      draftRef.current = next;
      setDraft(next);
      setSaved(false);
      setDraftStatus('unsaved');
      event.preventDefault();
      return;
    }
    if (!dragStart || (tool !== 'rectangle' && tool !== 'circle')) return;
    const point = pointFromEvent(event, item);
    if (tool === 'rectangle') {
      setPreview({ type: tool, geometry: { x: Math.min(dragStart[0], point[0]), y: Math.min(dragStart[1], point[1]), width: Math.abs(point[0] - dragStart[0]), height: Math.abs(point[1] - dragStart[1]) } });
    } else {
      setPreview({ type: tool, geometry: { cx: dragStart[0], cy: dragStart[1], radius: Math.hypot(point[0] - dragStart[0], point[1] - dragStart[1]) } });
    }
  };

  const onPointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (readOnly) return;
    if (roiDragRef.current) {
      roiDragRef.current = null;
      interactionRef.current = false;
      event.currentTarget.releasePointerCapture?.(event.pointerId);
      event.preventDefault();
      return;
    }
    const resize = resizeRef.current;
    if (resize) {
      if (resize.moved) {
        setHistory((previous) => [...previous, resize.beforeDraft]);
        setSelectedShapeId(resize.shapeId);
      }
      resizeRef.current = null;
      interactionRef.current = false;
      if (resize.moved) setDraftStatus('unsaved');
      event.currentTarget.releasePointerCapture?.(event.pointerId);
      event.preventDefault();
      return;
    }
    const shapeDrag = shapeDragRef.current;
    if (shapeDrag) {
      if (shapeDrag.moved) {
        setHistory((previous) => [...previous, shapeDrag.beforeDraft]);
        setSelectedShapeId(shapeDrag.shapeId);
      }
      shapeDragRef.current = null;
      interactionRef.current = false;
      if (shapeDrag.moved) setDraftStatus('unsaved');
      event.currentTarget.releasePointerCapture?.(event.pointerId);
      event.preventDefault();
      return;
    }
    if (!item || !dragStart || (tool !== 'rectangle' && tool !== 'circle')) return;
    const point = pointFromEvent(event, item);
    let geometry: AnnotationGeometry;
    if (tool === 'rectangle') {
      geometry = { x: Math.min(dragStart[0], point[0]), y: Math.min(dragStart[1], point[1]), width: Math.abs(point[0] - dragStart[0]), height: Math.abs(point[1] - dragStart[1]) };
      if (geometry.width < 2 || geometry.height < 2) { setDragStart(null); setPreview(null); return; }
    } else {
      geometry = { cx: dragStart[0], cy: dragStart[1], radius: Math.hypot(point[0] - dragStart[0], point[1] - dragStart[1]) };
      if (geometry.radius < 2) { setDragStart(null); setPreview(null); return; }
    }
    commit([...draft, annotation(tool, label, geometry)]);
    setDragStart(null);
    setPreview(null);
    interactionRef.current = false;
  };

  const onPointerCancel = () => {
    const roiDrag = roiDragRef.current;
    if (roiDrag) {
      setRoiEdit((current) => current ? { ...current, rect: roiDrag.base } : current);
      roiDragRef.current = null;
    }
    const resize = resizeRef.current;
    if (resize) {
      draftRef.current = resize.beforeDraft;
      setDraft(resize.beforeDraft);
      resizeRef.current = null;
    }
    const shapeDrag = shapeDragRef.current;
    if (shapeDrag) {
      draftRef.current = shapeDrag.beforeDraft;
      setDraft(shapeDrag.beforeDraft);
      shapeDragRef.current = null;
    }
    setDragStart(null);
    setPreview(null);
    interactionRef.current = false;
  };

  const onDoubleClick = (event: ReactMouseEvent<SVGSVGElement>) => {
    if (readOnly || tool !== 'polygon') return;
    event.preventDefault();
    if (polygonPoints.length < 3) return;
    commit([...draft, annotation('polygon', label, { points: polygonPoints })]);
    setPolygonPoints([]);
  };

  const undo = () => {
    if (readOnly) return;
    const previous = history.at(-1);
    if (!previous) return;
    draftRef.current = previous;
    setDraft(previous);
    setHistory((entries) => entries.slice(0, -1));
    setSelectedShapeId(null);
    setSaved(false);
    setDraftStatus('unsaved');
  };

  const deleteSelected = () => {
    if (readOnly) return;
    if (!selectedShapeId) return;
    commit(draftRef.current.filter((entry) => entry.shape_id !== selectedShapeId));
  };

  const toggleSelectedLock = () => {
    if (readOnly) return;
    if (!selectedShapeId) return;
    const selected = draftRef.current.find((entry) => entry.shape_id === selectedShapeId);
    if (!selected) return;
    commit(draftRef.current.map((entry) => entry.shape_id === selectedShapeId
      ? { ...entry, locked: !annotationLocked(entry) }
      : entry), selectedShapeId);
  };

  const moveSelectedByKeyboard = (shortcut: string) => {
    if (readOnly || !item || !selectedShapeId) return;
    const selected = draftRef.current.find((entry) => entry.shape_id === selectedShapeId);
    if (!selected || annotationLocked(selected)) return;
    const step = 1;
    const delta: Point = [shortcut === 'arrowleft' ? -step : shortcut === 'arrowright' ? step : 0,
      shortcut === 'arrowup' ? -step : shortcut === 'arrowdown' ? step : 0];
    const next = draftRef.current.map((entry) => entry.shape_id === selectedShapeId
      ? { ...entry, geometry: translateAnnotationGeometry(entry, delta, item) }
      : entry);
    commit(next, selectedShapeId);
  };

  const onShortcut = (shortcut: string) => {
    if (shortcut === 'v') activateTool('select');
    else if (shortcut === 'b') activateTool('rectangle');
    else if (shortcut === 'escape') {
      setPolygonPoints([]);
      setDragStart(null);
      setPreview(null);
      setSelectedShapeId(null);
      clearRoiSelection();
      setTool('select');
    } else if (shortcut === 'l') toggleSelectedLock();
    else if (shortcut.startsWith('arrow')) moveSelectedByKeyboard(shortcut);
  };

  const onCoordinateInspectorChange = (active: boolean) => {
    setIsCoordinateInspector(active);
    setPolygonPoints([]);
    setDragStart(null);
    setPreview(null);
    setTool('select');
  };

  const selectedAnnotation = selectedShapeId
    ? draftRef.current.find((entry) => entry.shape_id === selectedShapeId) ?? null
    : null;
  const selectedIsLocked = selectedAnnotation ? annotationLocked(selectedAnnotation) : false;
  const annotationNeedsConfirmation = item?.annotation_confirmation_status !== 'CONFIRMED' || draftStatus !== 'saved';

  const changeSelectedLabel = (nextLabel: LesionLabel) => {
    if (readOnly || !selectedAnnotation || annotationLocked(selectedAnnotation) || selectedAnnotation.label === nextLabel) return;
    commit(draftRef.current.map((entry) => entry.shape_id === selectedShapeId
      ? { ...entry, label: nextLabel }
      : entry), selectedShapeId);
  };

  const onHumanAnnotationDerived = (savedCase: CaseRecord) => {
    const nextDraft = savedCase.human_annotations ?? [];
    setItem(savedCase);
    draftRef.current = nextDraft;
    setDraft(nextDraft);
    setHistory([]);
    setSelectedShapeId(null);
    setSelectedLesionId(null);
    setShowHuman(true);
    setTool('select');
    setSaved(true);
    setDraftStatus('saved');
  };

  const clearRoiSelection = () => {
    setSelectedLesionId(null);
    setRoiEdit(null);
    setRoiError(null);
    roiDragRef.current = null;
  };

  const beginAnnotationEdit = async (): Promise<boolean> => {
    if (!annotationConfirmed || editingConfirmed) return true;
    if (!(await confirm(EDIT_CONFIRMED_ANNOTATIONS_DIALOG))) return false;
    setEditingConfirmed(true);
    setSaveError(null);
    return true;
  };

  const selectLesion = async (detectionId: string) => {
    if (!item) return;
    if (readOnly && !(await beginAnnotationEdit())) return;
    const lesion = displayedLesions(item).find((entry) => entry.detection_id === detectionId);
    if (!lesion) return;
    setSelectedShapeId(null);
    setSelectedLesionId(detectionId);
    setRoiError(null);
    setRoiEdit({ detectionId, label: lesion.canonical_label as LesionLabel, rect: [...lesion.rectangle] as RoiRectangle });
  };

  const selectedLesion = item && selectedLesionId
    ? displayedLesions(item).find((entry) => entry.detection_id === selectedLesionId) ?? null
    : null;
  const rawSelectedLesion = item && selectedLesionId
    ? (item.lesion_review?.lesions ?? item.lesion?.lesions ?? []).find((entry) => entry.detection_id === selectedLesionId) ?? null
    : null;
  const roiGeometryChanged = Boolean(roiEdit && rawSelectedLesion && !sameRectangle(roiEdit.rect, rawSelectedLesion.rectangle));

  const roiReviewer = () => reviewer.trim();

  /** Flush any pending draft so ROI decisions never race the autosave revision. */
  const flushedCase = async (): Promise<CaseRecord | null> => {
    if (!item) return null;
    if (draftStatus === 'saved') return item;
    return persistDraft();
  };

  const confirmRoi = async () => {
    if (!item || !roiEdit || !rawSelectedLesion || roiSaving) return;
    const reviewerName = roiReviewer();
    if (!reviewerName) { setRoiError('Enter a reviewer name before confirming.'); return; }
    const [x1, y1, x2, y2] = roiEdit.rect;
    if (x1 < 0 || y1 < 0 || x2 <= x1 || y2 <= y1) { setRoiError('ROI geometry must have positive width and height.'); return; }
    setRoiSaving(true);
    setRoiError(null);
    try {
      const base = await flushedCase();
      if (!base) throw new Error('The annotation draft could not be saved. Try again.');
      const corrected = roiEdit.label !== rawSelectedLesion.canonical_label || roiGeometryChanged;
      const reviewed = await lesionReviewApi.review(base.image_id, {
        revision: base.revision,
        reviewer: reviewerName,
        detection_id: roiEdit.detectionId,
        action: corrected ? 'CORRECT' : 'CONFIRM',
        label: corrected ? roiEdit.label : undefined,
        rectangle: corrected ? roiEdit.rect : undefined,
      });
      const linked = (reviewed.human_annotations ?? []).find((entry) => entry.source_detection_id === roiEdit.detectionId);
      if (linked) {
        // A human annotation already derives from this ROI: update it in place
        // through the normal draft path (autosaved) instead of duplicating it.
        const geometry = { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
        setItem(reviewed);
        const nextDraft = (reviewed.human_annotations ?? []).map((entry) => entry.shape_id === linked.shape_id
          ? { ...entry, label: roiEdit.label, geometry }
          : entry);
        const changed = JSON.stringify(nextDraft) !== JSON.stringify(reviewed.human_annotations ?? []);
        draftRef.current = nextDraft;
        setDraft(nextDraft);
        setHistory([]);
        setDraftStatus(changed ? 'unsaved' : 'saved');
      } else {
        const derived = await humanAnnotationApi.deriveFromAi(base.image_id, {
          revision: reviewed.revision,
          reviewer: reviewerName,
          detection_id: roiEdit.detectionId,
          intent: corrected ? 'CORRECT_AS_HUMAN' : 'USE_AS_HUMAN',
        });
        onHumanAnnotationDerived(derived);
      }
      clearRoiSelection();
      toast({ id: 'roi-confirmed', status: 'success', title: 'Annotation confirmed', duration: 2000, position: 'bottom' });
    } catch (err) {
      setRoiError(errorText(err));
    } finally {
      setRoiSaving(false);
    }
  };

  const removeRoi = async () => {
    if (!item || !roiEdit || roiSaving) return;
    const reviewerName = roiReviewer();
    if (!reviewerName) { setRoiError('Enter a reviewer name before removing.'); return; }
    setRoiSaving(true);
    setRoiError(null);
    try {
      const base = await flushedCase();
      if (!base) throw new Error('The annotation draft could not be saved. Try again.');
      const saved = await lesionReviewApi.review(base.image_id, {
        revision: base.revision,
        reviewer: reviewerName,
        detection_id: roiEdit.detectionId,
        action: 'REJECT',
      });
      setItem(saved);
      const nextDraft = (saved.human_annotations ?? []).filter((entry) => entry.source_detection_id !== roiEdit.detectionId);
      draftRef.current = nextDraft;
      setDraft(nextDraft);
      setHistory([]);
      setDraftStatus(nextDraft.length !== (saved.human_annotations ?? []).length ? 'unsaved' : 'saved');
      clearRoiSelection();
      toast({ id: 'roi-removed', status: 'success', title: 'AI suggestion removed', duration: 2500, position: 'bottom' });
    } catch (err) {
      setRoiError(errorText(err));
    } finally {
      setRoiSaving(false);
    }
  };

  const annotationControls = (
    <Stack spacing={3}>
      <HStack spacing={2} flexWrap="wrap">
          <ToolButton active={tool === 'select'} onClick={() => activateTool('select')} isDisabled={isCoordinateInspector || readOnly}><MousePointer2 size={14} /> Select</ToolButton>
        <ToolButton active={tool === 'rectangle'} onClick={() => activateTool('rectangle')} isDisabled={isCoordinateInspector || readOnly}><Square size={14} /> Box</ToolButton>
        <ToolButton active={tool === 'polygon'} onClick={() => activateTool('polygon')} isDisabled={isCoordinateInspector || readOnly}><Pentagon size={14} /> Polygon</ToolButton>
        <ToolButton active={tool === 'point'} onClick={() => activateTool('point')} isDisabled={isCoordinateInspector || readOnly}><Circle size={14} /> Point</ToolButton>
        <ToolButton active={tool === 'circle'} onClick={() => activateTool('circle')} isDisabled={isCoordinateInspector || readOnly}><Circle size={14} /> Circle</ToolButton>
      </HStack>
      <HStack spacing={2}>
        <Button size="sm" leftIcon={<Undo2 size={14} />} onClick={undo} isDisabled={isCoordinateInspector || readOnly || history.length === 0}>Undo</Button>
        <Button size="sm" leftIcon={<Trash2 size={14} />} onClick={deleteSelected} isDisabled={isCoordinateInspector || readOnly || !selectedShapeId}>Delete selected</Button>
        <Button
          size="sm"
          leftIcon={selectedIsLocked ? <Unlock size={14} /> : <Lock size={14} />}
          onClick={toggleSelectedLock}
          isDisabled={isCoordinateInspector || readOnly || !selectedAnnotation}
          aria-label={selectedIsLocked ? 'Unlock selected human annotation' : 'Lock selected human annotation'}
        >
          {selectedIsLocked ? 'Unlock selected' : 'Lock selected'}
        </Button>
      </HStack>
      <HStack spacing={4} align="end" flexWrap="wrap">
        <FormControl maxW={{ base: '100%', laptop: '250px' }}>
          <FormLabel htmlFor="new-annotation-class" fontSize="sm">New annotation class</FormLabel>
          <Select id="new-annotation-class" value={label} onChange={(event) => setLabel(event.target.value as LesionLabel)} isDisabled={readOnly}>
            {LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </Select>
        </FormControl>
        {selectedAnnotation && (
          <FormControl maxW={{ base: '100%', laptop: '250px' }}>
            <FormLabel htmlFor="selected-annotation-class" fontSize="sm">Selected annotation class</FormLabel>
            <Select id="selected-annotation-class" value={selectedAnnotation.label} onChange={(event) => changeSelectedLabel(event.target.value as LesionLabel)} isDisabled={selectedIsLocked || readOnly}>
              {LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </Select>
          </FormControl>
        )}
        <HStack spacing={3} flexWrap="wrap" fontSize="sm">
          <HStack spacing={2}>
            <Text>AI suggestions</Text>
            <Button size="sm" variant={showAi ? 'secondary' : 'outline'} onClick={() => setShowAi((visible) => !visible)}>{showAi ? 'Shown' : 'Hidden'}</Button>
          </HStack>
          <HStack spacing={2}>
            <Text>Human annotations</Text>
            <Button size="sm" variant={showHuman ? 'secondary' : 'outline'} onClick={() => setShowHuman((visible) => !visible)}>{showHuman ? 'Shown' : 'Hidden'}</Button>
          </HStack>
        </HStack>
      </HStack>
    </Stack>
  );

  const fullScreenAnnotationControls = (
    <HStack spacing={1} flexWrap="wrap" align="center">
      <ToolButton ariaLabel="Select tool" active={tool === 'select'} onClick={() => activateTool('select')} isDisabled={isCoordinateInspector || readOnly}>
        <MousePointer2 size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Select</Box>
      </ToolButton>
      <ToolButton ariaLabel="Box tool" active={tool === 'rectangle'} onClick={() => activateTool('rectangle')} isDisabled={isCoordinateInspector || readOnly}>
        <Square size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Box</Box>
      </ToolButton>
      <ToolButton ariaLabel="Polygon tool" active={tool === 'polygon'} onClick={() => activateTool('polygon')} isDisabled={isCoordinateInspector || readOnly}>
        <Pentagon size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Polygon</Box>
      </ToolButton>
      <ToolButton ariaLabel="Point tool" active={tool === 'point'} onClick={() => activateTool('point')} isDisabled={isCoordinateInspector || readOnly}>
        <Circle size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Point</Box>
      </ToolButton>
      <ToolButton ariaLabel="Circle tool" active={tool === 'circle'} onClick={() => activateTool('circle')} isDisabled={isCoordinateInspector || readOnly}>
        <Circle size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Circle</Box>
      </ToolButton>
      <Button size="sm" leftIcon={<Undo2 size={14} />} aria-label="Undo annotation change" onClick={undo} isDisabled={isCoordinateInspector || readOnly || history.length === 0}>Undo</Button>
      <Button size="sm" leftIcon={<Trash2 size={14} />} aria-label="Delete selected annotation" onClick={deleteSelected} isDisabled={isCoordinateInspector || readOnly || !selectedShapeId}>Delete</Button>
      <Button size="sm" leftIcon={selectedIsLocked ? <Unlock size={14} /> : <Lock size={14} />} onClick={toggleSelectedLock} isDisabled={isCoordinateInspector || readOnly || !selectedAnnotation} aria-label={selectedIsLocked ? 'Unlock selected human annotation' : 'Lock selected human annotation'}>
        {selectedIsLocked ? 'Unlock' : 'Lock'}
      </Button>
      <Select aria-label="Lesion class" size="sm" value={label} onChange={(event) => setLabel(event.target.value as LesionLabel)} maxW={{ base: '150px', tablet: '190px' }} isDisabled={readOnly}>
        {LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </Select>
      <Button size="sm" variant={showAi ? 'secondary' : 'outline'} onClick={() => setShowAi((visible) => !visible)} aria-pressed={showAi}>AI {showAi ? 'on' : 'off'}</Button>
      <Button size="sm" variant={showHuman ? 'secondary' : 'outline'} onClick={() => setShowHuman((visible) => !visible)} aria-pressed={showHuman}>Human {showHuman ? 'on' : 'off'}</Button>
    </HStack>
  );

  const persistDraft = async (): Promise<CaseRecord | null> => {
    if (!item || saving) return null;
    if (draftStatus === 'saved') return item;
    if (!reviewer.trim()) {
      setSaveError('Reviewer name is required to save annotation changes.');
      return null;
    }
    setSaving(true);
    setDraftStatus('saving');
    setSaveError(null);
    try {
      const savedCase = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(item.image_id)}/annotations`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          revision: item.revision,
          reviewer: reviewer.trim(),
          annotations: draftRef.current.map(({ shape_id, type, label: entryLabel, geometry, locked, source_detection_id }) => ({
            shape_id,
            type,
            label: entryLabel,
            geometry,
            locked: locked !== false,
            source_detection_id,
          })),
        }),
      });
      setItem(savedCase);
      draftRef.current = savedCase.human_annotations ?? [];
      setDraft(draftRef.current);
      setHistory([]);
      setSaved(true);
      setDraftStatus('saved');
      setDefaultReviewer(useAsDefault ? reviewer : '');
      return savedCase;
    } catch (err) {
      setSaveError(errorText(err));
      setDraftStatus('failed');
      return null;
    } finally {
      setSaving(false);
    }
  };

  const confirmAnnotations = async (): Promise<boolean> => {
    if (!item) return false;
    if (!reviewer.trim()) {
      setSaveError('Reviewer name is required to confirm annotations.');
      return false;
    }
    const imageId = item.image_id;
    const persisted = await persistDraft();
    if (!persisted) return false;
    setSaving(true);
    try {
      const confirmed = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(imageId)}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: persisted.revision, action: 'CONFIRM_ANNOTATIONS', reviewer: reviewer.trim(), grade: null, comment: '' }),
      });
      setItem(confirmed);
      setSaved(true);
      setDraftStatus('saved');
      return true;
    } catch (err) {
      setSaveError(errorText(err));
      setDraftStatus('failed');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const draftStatusText = draftStatus === 'saving' ? 'Saving...'
    : draftStatus === 'failed' ? 'Save failed'
      : draftStatus === 'unsaved' ? (reviewer.trim() ? 'Saving...' : 'Enter a reviewer name to save')
        : 'Draft saved';

  const guarded = Boolean(item && (!caseComplete(item) || draftStatus !== 'saved' || editingConfirmed));

  const leaveToWorklist = async () => {
    if (guarded && !(await confirm(LEAVE_CASE_DIALOG))) return;
    if (draftStatus !== 'saved') await persistDraft();
    navigate('/worklist');
  };

  const openNextImage = async (completedId: string) => {
    const nextId = nextIncompleteCaseId(await loadCaseList(), completedId);
    navigate('/worklist', { state: { caseComplete: completedId, openConfirmImage: nextId } });
    return nextId;
  };

  /** Confirm Annotation finishes this image and opens the next Worklist image. */
  const completeCase = async () => {
    if (!item || completing) return;
    setCompleting(true);
    try {
      if (!(await confirmAnnotations())) return;
      clearRoiSelection();
      const nextId = nextIncompleteCaseId(await loadCaseList(), item.image_id);
      toast({
        id: 'case-complete',
        status: 'success',
        title: nextId ? 'Case complete · Opening next image' : 'Case complete · Every Worklist image is complete',
        duration: 3500,
        position: 'top',
        isClosable: true,
      });
      navigate('/worklist', { state: { caseComplete: item.image_id, openConfirmImage: nextId } });
    } finally {
      setCompleting(false);
    }
  };

  useEffect(() => {
    if (skipAutosaveRef.current) {
      skipAutosaveRef.current = false;
      return;
    }
    if (draftStatus !== 'unsaved' || interactionRef.current || !reviewer.trim()) return;
    const timer = window.setTimeout(() => { void persistDraft(); }, 900);
    return () => window.clearTimeout(timer);
  }, [draft, draftStatus, reviewer]);

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (draftStatus === 'unsaved' || draftStatus === 'saving' || draftStatus === 'failed') {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [draftStatus]);

  if (!imageId) return <Center minH="360px"><Text>Select an image from the Worklist.</Text></Center>;
  if (loading && !item) return <Center minH="360px"><Spinner color="action.primary" /></Center>;
  if (error || !item) {
    return <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={6}><Alert status="error"><AlertIcon /><Text>{error ?? 'Case unavailable.'}</Text></Alert><Button mt={4} onClick={() => navigate('/worklist')}>Back to Worklist</Button></Box>;
  }

  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader
        pathname={pathname}
        title="Annotation Editor"
        subtitle={`${item.display_name} - human annotations are separate from AI suggestions`}
        actions={<HStack><Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} leftIcon={<ArrowLeft size={15} />} variant="ghost">Back to Review</Button><Button onClick={() => void leaveToWorklist()}>Back to Worklist</Button></HStack>}
      />
      <HStack mb={3} spacing={2} fontSize="sm" aria-label="DR grade status" color={hasConfirmedGrade ? 'text.secondary' : 'status.warning'}>
        {hasConfirmedGrade ? <CheckCircle2 size={16} color="var(--chakra-colors-status-success)" /> : null}
        <Text>{hasConfirmedGrade ? `DR grade confirmed · Grade ${item.clinician_review?.final_grade}` : 'DR grade not confirmed'}</Text>
      </HStack>
      {Boolean((location.state as { gradingComplete?: boolean } | null)?.gradingComplete) && hasConfirmedGrade && (
        <Alert status="success" mb={4}><AlertIcon /><Text><strong>Grading complete.</strong> Correct AI regions only where you disagree, then Confirm Annotation to finish this image.</Text></Alert>
      )}
      {!hasConfirmedGrade && (
        <Alert status="warning" mb={4}>
          <AlertIcon />
          <Stack spacing={2}>
            <Text><strong>Confirm the DR grade first.</strong> Annotation review follows Clinician Review for this image. Your annotation draft is kept.</Text>
            <Button as={Link} to={`/clinician-review/${encodeURIComponent(item.image_id)}`} size="sm" variant="outline" alignSelf="flex-start">Open Clinician Review</Button>
          </Stack>
        </Alert>
      )}
      {readOnly && (
        <Alert status="info" mb={4}>
          <AlertIcon />
          <Stack spacing={1}>
            <Text fontWeight="semibold">Annotations confirmed</Text>
            <Text fontSize="sm">Reviewer: {item.annotation_confirmation?.reviewer ?? 'Not recorded'}</Text>
            <Text fontSize="sm">Confirmed at: {formatTimestamp(item.annotation_confirmation?.timestamp)}</Text>
          </Stack>
        </Alert>
      )}
      <Stack spacing={3} mb={5}>
        <CaseNavigation
          imageId={item.image_id}
          guarded={guarded}
          confirm={confirm}
          onBeforeSwitch={async () => { if (draftStatus !== 'saved') await persistDraft(); }}
        />
        <NextActionHint item={item} />
      </Stack>
      <Grid templateColumns={{ base: '1fr', laptop: 'minmax(0, 1.4fr) minmax(300px, 0.6fr)' }} gap={5} alignItems="start">
        <Section title="Retinal annotation canvas" description="Coordinates are stored in original image pixel space. Double-click to finish a polygon.">
          <RetinalCanvas
            item={item}
            showAi={showAi}
            showHuman={showHuman}
            humanAnnotations={draft}
            selectedShapeId={selectedShapeId}
            selectedLesionId={selectedLesionId}
            onSelectLesion={(detectionId) => { void selectLesion(detectionId); }}
            onSelectHuman={(shapeId) => { setSelectedShapeId(shapeId); clearRoiSelection(); }}
            renderOverlay={(context) => (selectedLesion && roiEdit && !readOnly ? (
              <AiRoiPopover
                item={item}
                lesion={selectedLesion}
                context={context}
                label={roiEdit.label}
                rectangle={roiEdit.rect}
                geometryChanged={roiGeometryChanged}
                saving={roiSaving}
                error={roiError}
                onLabelChange={(nextLabel) => setRoiEdit((current) => current ? { ...current, label: nextLabel } : current)}
                onConfirm={() => void confirmRoi()}
                onRemove={() => void removeRoi()}
                onClose={clearRoiSelection}
              />
            ) : null)}
            onHumanPointerDown={onHumanPointerDown}
            onHumanResizeStart={onHumanResizeStart}
            onCoordinateInspectorChange={onCoordinateInspectorChange}
            onShortcut={onShortcut}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerCancel}
            onDoubleClick={onDoubleClick}
            fullScreenControls={fullScreenAnnotationControls}
            renderInStage={(scale) => (roiEdit && !readOnly ? <RoiCorrectionBox rect={roiEdit.rect} scale={scale} /> : null)}
          >
            {polygonPoints.length > 0 && <polyline points={polygonPoints.map((point) => point.join(',')).join(' ')} fill="var(--chakra-colors-text-primary)" fillOpacity={0.1} stroke="var(--chakra-colors-text-primary)" strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />}
            {previewShape(preview)}
          </RetinalCanvas>
          <HStack mt={4} spacing={3} flexWrap="wrap" fontSize="sm">
            <Text fontWeight="semibold">{draft.length} human annotation{draft.length === 1 ? '' : 's'}</Text>
            <Text aria-live="polite" color={draftStatus === 'failed' ? 'status.danger' : 'text.secondary'}>{draftStatusText}</Text>
            {!readOnly && <Button size="xs" variant="ghost" leftIcon={<Save size={12} />} onClick={() => void persistDraft()} isDisabled={saving || draftStatus === 'saved'}>Save draft</Button>}
          </HStack>
        </Section>
        <Stack spacing={5}>
          <Section title="Finish this image" description="Confirming annotations completes this case and opens the next Worklist image.">
            <Stack spacing={3}>
              <Stack spacing={1} fontSize="sm" color="text.secondary">
                <Text>AI suggestions are optional visual evidence.</Text>
                <Text>You only need to edit a region when you disagree or want to record a human annotation.</Text>
                <Text>Confirming annotations completes this case; it does not mean every AI ROI was individually verified.</Text>
              </Stack>
              <ReviewerField id="annotation-reviewer" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />
              {saveError && <Alert status="error"><AlertIcon /><Text fontSize="sm">{saveError}</Text></Alert>}
              {readOnly ? (
                <HStack spacing={2} flexWrap="wrap">
                  <Button variant="solid" onClick={() => void openNextImage(item.image_id)}>Open next image</Button>
                  <Button variant="outline" onClick={() => void beginAnnotationEdit()}>Edit confirmed annotations</Button>
                </HStack>
              ) : (
                <Button variant="solid" onClick={() => void completeCase()} isLoading={completing || saving} loadingText="Confirming" isDisabled={!hasConfirmedGrade || roiSaving}>Confirm Annotation</Button>
              )}
            </Stack>
          </Section>
          <Section title="Editor tools" description="Optional: draw or edit human annotations. Select a tool, choose a lesion class, then draw.">
            {annotationControls}
          </Section>
          <SimpleGrid columns={2} spacing={3} fontSize="sm">
            {LABEL_OPTIONS.map((option) => <HStack key={option.value} spacing={2}><Box w="10px" h="10px" borderRadius="sm" bg={LESION_COLORS[option.value]} /><Text>{LESION_SHORT_LABELS[option.value]} - {option.label}</Text></HStack>)}
          </SimpleGrid>
        </Stack>
      </Grid>
      {confirmDialog}
    </Box>
  );
}
