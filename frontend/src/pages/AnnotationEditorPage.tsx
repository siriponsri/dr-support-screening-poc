import { useT } from '@/lib/i18n';
import { usePageNavigationGuard } from '@/components/shell/NavigationGuard';
import { useActiveCaseSession } from '@/hooks/useActiveCaseSession';
import { localTiming } from '@/lib/localTiming';
import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type MouseEvent as ReactMouseEvent } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Center,
  Collapse,
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
import { ReviewerField } from '@/components/common/ReviewerField';
import { GuideHint } from '@/components/common/GuideHint';
import { AiRoiPopover } from '@/components/review/AiRoiPopover';
import { ArtifactRoiControls } from '@/components/review/ArtifactRoiControls';
import { annotationAssistLesions } from '@/lib/artifactRoiAssist';
import { displayedLesions } from '@/components/review/lesionPresentation';
import { RetinalCanvas, LESION_COLORS, LESION_SHORT_LABELS, type RectangleResizeHandle } from '@/components/review/RetinalCanvas';
import { EDIT_CONFIRMED_ANNOTATIONS_DIALOG, SWITCH_IMAGE_DIALOG, LEAVE_CASE_DIALOG, useConfirmDialog } from '@/components/common/ConfirmDialog';
import { annotationsConfirmed, caseComplete, formatTimestamp, gradeConfirmed, imageContextConfirmed } from '@/lib/caseProgress';
import { loadCaseList, nextIncompleteCaseId } from '@/lib/caseNavigation';
import {
  apiJson,
  annotationCompletenessApi,
  drGradeLabel,
  humanAnnotationApi,
  lesionReviewApi,
  type AnnotationGeometry,
  type CaseRecord,
  type HumanAnnotation,
  type LesionLabel,
  type AnnotationCompletenessState,
} from '@/lib/api';
import { ArrowLeft, CheckCircle2, ChevronDown, ChevronUp, Lock, MousePointer2, Square, Trash2, Undo2, Unlock } from '@/lib/icons';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';
import { markGuideFirstFlowCompleted } from '@/lib/hintPreference';
import { useAnnotationDraft } from '@/hooks/useAnnotationDraft';
import {
  annotation,
  annotationLocked,
  editRoiRectangle,
  pointFromEvent,
  resizeRectangleGeometry,
  sameRectangle,
  translateAnnotationGeometry,
  type Point,
  type RoiRectangle,
  type Tool,
} from '@/components/annotation/annotationGeometry';
import { LABEL_OPTIONS, MoreToolsPopover, previewShape, RoiCorrectionBox, TOOL_GUIDANCE, TOOL_LABELS, ToolButton } from '@/components/annotation/AnnotationTools';

// The geometry helpers moved to components/annotation; tests and other code still import them from here.
export { editRoiRectangle, pointFromEvent, resizeRectangleGeometry, translateAnnotationGeometry };

function coreFinishState(record: CaseRecord): Exclude<AnnotationCompletenessState, 'NOT_REVIEWED'> {
  const findingCount = (record.human_annotations?.length ?? 0) + (record.annotations?.length ?? 0);
  return findingCount > 0 ? 'REVIEWED_FINDINGS_RECORDED' : 'REVIEWED_NONE_FOUND';
}

function errorText(err: unknown) {
  return err instanceof Error ? err.message : 'The request could not be completed.';
}

export function AnnotationEditorPage() {
  const { imageId } = useParams<{ imageId: string }>();
  return <AnnotationEditorPageSession key={imageId ?? ''} />;
}

function AnnotationEditorPageSession() {
  const isActive = useActiveCaseSession();
  const location = useLocation();
  const { pathname } = location;
  const navigate = useNavigate();
  const { imageId } = useParams<{ imageId: string }>();
  const t = useT();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [draft, setDraft] = useState<HumanAnnotation[]>([]);
  const [history, setHistory] = useState<HumanAnnotation[][]>([]);
  const [tool, setTool] = useState<Tool>('select');
  const [isCoordinateInspector, setIsCoordinateInspector] = useState(false);
  const [label, setLabel] = useState<LesionLabel | ''>('');
  const [reviewer, setReviewer] = useState(() => getDefaultReviewer());
  const [selectedShapeId, setSelectedShapeId] = useState<string | null>(null);
  const [selectedLesionId, setSelectedLesionId] = useState<string | null>(null);
  const [polygonPoints, setPolygonPoints] = useState<Point[]>([]);
  const [dragStart, setDragStart] = useState<Point | null>(null);
  const [preview, setPreview] = useState<{ type: Tool; geometry: AnnotationGeometry } | null>(null);
  const [showAi, setShowAi] = useState(true);
  const [showFilteredArtifacts, setShowFilteredArtifacts] = useState(false);
  const [showArtifactOverlay, setShowArtifactOverlay] = useState(false);
  const [artifactOverlayFailed, setArtifactOverlayFailed] = useState(false);
  const [previewArtifactProposals, setPreviewArtifactProposals] = useState(false);
  const [showHuman, setShowHuman] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [draftStatus, setDraftStatus] = useState<'saved' | 'unsaved' | 'saving' | 'failed'>('saved');
  const [useAsDefault, setUseAsDefault] = useState(true);
  const [editingConfirmed, setEditingConfirmed] = useState(false);
  const [roiEdit, setRoiEdit] = useState<{ detectionId: string; label: LesionLabel; rect: RoiRectangle } | null>(null);
  const [roiSaving, setRoiSaving] = useState(false);
  const [roiError, setRoiError] = useState<string | null>(null);
  const [completing, setCompleting] = useState(false);
  const [moreToolsOpen, setMoreToolsOpen] = useState(false);
  const [fullScreenMoreToolsOpen, setFullScreenMoreToolsOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [confirmDialog, confirm] = useConfirmDialog();
  const toast = useToast();
  const roiDragRef = useRef<{ handle: RectangleResizeHandle | null; start: Point; base: RoiRectangle; moved: boolean } | null>(null);
  const interactionRef = useRef(false);
  const actionBusyRef = useRef(false);
  const savingRef = useRef(false);
  const skipAutosaveRef = useRef(true);
  const completenessWrittenForFinishRef = useRef(false);
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

  const loadCase = useCallback(async (requestIsCurrent: () => boolean = isActive) => {
    if (!imageId) return;
    setLoading(true);
    setError(null);
    try {
      let loaded = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(imageId)}`);
      if (!isActive() || !requestIsCurrent()) return;
      const artifactBeforePrepare = loaded.artifact_roi_assist;
      if (artifactBeforePrepare?.enabled && ['NOT_PREPARED', 'STALE_OR_UNAVAILABLE_RETAINED_ALL',
        'INVALID_BINDING_RETAINED_ALL'].includes(artifactBeforePrepare.status)) {
        try {
          loaded = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(imageId)}/artifact-roi/prepare`, {
            method: 'POST', body: JSON.stringify({ revision: loaded.revision, scope_sha256: artifactBeforePrepare.scope_sha256 }),
          });
        } catch {
          loaded = { ...loaded, artifact_roi_assist: { ...artifactBeforePrepare,
            status: 'UNAVAILABLE_RETAINED_ALL', suppressed_ids: [], suppressed: [], overlay_url: null } };
        }
        if (!isActive() || !requestIsCurrent()) return;
      }
      setItem(loaded);
      setShowFilteredArtifacts(false); setShowArtifactOverlay(false); setArtifactOverlayFailed(false);
      setPreviewArtifactProposals(false);
      localTiming.modality(imageId, loaded.modality);
      localTiming.event('case_ready', imageId);
      setDraft(loaded.human_annotations ?? []);
      setHistory([]);
      setDraftStatus('saved');
      setEditingConfirmed(false);
      setSelectedLesionId(null);
      setRoiEdit(null);
      setRoiError(null);
      skipAutosaveRef.current = true;
    } catch (err) {
      if (isActive() && requestIsCurrent()) setError(errorText(err));
    } finally {
      if (isActive() && requestIsCurrent()) setLoading(false);
    }
  }, [imageId]);

  useEffect(() => {
    let current = true;
    void loadCase(() => current);
    return () => { current = false; };
  }, [loadCase]);

  const annotationConfirmed = annotationsConfirmed(item);
  const hasConfirmedGrade = gradeConfirmed(item);
  const readOnly = !hasConfirmedGrade || completing || Boolean(annotationConfirmed && !editingConfirmed);
  const importedFindingCount = item?.annotations?.length ?? 0;
  const recordedFindingCount = draft.length + importedFindingCount;
  const hasRecordedFindings = recordedFindingCount > 0;
  // With no human finding, every AI suggestion stays unaccepted; say so on Finish.
  const unacceptedAiCount = hasRecordedFindings ? 0 : item?.lesion_review?.suggestion_count ?? 0;
  const finishLabel = hasRecordedFindings
    ? 'Finish image & next'
    : unacceptedAiCount > 0
      ? `Finish: no findings added (${unacceptedAiCount} AI suggestion${unacceptedAiCount === 1 ? '' : 's'} not accepted)`
      : 'Finish: reviewed none found';

  const commit = (next: HumanAnnotation[], nextSelection: string | null = null) => {
    if (readOnly || actionBusyRef.current) return;
    if (item) localTiming.event('review_edit', item.image_id);
    setHistory((previous) => [...previous, draftRef.current]);
    draftRef.current = next;
    setDraft(next);
    setSelectedShapeId(nextSelection);
    setSaved(false);
    setDraftStatus('unsaved');
    completenessWrittenForFinishRef.current = false;
  };

  const activateTool = (nextTool: Tool) => {
    if (readOnly || actionBusyRef.current) return;
    if (tool === 'polygon' && polygonPoints.length >= 3 && label) {
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
    if (readOnly || actionBusyRef.current || !item || tool === 'select') return;
    if (!label) {
      setSaveError('Choose a finding class before drawing.');
      return;
    }
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
    if (readOnly || actionBusyRef.current || !item) return;
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
    if (readOnly || actionBusyRef.current || !item) return;
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
    if (readOnly || actionBusyRef.current || !item) return;
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
    if (readOnly || actionBusyRef.current) return;
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
    if (!label) {
      setDragStart(null);
      setPreview(null);
      setSaveError('Choose a finding class before drawing.');
      return;
    }
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
    if (readOnly || actionBusyRef.current || tool !== 'polygon' || !label) return;
    event.preventDefault();
    if (polygonPoints.length < 3) return;
    commit([...draft, annotation('polygon', label, { points: polygonPoints })]);
    setPolygonPoints([]);
  };

  const undo = () => {
    if (readOnly || actionBusyRef.current) return;
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
    if (readOnly || actionBusyRef.current) return;
    if (!selectedShapeId) return;
    commit(draftRef.current.filter((entry) => entry.shape_id !== selectedShapeId));
  };

  const toggleSelectedLock = () => {
    if (readOnly || actionBusyRef.current) return;
    if (!selectedShapeId) return;
    const selected = draftRef.current.find((entry) => entry.shape_id === selectedShapeId);
    if (!selected) return;
    commit(draftRef.current.map((entry) => entry.shape_id === selectedShapeId
      ? { ...entry, locked: !annotationLocked(entry) }
      : entry), selectedShapeId);
  };

  const moveSelectedByKeyboard = (shortcut: string) => {
    if (readOnly || actionBusyRef.current || !item || !selectedShapeId) return;
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
  const [completenessSaving, setCompletenessSaving] = useState<string | null>(null);

  const changeSelectedLabel = (nextLabel: LesionLabel) => {
    if (readOnly || actionBusyRef.current || !selectedAnnotation || annotationLocked(selectedAnnotation) || selectedAnnotation.label === nextLabel) return;
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
    if (!hasConfirmedGrade) return false;
    if (!annotationConfirmed || editingConfirmed) return true;
    if (!(await confirm(EDIT_CONFIRMED_ANNOTATIONS_DIALOG))) return false;
    setEditingConfirmed(true);
    setSaveError(null);
    return true;
  };

  const selectLesion = async (detectionId: string) => {
    if (!item || !hasConfirmedGrade || actionBusyRef.current) return;
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

  const confirmRoi = async () => {
    if (!item || readOnly || !roiEdit || !rawSelectedLesion || roiSaving || actionBusyRef.current || interactionRef.current) return;
    const reviewerName = roiReviewer();
    if (!reviewerName) { setRoiError('Enter a reviewer name before confirming.'); return; }
    const [x1, y1, x2, y2] = roiEdit.rect;
    if (x1 < 0 || y1 < 0 || x2 <= x1 || y2 <= y1) { setRoiError('ROI geometry must have positive width and height.'); return; }
    actionBusyRef.current = true;
    setRoiSaving(true);
    setRoiError(null);
    try {
      const base = await flushedCase();
      if (!isActive()) return;
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
      if (!isActive()) return;
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
        if (!isActive()) return;
        onHumanAnnotationDerived(derived);
      }
      clearRoiSelection();
      toast({ id: 'roi-confirmed', status: 'success', title: 'Annotation confirmed', duration: 2000, position: 'bottom' });
    } catch (err) {
      setRoiError(errorText(err));
    } finally {
      actionBusyRef.current = false;
      setRoiSaving(false);
    }
  };

  const removeRoi = async () => {
    if (!item || readOnly || !roiEdit || roiSaving || actionBusyRef.current || interactionRef.current) return;
    const reviewerName = roiReviewer();
    if (!reviewerName) { setRoiError('Enter a reviewer name before removing.'); return; }
    actionBusyRef.current = true;
    setRoiSaving(true);
    setRoiError(null);
    try {
      const base = await flushedCase();
      if (!isActive()) return;
      if (!base) throw new Error('The annotation draft could not be saved. Try again.');
      const saved = await lesionReviewApi.review(base.image_id, {
        revision: base.revision,
        reviewer: reviewerName,
        detection_id: roiEdit.detectionId,
        action: 'REJECT',
      });
      if (!isActive()) return;
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
      actionBusyRef.current = false;
      setRoiSaving(false);
    }
  };

  const annotationControls = (
    <Stack spacing={2}>
      <HStack spacing={2} flexWrap="wrap" align="end">
        <ToolButton active={tool === 'select'} onClick={() => activateTool('select')} isDisabled={isCoordinateInspector || roiSaving || readOnly}><MousePointer2 size={14} /> Select</ToolButton>
        <ToolButton active={tool === 'rectangle'} onClick={() => activateTool('rectangle')} isDisabled={isCoordinateInspector || roiSaving || readOnly}><Square size={14} /> Box</ToolButton>
        <MoreToolsPopover open={moreToolsOpen} onOpenChange={setMoreToolsOpen} tool={tool} onToolChange={setTool} onActivate={activateTool} disabled={readOnly || roiSaving} inspectorActive={isCoordinateInspector} />
        <Button size="sm" leftIcon={<Undo2 size={14} />} onClick={undo} isDisabled={isCoordinateInspector || roiSaving || readOnly || history.length === 0}>{t('Undo')}</Button>
        <Button size="sm" leftIcon={<Trash2 size={14} />} onClick={deleteSelected} isDisabled={isCoordinateInspector || roiSaving || readOnly || !selectedShapeId}>{t('Delete selected')}</Button>
        <Button
          size="sm"
          leftIcon={selectedIsLocked ? <Unlock size={14} /> : <Lock size={14} />}
          onClick={toggleSelectedLock}
          isDisabled={isCoordinateInspector || roiSaving || readOnly || !selectedAnnotation}
          aria-label={selectedIsLocked ? t('Unlock selected human annotation') : t('Lock selected human annotation')}
        >
          {selectedIsLocked ? t('Unlock selected') : t('Lock selected')}
        </Button>
        <FormControl width={{ base: '100%', tablet: '180px' }} flexShrink={0}>
          <FormLabel htmlFor="new-annotation-class" fontSize="xs" mb={1}>{t('Finding class')}</FormLabel>
          <Select id="new-annotation-class" size="sm" value={label} onChange={(event) => setLabel(event.target.value as LesionLabel | '')} isDisabled={readOnly || roiSaving}>
            <option value="">{t('Choose finding...')}</option>
            {LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </Select>
        </FormControl>
        {selectedAnnotation && (
          <FormControl width={{ base: '100%', tablet: '180px' }} flexShrink={0}>
            <FormLabel htmlFor="selected-annotation-class" fontSize="xs" mb={1}>{t('Selected annotation class')}</FormLabel>
            <Select id="selected-annotation-class" size="sm" value={selectedAnnotation.label} onChange={(event) => changeSelectedLabel(event.target.value as LesionLabel)} isDisabled={selectedIsLocked || readOnly || roiSaving}>
              {LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </Select>
          </FormControl>
        )}
        <Button size="sm" variant={showAi ? 'secondary' : 'outline'} onClick={() => setShowAi((visible) => !visible)} aria-pressed={showAi}>AI {showAi ? 'on' : 'off'}</Button>
        <Button size="sm" variant={showHuman ? 'secondary' : 'outline'} onClick={() => setShowHuman((visible) => !visible)} aria-pressed={showHuman}>Human {showHuman ? 'on' : 'off'}</Button>
      </HStack>
      <HStack spacing={2} flexWrap="wrap" fontSize="xs" color="text.secondary" aria-live="polite">
        <Text fontWeight="semibold">{t('Active tool:')} {TOOL_LABELS[tool]}</Text>
        <Text>{t(TOOL_GUIDANCE[tool])}</Text>
      </HStack>
    </Stack>
  );

  const fullScreenAnnotationControls = (
    <Stack spacing={1}>
      <HStack spacing={1} flexWrap="wrap" align="center">
        <ToolButton ariaLabel="Select tool" active={tool === 'select'} onClick={() => activateTool('select')} isDisabled={isCoordinateInspector || roiSaving || readOnly}>
          <MousePointer2 size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Select</Box>
        </ToolButton>
        <ToolButton ariaLabel="Box tool" active={tool === 'rectangle'} onClick={() => activateTool('rectangle')} isDisabled={isCoordinateInspector || roiSaving || readOnly}>
          <Square size={14} /><Box display={{ base: 'none', tablet: 'inline' }}>Box</Box>
        </ToolButton>
        <MoreToolsPopover open={fullScreenMoreToolsOpen} onOpenChange={setFullScreenMoreToolsOpen} tool={tool} onToolChange={setTool} onActivate={activateTool} disabled={readOnly || roiSaving} inspectorActive={isCoordinateInspector} fullscreen />
        <Button size="sm" leftIcon={<Undo2 size={14} />} aria-label={t('Undo annotation change')} onClick={undo} isDisabled={isCoordinateInspector || roiSaving || readOnly || history.length === 0}>{t('Undo')}</Button>
        <Button size="sm" leftIcon={<Trash2 size={14} />} aria-label={t('Delete selected annotation')} onClick={deleteSelected} isDisabled={isCoordinateInspector || roiSaving || readOnly || !selectedShapeId}>{t('Delete')}</Button>
        <Button size="sm" leftIcon={selectedIsLocked ? <Unlock size={14} /> : <Lock size={14} />} onClick={toggleSelectedLock} isDisabled={isCoordinateInspector || roiSaving || readOnly || !selectedAnnotation} aria-label={selectedIsLocked ? t('Unlock selected human annotation') : t('Lock selected human annotation')}>
          {selectedIsLocked ? t('Unlock') : t('Lock')}
        </Button>
        <Select aria-label={t('Finding class')} size="sm" value={label} onChange={(event) => setLabel(event.target.value as LesionLabel | '')} maxW={{ base: '150px', tablet: '190px' }} isDisabled={readOnly || roiSaving}>
          <option value="">{t('Choose finding...')}</option>
          {LABEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </Select>
        <Button size="sm" variant={showAi ? 'secondary' : 'outline'} onClick={() => setShowAi((visible) => !visible)} aria-pressed={showAi}>AI {showAi ? 'on' : 'off'}</Button>
        <Button size="sm" variant={showHuman ? 'secondary' : 'outline'} onClick={() => setShowHuman((visible) => !visible)} aria-pressed={showHuman}>Human {showHuman ? 'on' : 'off'}</Button>
      </HStack>
      <HStack spacing={2} flexWrap="wrap" fontSize="xs" color="text.secondary" aria-live="polite">
        <Text fontWeight="semibold">{t('Active tool:')} {TOOL_LABELS[tool]}</Text>
        <Text>{t(TOOL_GUIDANCE[tool])}</Text>
      </HStack>
    </Stack>
  );

  const persistDraft = async (withinAction = false): Promise<CaseRecord | null> => {
    if (!item || savingRef.current || (actionBusyRef.current && !withinAction) || !isActive()) return null;
    if (draftStatus === 'saved') return item;
    if (!hasConfirmedGrade) return null;
    if (!reviewer.trim()) {
      setSaveError('Reviewer name is required to save annotation changes.');
      return null;
    }
    const submittedDraft = draftRef.current;
    savingRef.current = true;
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
          annotations: submittedDraft.map(({ shape_id, type, label: entryLabel, geometry, locked, source_detection_id }) => ({
            shape_id,
            type,
            label: entryLabel,
            geometry,
            locked: locked !== false,
            source_detection_id,
          })),
        }),
      });
      if (!isActive()) return null;
      setItem(savedCase);
      // Edits made during the request belong to the next revision. Keep them
      // visible and unsaved; never confirm a snapshot that omits those edits.
      if (draftRef.current !== submittedDraft) {
        setDraftStatus('unsaved');
        return null;
      }
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
      savingRef.current = false;
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
    if (!persisted || !isActive()) return false;
    setSaving(true);
    try {
      const confirmed = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(imageId)}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: persisted.revision, action: 'CONFIRM_ANNOTATIONS', reviewer: reviewer.trim(), grade: null, comment: '' }),
      });
      if (!isActive()) return false;
      setItem(confirmed);
      if (annotationsConfirmed(confirmed)) localTiming.event('annotation_confirmed_save', confirmed.image_id);
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

  const guarded = Boolean(item && (completing || !caseComplete(item) || draftStatus !== 'saved' || editingConfirmed));
  const completedReview = Boolean(annotationConfirmed && hasConfirmedGrade && !editingConfirmed && !completing);

  const saveBeforeLeaving = async (): Promise<boolean> => {
    if (actionBusyRef.current || savingRef.current) return false;
    if (draftStatus === 'saved') return true;
    return Boolean(await persistDraft());
  };

  const authorizeLeave = async (reason: 'route' | 'case' | 'workspace' = 'route') => {
    if (actionBusyRef.current || savingRef.current) {
      setSaveError('Wait for the current annotation save or review action before leaving.');
      return false;
    }
    const dirty = draftStatus !== 'saved';
    const options = reason === 'case' ? SWITCH_IMAGE_DIALOG : dirty ? {
      title: 'Save draft before leaving?',
      body: ['Your annotation edits are not saved yet.', 'Save the draft before leaving. This does not confirm findings.'],
      cancelLabel: 'Stay on this image', confirmLabel: 'Save draft and leave',
    } : LEAVE_CASE_DIALOG;
    if (guarded && !(await confirm(options))) return false;
    return await saveBeforeLeaving() && isActive();
  };
  const navigationGuard = usePageNavigationGuard(authorizeLeave);

  const leaveTo = async (destination: string) => {
    if (!(await authorizeLeave())) return;
    navigationGuard.approved(() => navigate(destination));
  };

  const completionCaseList = async (): Promise<CaseRecord[] | null> => {
    try {
      const cases = await loadCaseList();
      return isActive() ? cases : null;
    } catch {
      if (isActive()) setSaveError('Image saved. The Worklist could not be loaded. Return to Worklist and retry.');
      return null;
    }
  };

  const openNextImage = async (completedId: string) => {
    const cases = await completionCaseList();
    if (!cases) return;
    const nextId = nextIncompleteCaseId(cases, completedId);
    const next = cases.find((entry) => entry.image_id === nextId);
    if (next && imageContextConfirmed(next)) navigationGuard.approved(() => navigate(`/review/${encodeURIComponent(next.image_id)}`));
    else navigationGuard.approved(() => navigate('/worklist', { state: { caseComplete: completedId, openConfirmImage: nextId } }));
  };

  const advanceAfterCompletion = async (completedId: string) => {
    const cases = await completionCaseList();
    if (!cases) return;
    const nextId = nextIncompleteCaseId(cases, completedId);
    const next = cases.find((entry) => entry.image_id === nextId);
    toast({
      id: 'case-complete',
      status: 'success',
      title: nextId ? t('Case complete: opening next image') : t('Case complete: every Worklist image is complete'),
      duration: 3500,
      position: 'top',
      isClosable: true,
    });
    if (next && imageContextConfirmed(next)) navigationGuard.approved(() => navigate(`/review/${encodeURIComponent(next.image_id)}`));
    else navigationGuard.approved(() => navigate('/worklist', { state: { caseComplete: completedId, openConfirmImage: nextId } }));
  };

  const refreshAfterFinishFailure = async (completenessRequestLost: boolean): Promise<CaseRecord | null> => {
    if (!item) return null;
    try {
      // Re-read after a failed mutation so a committed request with a lost
      // response can be retried from the current revision.
      const refreshed = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(item.image_id)}`);
      if (!isActive()) return null;
      setItem(refreshed);
      draftRef.current = refreshed.human_annotations ?? [];
      setDraft(draftRef.current);
      setHistory([]);
      setDraftStatus('saved');
      setSaved(true);
      const refreshedTargetState = coreFinishState(refreshed);
      completenessWrittenForFinishRef.current = completenessRequestLost
        && refreshed.annotation_completeness?.CORE?.state === refreshedTargetState;
      return refreshed;
    } catch {
      completenessWrittenForFinishRef.current = false;
      return null;
    }
  };

  /** Finish records Core completeness, confirms the current set, then advances. */
  const completeCase = async () => {
    if (!item || completing || completenessSaving || actionBusyRef.current || savingRef.current || interactionRef.current || !isActive()) return;
    if (!reviewer.trim()) {
      setSaveError('Reviewer name is required to finish this image.');
      return;
    }
    actionBusyRef.current = true;
    setCompleting(true);
    let completenessRequestLost = false;
    let targetState: Exclude<AnnotationCompletenessState, 'NOT_REVIEWED'> | null = null;
    try {
      let persisted = await persistDraft(true);
      if (!persisted || !isActive()) return;
      targetState = coreFinishState(persisted);
      const completenessAlreadyWritten = completenessWrittenForFinishRef.current
        && persisted.annotation_completeness?.CORE?.state === targetState;
      const completenessNeedsWrite = !completenessAlreadyWritten
        && (persisted.annotation_completeness?.CORE?.state !== targetState
        || !annotationsConfirmed(persisted)
        || editingConfirmed);
      if (completenessNeedsWrite) {
        setCompletenessSaving('CORE');
        try {
          persisted = await annotationCompletenessApi.update(item.image_id, {
            revision: persisted.revision,
            reviewer: reviewer.trim(),
            group: 'CORE',
            state: targetState,
            taxonomy_version: 'core-lesions-v1',
          });
          if (!isActive()) return;
          setItem(persisted);
          completenessWrittenForFinishRef.current = true;
        } catch (err) {
          completenessRequestLost = true;
          throw err;
        } finally {
          setCompletenessSaving(null);
        }
      }
      setSaving(true);
      const confirmed = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(item.image_id)}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: persisted.revision, action: 'CONFIRM_ANNOTATIONS', reviewer: reviewer.trim(), grade: null, comment: '' }),
      });
      if (!isActive()) return;
      setItem(confirmed);
      setSaved(true);
      if (annotationsConfirmed(confirmed)) localTiming.event('annotation_confirmed_save', confirmed.image_id);
      setDraftStatus('saved');
      completenessWrittenForFinishRef.current = false;
      clearRoiSelection();
      markGuideFirstFlowCompleted();
      await advanceAfterCompletion(item.image_id);
    } catch (err) {
      if (!isActive()) return;
      const refreshed = await refreshAfterFinishFailure(completenessRequestLost);
      const refreshedTargetState = refreshed ? coreFinishState(refreshed) : null;
      if (refreshed
        && annotationsConfirmed(refreshed)
        && refreshedTargetState
        && refreshed.annotation_completeness?.CORE?.state === refreshedTargetState) {
        clearRoiSelection();
        markGuideFirstFlowCompleted();
        await advanceAfterCompletion(refreshed.image_id);
        return;
      }
      setSaveError(errorText(err));
      setDraftStatus('failed');
    } finally {
      setSaving(false);
      actionBusyRef.current = false;
      setCompleting(false);
    }
  };

  // Autosave (900 ms), flush-before-ROI-decision/Finish and the leave-page guard; same place, same order.
  const { flushedCase } = useAnnotationDraft({
    item, draft, draftStatus, reviewer, completing, saving, roiSaving, persistDraft,
    skipAutosaveRef, actionBusyRef, interactionRef, savingRef,
  });

  if (!imageId) return <Center minH="360px"><Text>{t('Select an image from the Worklist.')}</Text></Center>;
  if (loading && !item) return <Center minH="360px"><Spinner color="action.primary" /></Center>;
  if (error || !item) {
    return <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={6}><Alert status="error"><AlertIcon /><Text>{t(error ?? 'Case unavailable.')}</Text></Alert><Button mt={4} onClick={() => navigate('/worklist')}>{t('Back to Worklist')}</Button></Box>;
  }

  return (
    <Box as="main" maxW="1920px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader
        pathname={pathname}
        title="Annotation Editor"
        subtitle={`${item.display_name} - ${t('human annotations are separate from AI suggestions')}`}
        actions={<HStack><Button onClick={() => void leaveTo(`/review/${encodeURIComponent(item.image_id)}`)} leftIcon={<ArrowLeft size={15} />} variant="ghost">{t('Back to Review')}</Button><Button onClick={() => void leaveTo('/worklist')}>{t('Back to Worklist')}</Button></HStack>}
      />
      <HStack mb={3} spacing={2} fontSize="sm" aria-label="DR grade status" color={hasConfirmedGrade ? 'text.secondary' : 'status.warning'}>
        {hasConfirmedGrade ? <CheckCircle2 size={16} color="var(--chakra-colors-status-success)" /> : null}
        <Text>{hasConfirmedGrade ? `${t('DR grade confirmed:')} ${drGradeLabel(item.clinician_review?.final_grade) ?? t('Grade confirmed')}` : t('DR grade not confirmed')}</Text>
      </HStack>
      {Boolean((location.state as { gradingComplete?: boolean } | null)?.gradingComplete) && hasConfirmedGrade && (
          <Alert status="success" mb={4}><AlertIcon /><Text><strong>{t('Grading complete.')}</strong> {t('Correct AI regions only where you disagree, then finish this image.')}</Text></Alert>
      )}
      {!hasConfirmedGrade && (
        <Alert status="warning" mb={4}>
          <AlertIcon />
          <Stack spacing={2}>
            <Text><strong>{t('Confirm the DR grade first.')}</strong> {t('Annotation review follows Clinician Review for this image. Your annotation draft is kept.')}</Text>
            <Button as={Link} to={`/clinician-review/${encodeURIComponent(item.image_id)}`} size="sm" variant="outline" alignSelf="flex-start">{t('Open Clinician Review')}</Button>
          </Stack>
        </Alert>
      )}
      {annotationConfirmed && !editingConfirmed && !completing && (
        <Alert status="info" mb={4}>
          <AlertIcon />
          <Stack spacing={1}>
            <Text fontWeight="semibold">{t('Annotations confirmed')}</Text>
            {item.annotation_confirmation?.reviewer && <Text fontSize="sm">{t('Reviewer:')} {item.annotation_confirmation.reviewer}</Text>}
            {item.annotation_confirmation?.timestamp && <Text fontSize="sm">{t('Confirmed at:')} {formatTimestamp(item.annotation_confirmation.timestamp)}</Text>}
          </Stack>
        </Alert>
      )}
      <Stack spacing={3} mb={5}>
        <CaseNavigation
          imageId={item.image_id}
          guarded={guarded}
          confirm={confirm}
          onBeforeSwitch={saveBeforeLeaving}
        />
      </Stack>
      <Grid minW={0} templateColumns={{ base: '1fr', laptop: 'minmax(0, 1fr) 320px' }} gap={5} alignItems="start">
        <Stack minW={0} spacing={4}>
        <Section title="Review findings">
          {annotationControls}
        </Section>
        <Section title="Retinal image" description="Inspect the image and record only the findings you choose to keep.">
          <ArtifactRoiControls item={item} showFiltered={showFilteredArtifacts} showOverlay={showArtifactOverlay}
            previewProposals={previewArtifactProposals} onPreviewProposals={setPreviewArtifactProposals}
            onShowFiltered={setShowFilteredArtifacts} onShowOverlay={setShowArtifactOverlay}
            onCaseChange={(saved) => {
              if (isActive() && saved.image_id === imageId) setItem((current) =>
                current && current.revision <= saved.revision ? saved : current);
            }} />
          {artifactOverlayFailed && <Alert status="warning"><AlertIcon />{t('Artifact overlay unavailable; all suggestions retained.')}</Alert>}
          <RetinalCanvas
            item={item}
            aiLesionsOverride={annotationAssistLesions(item, showFilteredArtifacts, artifactOverlayFailed, previewArtifactProposals)}
            maskOverlayUrl={showArtifactOverlay && !artifactOverlayFailed ? item.artifact_roi_assist?.overlay_url : null}
            maskOverlayLabel={item.artifact_roi_assist?.status === 'SHADOW_ONLY'
              ? 'Artifact proposal in orange; optional visibility preview only. No clinical labels or model input changed.'
              : item.artifact_roi_assist?.evidence_kind === 'GENERIC_IMAGE_ONLY_EMPIRICAL_NOT_CERTIFIED'
                ? 'Empirical artifact candidates in orange; uncertain areas retained. Original and model input unchanged.'
              : 'Sure-exclude artifact areas in orange; uncertain areas retained. Original and model input unchanged.'}
            onMaskOverlayError={() => { setArtifactOverlayFailed(true); setShowArtifactOverlay(false); }}
            showAi={showAi}
            showHuman={showHuman}
            humanAnnotations={draft}
            selectedShapeId={hasConfirmedGrade ? selectedShapeId : null}
            selectedLesionId={selectedLesionId}
            onSelectLesion={hasConfirmedGrade ? (detectionId) => { void selectLesion(detectionId); } : undefined}
            onSelectHuman={hasConfirmedGrade ? (shapeId) => { setSelectedShapeId(shapeId); clearRoiSelection(); } : undefined}
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
            onBeforeFullScreen={() => setMoreToolsOpen(false)}
            fullScreenControls={fullScreenAnnotationControls}
            renderInStage={(scale) => (roiEdit && !readOnly ? <RoiCorrectionBox rect={roiEdit.rect} scale={scale} /> : null)}
          >
            {polygonPoints.length > 0 && <polyline points={polygonPoints.map((point) => point.join(',')).join(' ')} fill="var(--chakra-colors-text-primary)" fillOpacity={0.1} stroke="var(--chakra-colors-text-primary)" strokeWidth={3} strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />}
            {previewShape(preview)}
          </RetinalCanvas>
          <HStack mt={4} spacing={3} flexWrap="wrap" fontSize="sm">
            <Text fontWeight="semibold">{draft.length} {t(draft.length === 1 ? 'human annotation' : 'human annotations')}</Text>
            <Text aria-live="polite" color={draftStatus === 'failed' ? 'status.danger' : 'text.secondary'}>{t(draftStatusText)}</Text>
          </HStack>
        </Section>
        <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={3} fontSize="sm">
          {LABEL_OPTIONS.map((option) => <HStack key={option.value} spacing={2}><Box w="10px" h="10px" borderRadius="sm" bg={LESION_COLORS[option.value]} /><Text>{LESION_SHORT_LABELS[option.value]} - {option.label}</Text></HStack>)}
        </SimpleGrid>
        </Stack>
        <Stack minW={0} spacing={5}>
          <Section title={completedReview ? 'Review complete' : 'Complete review'} description={hasRecordedFindings ? `${recordedFindingCount} ${t(recordedFindingCount === 1 ? 'finding recorded.' : 'findings recorded.')}` : 'No Core findings recorded.'}>
            <Stack spacing={3}>
              {!completedReview && <GuideHint step="findings" />}
              {!hasRecordedFindings && !annotationConfirmed && <Text fontSize="sm" color="text.secondary">{t('Finishing confirms Core findings were reviewed and none were found.')}{unacceptedAiCount > 0 ? ` ${t('AI suggestions you did not accept are not recorded as findings.')}` : ''}</Text>}
              {!completedReview && <ReviewerField compact id="annotation-reviewer" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />}
              {saveError && <Alert status="error" aria-live="assertive"><AlertIcon /><Text fontSize="sm">{t(saveError)}</Text></Alert>}
              {readOnly && hasConfirmedGrade && !completing ? (
                <HStack spacing={2} flexWrap="wrap">
                  <Button variant="solid" onClick={() => void openNextImage(item.image_id)}>{t('Open next image')}</Button>
                  <Button variant="outline" onClick={() => void beginAnnotationEdit()}>{t('Edit confirmed annotations')}</Button>
                </HStack>
              ) : (
                <Button variant="solid" onClick={() => void completeCase()} isLoading={completing || saving || Boolean(completenessSaving)} loadingText={t('Finishing')} isDisabled={!hasConfirmedGrade || roiSaving} whiteSpace="normal" h="auto" minH="36px" py={2}>{finishLabel}</Button>
              )}
            </Stack>
          </Section>
          <Box borderWidth="1px" borderColor="border.default" borderRadius="md" p={3}>
                <Button
                  variant="ghost"
                  size="sm"
                  px={0}
                  rightIcon={advancedOpen ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                  aria-expanded={advancedOpen}
                  aria-controls="advanced-findings-review"
                  onClick={() => setAdvancedOpen((open) => !open)}
                >
                  {t('Advanced findings (optional)')}
                </Button>
                <Collapse in={advancedOpen} animateOpacity>
                  <Stack id="advanced-findings-review" spacing={2} mt={2}>
                    <Text fontSize="sm" color="text.secondary">{t('Advanced findings are optional and deferred to a later phase. Complete the Core review above before finishing this image.')}</Text>
                  </Stack>
              </Collapse>
              </Box>
        </Stack>
      </Grid>
      {confirmDialog}
    </Box>
  );
}
