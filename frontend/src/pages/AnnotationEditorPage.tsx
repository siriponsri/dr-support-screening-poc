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
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { RetinalCanvas, LESION_COLORS, LESION_SHORT_LABELS, type RectangleResizeHandle } from '@/components/review/RetinalCanvas';
import {
  apiJson,
  type AnnotationGeometry,
  type AnnotationType,
  type CaseRecord,
  type HumanAnnotation,
  type LesionLabel,
} from '@/lib/api';
import { ArrowLeft, Circle, Lock, MousePointer2, Pentagon, Save, Square, Trash2, Undo2, Unlock } from '@/lib/icons';
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
  const { pathname } = useLocation();
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
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [imageId]);

  useEffect(() => { void loadCase(); }, [loadCase]);

  const commit = (next: HumanAnnotation[], nextSelection: string | null = null) => {
    setHistory((previous) => [...previous, draftRef.current]);
    draftRef.current = next;
    setDraft(next);
    setSelectedShapeId(nextSelection);
    setSaved(false);
  };

  const activateTool = (nextTool: Tool) => {
    if (tool === 'polygon' && polygonPoints.length >= 3) {
      commit([...draft, annotation('polygon', label, { points: polygonPoints })]);
      setPolygonPoints([]);
    }
    setDragStart(null);
    setPreview(null);
    setTool(nextTool);
  };

  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!item || tool === 'select') return;
    event.preventDefault();
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
    if (!item) return;
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
    if (!item) return;
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
    if (!item) return;
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
    const resize = resizeRef.current;
    if (resize) {
      if (resize.moved) {
        setHistory((previous) => [...previous, resize.beforeDraft]);
        setSelectedShapeId(resize.shapeId);
      }
      resizeRef.current = null;
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
  };

  const onPointerCancel = () => {
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
  };

  const onDoubleClick = (event: ReactMouseEvent<SVGSVGElement>) => {
    if (tool !== 'polygon') return;
    event.preventDefault();
    if (polygonPoints.length < 3) return;
    commit([...draft, annotation('polygon', label, { points: polygonPoints })]);
    setPolygonPoints([]);
  };

  const undo = () => {
    const previous = history.at(-1);
    if (!previous) return;
    draftRef.current = previous;
    setDraft(previous);
    setHistory((entries) => entries.slice(0, -1));
    setSelectedShapeId(null);
    setSaved(false);
  };

  const deleteSelected = () => {
    if (!selectedShapeId) return;
    commit(draftRef.current.filter((entry) => entry.shape_id !== selectedShapeId));
  };

  const toggleSelectedLock = () => {
    if (!selectedShapeId) return;
    const selected = draftRef.current.find((entry) => entry.shape_id === selectedShapeId);
    if (!selected) return;
    commit(draftRef.current.map((entry) => entry.shape_id === selectedShapeId
      ? { ...entry, locked: !annotationLocked(entry) }
      : entry), selectedShapeId);
  };

  const moveSelectedByKeyboard = (shortcut: string) => {
    if (!item || !selectedShapeId) return;
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

  const annotationControls = (
    <Stack spacing={3}>
      <HStack spacing={2} flexWrap="wrap">
        <ToolButton active={tool === 'select'} onClick={() => activateTool('select')} isDisabled={isCoordinateInspector}><MousePointer2 size={14} /> Select</ToolButton>
        <ToolButton active={tool === 'rectangle'} onClick={() => activateTool('rectangle')} isDisabled={isCoordinateInspector}><Square size={14} /> Box</ToolButton>
        <ToolButton active={tool === 'polygon'} onClick={() => activateTool('polygon')} isDisabled={isCoordinateInspector}><Pentagon size={14} /> Polygon</ToolButton>
        <ToolButton active={tool === 'point'} onClick={() => activateTool('point')} isDisabled={isCoordinateInspector}><Circle size={14} /> Point</ToolButton>
        <ToolButton active={tool === 'circle'} onClick={() => activateTool('circle')} isDisabled={isCoordinateInspector}><Circle size={14} /> Circle</ToolButton>
      </HStack>
      <HStack spacing={2}>
        <Button size="sm" leftIcon={<Undo2 size={14} />} onClick={undo} isDisabled={isCoordinateInspector || history.length === 0}>Undo</Button>
        <Button size="sm" leftIcon={<Trash2 size={14} />} onClick={deleteSelected} isDisabled={isCoordinateInspector || !selectedShapeId}>Delete selected</Button>
        <Button
          size="sm"
          leftIcon={selectedIsLocked ? <Unlock size={14} /> : <Lock size={14} />}
          onClick={toggleSelectedLock}
          isDisabled={isCoordinateInspector || !selectedAnnotation}
          aria-label={selectedIsLocked ? 'Unlock selected human annotation' : 'Lock selected human annotation'}
        >
          {selectedIsLocked ? 'Unlock selected' : 'Lock selected'}
        </Button>
      </HStack>
      <HStack spacing={4} align="end" flexWrap="wrap">
        <FormControl maxW={{ base: '100%', laptop: '250px' }}>
          <FormLabel fontSize="sm">Lesion class</FormLabel>
          <Select value={label} onChange={(event) => setLabel(event.target.value as LesionLabel)}>
            {LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </Select>
        </FormControl>
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
      <ToolButton ariaLabel="Select tool" active={tool === 'select'} onClick={() => activateTool('select')} isDisabled={isCoordinateInspector}>
        <MousePointer2 size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Select</Box>
      </ToolButton>
      <ToolButton ariaLabel="Box tool" active={tool === 'rectangle'} onClick={() => activateTool('rectangle')} isDisabled={isCoordinateInspector}>
        <Square size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Box</Box>
      </ToolButton>
      <ToolButton ariaLabel="Polygon tool" active={tool === 'polygon'} onClick={() => activateTool('polygon')} isDisabled={isCoordinateInspector}>
        <Pentagon size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Polygon</Box>
      </ToolButton>
      <ToolButton ariaLabel="Point tool" active={tool === 'point'} onClick={() => activateTool('point')} isDisabled={isCoordinateInspector}>
        <Circle size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Point</Box>
      </ToolButton>
      <ToolButton ariaLabel="Circle tool" active={tool === 'circle'} onClick={() => activateTool('circle')} isDisabled={isCoordinateInspector}>
        <Circle size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Circle</Box>
      </ToolButton>
      <Button size="sm" leftIcon={<Undo2 size={14} />} aria-label="Undo annotation change" onClick={undo} isDisabled={isCoordinateInspector || history.length === 0}>Undo</Button>
      <Button size="sm" leftIcon={<Trash2 size={14} />} aria-label="Delete selected annotation" onClick={deleteSelected} isDisabled={isCoordinateInspector || !selectedShapeId}>Delete</Button>
      <Button size="sm" leftIcon={selectedIsLocked ? <Unlock size={14} /> : <Lock size={14} />} onClick={toggleSelectedLock} isDisabled={isCoordinateInspector || !selectedAnnotation} aria-label={selectedIsLocked ? 'Unlock selected human annotation' : 'Lock selected human annotation'}>
        {selectedIsLocked ? 'Unlock' : 'Lock'}
      </Button>
      <Select aria-label="Lesion class" size="sm" value={label} onChange={(event) => setLabel(event.target.value as LesionLabel)} maxW={{ base: '150px', tablet: '190px' }}>
        {LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </Select>
      <Button size="sm" variant={showAi ? 'secondary' : 'outline'} onClick={() => setShowAi((visible) => !visible)} aria-pressed={showAi}>AI {showAi ? 'on' : 'off'}</Button>
      <Button size="sm" variant={showHuman ? 'secondary' : 'outline'} onClick={() => setShowHuman((visible) => !visible)} aria-pressed={showHuman}>Human {showHuman ? 'on' : 'off'}</Button>
    </HStack>
  );

  const save = async () => {
    if (!item || saving) return;
    if (!reviewer.trim()) {
      setSaveError('Reviewer name is required before saving human annotations.');
      return;
    }
    setSaving(true);
    setDefaultReviewer(reviewer);
    setSaveError(null);
    setSaved(false);
    try {
      const savedCase = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(item.image_id)}/annotations`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          revision: item.revision,
          reviewer: reviewer.trim(),
          annotations: draft.map(({ shape_id, type, label: entryLabel, geometry, locked }) => ({
            shape_id,
            type,
            label: entryLabel,
            geometry,
            locked: locked !== false,
          })),
        }),
      });
      setItem(savedCase);
      draftRef.current = savedCase.human_annotations ?? [];
      setDraft(draftRef.current);
      setHistory([]);
      setSaved(true);
    } catch (err) {
      setSaveError(errorText(err));
    } finally {
      setSaving(false);
    }
  };

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
        actions={<HStack><Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} leftIcon={<ArrowLeft size={15} />}>Back to Review</Button><Button as={Link} to="/worklist">Back to Worklist</Button></HStack>}
      />
      <Grid templateColumns={{ base: '1fr', laptop: 'minmax(0, 1.4fr) minmax(300px, 0.6fr)' }} gap={5} alignItems="start">
        <Section title="Retinal annotation canvas" description="Coordinates are stored in original image pixel space. Double-click to finish a polygon.">
          <RetinalCanvas
            item={item}
            showAi={showAi}
            showHuman={showHuman}
            humanAnnotations={draft}
            selectedShapeId={selectedShapeId}
            onSelectHuman={setSelectedShapeId}
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
          >
            {polygonPoints.length > 0 && <polyline points={polygonPoints.map((point) => point.join(',')).join(' ')} fill="var(--chakra-colors-text-primary)" fillOpacity={0.1} stroke="var(--chakra-colors-text-primary)" strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />}
            {previewShape(preview)}
          </RetinalCanvas>
          <HStack mt={4} spacing={3} flexWrap="wrap" fontSize="sm">
            <Text fontWeight="semibold">{draft.length} human annotation{draft.length === 1 ? '' : 's'}</Text>
            <Text color="text.secondary">AI suggestions are optional visual evidence; human annotations remain separate.</Text>
          </HStack>
        </Section>
        <Stack spacing={5}>
          <Section title="Editor tools" description="Select a tool, choose a lesion class, then draw on the image.">
            {annotationControls}
          </Section>
          <Section title="Save human annotations" description="Saving writes only explicit HUMAN annotations to the case record.">
            <Stack spacing={3}>
              <FormControl isRequired>
                <FormLabel fontSize="sm">Reviewer name</FormLabel>
                <Input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Enter reviewer name" />
              </FormControl>
              {saveError && <Alert status="error"><AlertIcon /><Text fontSize="sm">{saveError}</Text></Alert>}
              {saved && <Alert status="success"><AlertIcon /><Text fontSize="sm">Human annotations saved.</Text></Alert>}
              <Button variant="solid" leftIcon={<Save size={15} />} onClick={() => void save()} isLoading={saving} isDisabled={saving}>Save annotations</Button>
            </Stack>
          </Section>
          <SimpleGrid columns={2} spacing={3} fontSize="sm">
            {LABEL_OPTIONS.map((option) => <HStack key={option.value} spacing={2}><Box w="10px" h="10px" borderRadius="sm" bg={LESION_COLORS[option.value]} /><Text>{LESION_SHORT_LABELS[option.value]} - {option.label}</Text></HStack>)}
          </SimpleGrid>
        </Stack>
      </Grid>
    </Box>
  );
}
