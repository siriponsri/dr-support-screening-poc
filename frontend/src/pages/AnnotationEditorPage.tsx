import { useCallback, useEffect, useState, type PointerEvent as ReactPointerEvent, type MouseEvent as ReactMouseEvent } from 'react';
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
import { RetinalCanvas, LESION_COLORS, LESION_SHORT_LABELS } from '@/components/review/RetinalCanvas';
import {
  apiJson,
  type AnnotationGeometry,
  type AnnotationType,
  type CaseRecord,
  type HumanAnnotation,
  type LesionLabel,
} from '@/lib/api';
import { ArrowLeft, Check, Circle, MousePointer2, Pentagon, Save, Square, Trash2, Undo2 } from '@/lib/icons';

type Tool = 'select' | 'rectangle' | 'polygon' | 'point' | 'circle';
type Point = [number, number];

const LABEL_OPTIONS: Array<{ value: LesionLabel; label: string }> = [
  { value: 'MICROANEURYSM', label: 'Microaneurysm' },
  { value: 'HEMORRHAGE', label: 'Hemorrhage' },
  { value: 'HARD_EXUDATE', label: 'Hard exudate' },
  { value: 'SOFT_EXUDATE', label: 'Soft exudate' },
];

function errorText(err: unknown) {
  return err instanceof Error ? err.message : 'The request could not be completed.';
}

function pointFromEvent(event: ReactPointerEvent<SVGSVGElement>, item: CaseRecord): Point {
  const bounds = event.currentTarget.getBoundingClientRect();
  return [
    Math.max(0, Math.min(item.width, ((event.clientX - bounds.left) / bounds.width) * item.width)),
    Math.max(0, Math.min(item.height, ((event.clientY - bounds.top) / bounds.height) * item.height)),
  ];
}

function makeId() {
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function annotation(type: AnnotationType, label: LesionLabel, geometry: AnnotationGeometry): HumanAnnotation {
  return { shape_id: makeId(), type, label, geometry, source: 'HUMAN', reviewer: '', created_at: '' };
}

function previewShape(preview: { type: Tool; geometry: AnnotationGeometry } | null) {
  if (!preview) return null;
  const { type, geometry } = preview;
  const color = '#111827';
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

function ToolButton({ tool, active, onClick, children }: { tool?: Tool; active?: boolean; onClick: () => void; children: React.ReactNode }) {
  return <Button size="sm" variant={active ? 'secondary' : 'outline'} onClick={onClick} aria-pressed={active}>{children}</Button>;
}

export function AnnotationEditorPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { imageId } = useParams<{ imageId: string }>();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [draft, setDraft] = useState<HumanAnnotation[]>([]);
  const [history, setHistory] = useState<HumanAnnotation[][]>([]);
  const [tool, setTool] = useState<Tool>('select');
  const [label, setLabel] = useState<LesionLabel>('MICROANEURYSM');
  const [reviewer, setReviewer] = useState('');
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

  const commit = (next: HumanAnnotation[]) => {
    setHistory((previous) => [...previous, draft]);
    setDraft(next);
    setSelectedShapeId(null);
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

  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!item || !dragStart || (tool !== 'rectangle' && tool !== 'circle')) return;
    const point = pointFromEvent(event, item);
    if (tool === 'rectangle') {
      setPreview({ type: tool, geometry: { x: Math.min(dragStart[0], point[0]), y: Math.min(dragStart[1], point[1]), width: Math.abs(point[0] - dragStart[0]), height: Math.abs(point[1] - dragStart[1]) } });
    } else {
      setPreview({ type: tool, geometry: { cx: dragStart[0], cy: dragStart[1], radius: Math.hypot(point[0] - dragStart[0], point[1] - dragStart[1]) } });
    }
  };

  const onPointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
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

  const onDoubleClick = (event: ReactMouseEvent<SVGSVGElement>) => {
    event.preventDefault();
    if (tool === 'polygon' && polygonPoints.length >= 3) {
      commit([...draft, annotation('polygon', label, { points: polygonPoints })]);
      setPolygonPoints([]);
    }
  };

  const undo = () => {
    const previous = history.at(-1);
    if (!previous) return;
    setDraft(previous);
    setHistory((entries) => entries.slice(0, -1));
    setSelectedShapeId(null);
    setSaved(false);
  };

  const deleteSelected = () => {
    if (!selectedShapeId) return;
    commit(draft.filter((entry) => entry.shape_id !== selectedShapeId));
  };

  const save = async () => {
    if (!item || saving) return;
    if (!reviewer.trim()) {
      setSaveError('Reviewer name is required before saving human annotations.');
      return;
    }
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      const savedCase = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(item.image_id)}/annotations`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          revision: item.revision,
          reviewer: reviewer.trim(),
          annotations: draft.map(({ shape_id, type, label: entryLabel, geometry }) => ({ shape_id, type, label: entryLabel, geometry })),
        }),
      });
      setItem(savedCase);
      setDraft(savedCase.human_annotations ?? []);
      setHistory([]);
      setSaved(true);
    } catch (err) {
      setSaveError(errorText(err));
    } finally {
      setSaving(false);
    }
  };

  if (!imageId) return <Center minH="360px"><Text>Select an image from the Worklist.</Text></Center>;
  if (loading && !item) return <Center minH="360px"><Spinner color="brand.500" /></Center>;
  if (error || !item) {
    return <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={6}><Alert status="error"><AlertIcon /><Text>{error ?? 'Case unavailable.'}</Text></Alert><Button mt={4} onClick={() => navigate('/worklist')}>Back to Worklist</Button></Box>;
  }

  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader
        pathname={pathname}
        title="Annotation Editor"
        subtitle={`${item.display_name} - human annotations are separate from AI suggestions`}
        actions={<HStack><Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} leftIcon={<ArrowLeft size={15} />}>Back to AI Review</Button><Button as={Link} to="/worklist">Back to Worklist</Button></HStack>}
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
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onDoubleClick={onDoubleClick}
          >
            {polygonPoints.length > 0 && <polyline points={polygonPoints.map((point) => point.join(',')).join(' ')} fill="#111827" fillOpacity={0.1} stroke="#111827" strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />}
            {previewShape(preview)}
          </RetinalCanvas>
          <HStack mt={4} spacing={3} flexWrap="wrap" fontSize="sm">
            <Text fontWeight="semibold">{draft.length} human annotation{draft.length === 1 ? '' : 's'}</Text>
            <Text color="text.secondary">AI suggestions remain suggestions until explicitly reviewed.</Text>
          </HStack>
        </Section>
        <Stack spacing={5}>
          <Section title="Editor tools" description="Select a tool, choose a lesion class, then draw on the image.">
            <Stack spacing={3}>
              <HStack spacing={2} flexWrap="wrap">
                <ToolButton active={tool === 'select'} onClick={() => activateTool('select')}><MousePointer2 size={14} /> Select</ToolButton>
                <ToolButton active={tool === 'rectangle'} onClick={() => activateTool('rectangle')}><Square size={14} /> Box</ToolButton>
                <ToolButton active={tool === 'polygon'} onClick={() => activateTool('polygon')}><Pentagon size={14} /> Polygon</ToolButton>
                <ToolButton active={tool === 'point'} onClick={() => activateTool('point')}><Circle size={14} /> Point</ToolButton>
                <ToolButton active={tool === 'circle'} onClick={() => activateTool('circle')}><Circle size={14} /> Circle</ToolButton>
              </HStack>
              <HStack spacing={2}>
                <Button size="sm" leftIcon={<Undo2 size={14} />} onClick={undo} isDisabled={history.length === 0}>Undo</Button>
                <Button size="sm" leftIcon={<Trash2 size={14} />} onClick={deleteSelected} isDisabled={!selectedShapeId}>Delete selected</Button>
              </HStack>
              <FormControl>
                <FormLabel fontSize="sm">Lesion class</FormLabel>
                <Select value={label} onChange={(event) => setLabel(event.target.value as LesionLabel)}>
                  {LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </Select>
              </FormControl>
              <Stack spacing={2} fontSize="sm">
                <Text>AI suggestions</Text>
                <Button size="sm" variant={showAi ? 'secondary' : 'outline'} onClick={() => setShowAi((visible) => !visible)}>{showAi ? 'Shown' : 'Hidden'}</Button>
                <Text>Human annotations</Text>
                <Button size="sm" variant={showHuman ? 'secondary' : 'outline'} onClick={() => setShowHuman((visible) => !visible)}>{showHuman ? 'Shown' : 'Hidden'}</Button>
              </Stack>
            </Stack>
          </Section>
          <Section title="Save human annotations" description="Saving writes only explicit HUMAN annotations to the case record.">
            <Stack spacing={3}>
              <FormControl isRequired>
                <FormLabel fontSize="sm">Reviewer name</FormLabel>
                <Input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Enter reviewer name" />
              </FormControl>
              {saveError && <Alert status="error"><AlertIcon /><Text fontSize="sm">{saveError}</Text></Alert>}
              {saved && <Alert status="success"><AlertIcon /><Text fontSize="sm">Human annotations saved.</Text></Alert>}
              <Button colorScheme="red" leftIcon={<Save size={15} />} onClick={() => void save()} isLoading={saving} isDisabled={saving}>Save annotations</Button>
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
