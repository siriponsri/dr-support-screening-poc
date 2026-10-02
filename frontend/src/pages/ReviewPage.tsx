import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Code,
  Center,
  Collapse,
  Grid,
  Heading,
  HStack,
  SimpleGrid,
  Select,
  Spinner,
  Stack,
  Text,
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { StatusBadge } from '@/components/common/StatusBadge';
import { RetinalCanvas, LESION_COLORS } from '@/components/review/RetinalCanvas';
import { displayedLesions } from '@/components/review/lesionPresentation';
import { CaseNavigation } from '@/components/common/CaseNavigation';
import { NextActionHint } from '@/components/common/NextActionHint';
import {
  apiJson,
  drGradeLabel,
  type CaseRecord,
  type LesionLabel,
  type ModelDescriptor,
} from '@/lib/api';
import { ArrowLeft, ChevronDown, ChevronUp, Play, UserRound } from '@/lib/icons';
import { LEAVE_CASE_DIALOG, useConfirmDialog } from '@/components/common/ConfirmDialog';
import { caseComplete } from '@/lib/caseProgress';

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'The request could not be completed.';
}

function clinicianModelStatus(status?: string | null) {
  switch (status) {
    case 'LOADED': return 'Ready';
    case 'REMOTE_NOT_CONFIGURED': return 'Model service unavailable';
    case 'ASSET_REQUIRED': return 'Model setup required';
    case 'CONFIGURED_NOT_VERIFIED': return 'Verification required';
    default: return status ? 'Status available' : 'Status not reported';
  }
}

function clinicianResultState(state?: string | null) {
  switch (state) {
    case 'AI_SUGGESTION': return 'Model suggestion';
    case 'UNCERTAIN': return 'Uncertain result';
    case 'UNGRADABLE': return 'Image not gradable';
    case 'UNSUPPORTED': return 'Unsupported input';
    default: return state ? 'Result available' : 'Not analyzed';
  }
}

function ResultWarnings({ item }: { item: CaseRecord }) {
  const warnings = [...(item.global?.warnings ?? []), ...(item.lesion?.warnings ?? [])];
  if (warnings.length === 0) return null;
  return (
    <Alert status="warning" mt={4}>
      <AlertIcon />
      <Stack spacing={1}>
        <Text fontWeight="semibold">Model notes available</Text>
        <Text fontSize="sm">Technical model notes are available in Models &amp; Audit. Review remains available; confirm the image and human decision.</Text>
      </Stack>
    </Alert>
  );
}

function ModelStatus({ models, error }: { models: ModelDescriptor[]; error: string | null }) {
  const relevant = models.filter((model) => ['retfound-aptos5', 'prism-dr-5fold'].includes(model.model_id));
  return (
    <Section title="Model / runtime status" description="Status reported by the existing model metadata contract.">
      {error && <Text color="status.warning" fontSize="sm">{error}</Text>}
      {!error && relevant.length === 0 && <Text color="text.secondary">No model status returned.</Text>}
      <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={3}>
        {relevant.map((model) => (
          <Box key={model.model_id} borderWidth="1px" borderColor="border.subtle" borderRadius="md" p={3}>
            <HStack justify="space-between" align="flex-start">
              <Stack spacing={1}>
                <Text fontWeight="semibold">{model.model_id}</Text>
                <Text fontSize="xs" color="text.secondary">{model.runtime ?? 'runtime not reported'}</Text>
              </Stack>
              <StatusBadge tone={model.status === 'LOADED' ? 'success' : 'warning'}>
                {clinicianModelStatus(model.status)}
              </StatusBadge>
            </HStack>
            {model.warnings?.length ? <Text mt={2} fontSize="xs" color="text.secondary">{model.warnings[0]}</Text> : null}
          </Box>
        ))}
      </SimpleGrid>
    </Section>
  );
}

function Assessment({ item }: { item: CaseRecord }) {
  if (!item.global) return <Text color="text.secondary">Not analyzed</Text>;
  return (
    <Stack spacing={3}>
      <HStack justify="space-between" align="flex-start">
        <Stack spacing={1}>
          <Text fontSize="sm" color="text.secondary">System-predicted DR grade</Text>
          <Heading size="lg">{item.global.grade === null ? item.global.state : (drGradeLabel(item.global.grade) ?? 'Grade available')}</Heading>
        </Stack>
      <StatusBadge tone={item.global.state === 'AI_SUGGESTION' ? 'info' : 'warning'}>{clinicianResultState(item.global.state)}</StatusBadge>
      </HStack>
      {item.global.confidence !== null && (
        <HStack justify="space-between">
          <Text color="text.secondary">Model confidence</Text>
          <Text fontWeight="semibold">{(item.global.confidence * 100).toFixed(1)}%</Text>
        </HStack>
      )}
      <Text fontSize="xs" color="text.muted">Model: {item.global.model_id} - {item.global.model_version}</Text>
    </Stack>
  );
}

function LesionSuggestions({ item }: { item: CaseRecord }) {
  if (!item.lesion) return <Text color="text.secondary">Not analyzed</Text>;
  const lesions = item.lesion.lesions;
  const counts = lesions.reduce<Record<string, number>>((result, lesion) => {
    result[lesion.canonical_label] = (result[lesion.canonical_label] ?? 0) + 1;
    return result;
  }, {});
  return (
    <Stack spacing={3}>
      <HStack justify="space-between">
        <Text color="text.secondary">AI lesion suggestions</Text>
        <Text fontWeight="semibold">{lesions.length}</Text>
      </HStack>
      <Stack spacing={2}>
        <Text fontSize="sm" color="text.secondary">Suggested classes</Text>
        {Object.keys(counts).length ? Object.entries(counts).map(([label, count]) => (
          <HStack key={label} justify="space-between"><Text>{LESION_DISPLAY_LABELS[label] ?? label.replace(/_/g, ' ')}</Text><Badge variant="info">{count}</Badge></HStack>
        )) : <Text color="text.secondary">No lesion suggestions</Text>}
      </Stack>
      <Text fontSize="xs" color="text.muted">Raw AI suggestions by class. Optional visual assistance; no per-detection action is required.</Text>
      <Text fontSize="xs" color="text.muted">Model: {item.lesion.model_id} - {item.lesion.model_version}</Text>
    </Stack>
  );
}

const LESION_DISPLAY_LABELS: Record<string, string> = {
  MICROANEURYSM: 'Microaneurysm',
  HEMORRHAGE: 'Hemorrhage',
  HARD_EXUDATE: 'Hard exudate',
  SOFT_EXUDATE: 'Soft exudate',
};

const MODEL_IDS = ['retfound-aptos5', 'prism-dr-5fold'];

function modelCapabilityUnavailable(models: ModelDescriptor[]): boolean {
  return models.some((model) => (
    MODEL_IDS.includes(model.model_id)
      && !['LOADED', 'SYNTHETIC_FIXTURE'].includes(model.status ?? '')
  ));
}

function LesionLegend() {
  return (
    <HStack spacing={3} flexWrap="wrap" fontSize="xs" color="text.secondary">
      {Object.entries(LESION_COLORS).map(([label, color]) => (
        <HStack key={label} spacing={1}>
          <Box w="9px" h="9px" borderRadius="sm" bg={color} />
          <Text>{LESION_DISPLAY_LABELS[label] ?? label.replace(/_/g, ' ')}</Text>
        </HStack>
      ))}
    </HStack>
  );
}

function MaskLegend() {
  return (
    <Stack spacing={1} aria-label="Mask preview key">
      <Text fontSize="xs" fontWeight="semibold" color="text.primary">Mask preview key</Text>
      <HStack spacing={3} flexWrap="wrap" fontSize="xs" color="text.secondary">
        <HStack spacing={1}>
          <Box w="9px" h="9px" borderRadius="sm" bg="#A9D5BE" />
          <Text>Retained retinal area</Text>
        </HStack>
        <HStack spacing={1}>
          <Box w="9px" h="9px" borderRadius="sm" bg="#D7BF87" />
          <Text>Excluded border / artifact area</Text>
        </HStack>
        <HStack spacing={1}>
          <Box w="9px" h="9px" borderWidth="2px" borderColor="text.secondary" borderRadius="sm" />
          <Text>Mask boundary (retained / excluded edge)</Text>
        </HStack>
      </HStack>
    </Stack>
  );
}

function admissionAllowsAnalysis(item: CaseRecord | null) {
  return Boolean(
    item?.admission
      && item.admission.modality_admission === 'FUNDUS_ACCEPTED'
      && (item.admission.quality_state === 'GRADABLE' || item.admission.quality_state === 'NOT_EVALUATED'),
  );
}

function patientEyeContext(item: CaseRecord) {
  const patient = item.patient_key ?? item.patient_candidate ?? item.display_name;
  const eye = item.laterality === 'LEFT' ? 'Left' : item.laterality === 'RIGHT' ? 'Right' : 'Eye not confirmed';
  return `${patient} \u00b7 ${eye}`;
}

function sourceOriginLabel(sourceOrigin: CaseRecord['source_origin']): string {
  if (sourceOrigin === 'PUBLIC') return 'Public source';
  if (sourceOrigin === 'SYNTHETIC') return 'Synthetic fixture';
  if (sourceOrigin === 'WORKSPACE') return 'Workspace input';
  return 'Not recorded';
}

function processingAudit(item: CaseRecord) {
  return item.analysis_preparation?.derivative ?? item.analysis_derivative;
}

function selectedMaskLabel(item: CaseRecord): string {
  const preparation = item.analysis_preparation;
  const audit = processingAudit(item);
  if (preparation?.status === 'NEEDS_REVIEW') {
    return preparation.candidate_mask_sha256
      ? 'Candidate mask recorded for inspection only; analysis not approved'
      : 'Unavailable - mask needs review; Original/manual review only';
  }
  if (preparation?.status === 'FAILED') {
    return 'Unavailable - mask preparation failed; Original/manual review only';
  }
  if (audit?.retinal_field_status === 'READY' && audit.valid_retina_mask_sha256) {
    return 'Retinal-field mask recorded; no fallback used';
  }
  if (audit?.retinal_field_status === 'NOT_APPLICABLE') {
    return 'No mask recorded; source representation used';
  }
  if (item.modality === 'UWF') {
    return 'Unavailable - no mask record; Original/manual review only';
  }
  return 'Not applicable for this case';
}

function analysisPreparationNote(item: CaseRecord): string {
  switch (item.analysis_preparation?.status) {
    case 'READY':
      if (processingAudit(item)?.retinal_field_status === 'NOT_APPLICABLE') {
        return 'No mask was recorded; the source representation is the analysis area. Original remains immutable.';
      }
      return 'Analysis area is a versioned, derived view; Original remains immutable.';
    case 'NEEDS_REVIEW':
      return item.analysis_preparation.candidate_mask_sha256
        ? 'A candidate mask is available in Mask preview for inspection only; it is not approved model input.'
        : 'No candidate mask is available; Original and manual review remain available.';
    case 'FAILED':
      return 'Mask preparation failed; Original and manual review remain available.';
    default:
      return 'No recorded analysis-area or mask representation is available; Original remains the review source.';
  }
}

function analysisTransformLabel(item: CaseRecord): string {
  return processingAudit(item)?.transform_description ?? 'Unavailable - no transform recorded';
}

function modelTransformLabel(item: CaseRecord): string {
  const preprocessing = item.global?.provenance?.preprocessing ?? item.lesion?.provenance?.preprocessing;
  if (preprocessing) return preprocessing;
  return item.global || item.lesion
    ? 'Unavailable - model transform not reported'
    : 'Unavailable - no model result recorded';
}

function modelDomainWarningLabel(item: CaseRecord): string {
  const warnings = [...(item.global?.warnings ?? []), ...(item.lesion?.warnings ?? [])].filter(Boolean);
  if (warnings.length > 0) return warnings.join(' ');
  return item.global || item.lesion
    ? 'No model/domain warning recorded'
    : 'Unavailable - no model result recorded';
}

export function ReviewPage() {
  const location = useLocation();
  const { pathname } = location;
  const navigate = useNavigate();
  const { imageId } = useParams<{ imageId: string }>();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [models, setModels] = useState<ModelDescriptor[]>([]);
  const [imageView, setImageView] = useState<'original' | 'analysis-area' | 'mask-overlay' | 'ai-evidence' | 'explainability'>('original');
  const [lesionFilter, setLesionFilter] = useState<LesionLabel | 'ALL'>('ALL');
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [maskOverlayLoadError, setMaskOverlayLoadError] = useState(false);
  const [processingOpen, setProcessingOpen] = useState(false);
  const [confirmDialog, confirm] = useConfirmDialog();

  const loadCase = useCallback(async () => {
    if (!imageId) return;
    setLoading(true);
    setError(null);
    try {
      setItem(await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(imageId)}`));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [imageId]);

  const loadModels = useCallback(async () => {
    try {
      setModels(await apiJson<ModelDescriptor[]>('/v1/models'));
      setModelError(null);
    } catch (err) {
      setModelError(errorText(err));
    }
  }, []);

  useEffect(() => {
    void loadCase();
    void loadModels();
    setImageView('original');
    setMaskOverlayLoadError(false);
  }, [loadCase, loadModels]);

  const handleMaskOverlayError = useCallback(() => {
    setMaskOverlayLoadError(true);
    setImageView((current) => current === 'mask-overlay' ? 'original' : current);
  }, []);

  const leaveToWorklist = async () => {
    if (item && !caseComplete(item) && !(await confirm(LEAVE_CASE_DIALOG))) return;
    navigate('/worklist');
  };

  const analyze = async () => {
    if (!item || analyzing) return;
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      setProgress('Running RETFound global grading...');
      await apiJson<unknown>('/v1/infer/global', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_id: item.image_id, modality: item.modality, model_id: 'retfound-aptos5' }),
      });
      setProgress('Running PRISM-DR lesion localization...');
      await apiJson<unknown>('/v1/infer/lesion-roi', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_id: item.image_id, modality: item.modality, model_id: 'prism-dr-5fold' }),
      });
      setProgress('Reloading returned case results...');
      await loadCase();
      await loadModels();
    } catch (err) {
      setAnalysisError(errorText(err));
      await loadCase();
    } finally {
      setProgress('');
      setAnalyzing(false);
    }
  };

  const allWarnings = useMemo(() => item ? [...(item.global?.warnings ?? []), ...(item.lesion?.warnings ?? [])] : [], [item]);
  const modelUnavailable = modelCapabilityUnavailable(models);
  const admissionReady = admissionAllowsAnalysis(item);
  const analysisAllowed = admissionReady && item?.modality === 'CFP' && ['PUBLIC', 'SYNTHETIC'].includes(item?.source_origin ?? item?.source_type ?? '') && !modelUnavailable;
  const analysisPreparationStatus = item?.analysis_preparation?.status;
  const analysisCandidateAvailable = Boolean(analysisPreparationStatus === 'READY' && item?.analysis_preparation?.derivative);
  const analysisAudit = item ? processingAudit(item) : null;
  const processingPathRecorded = Boolean(analysisPreparationStatus === 'READY' && analysisAudit);
  const maskCandidateAvailable = Boolean(
    (analysisPreparationStatus === 'READY' && analysisAudit?.valid_retina_mask_sha256)
      || (analysisPreparationStatus === 'NEEDS_REVIEW' && item?.analysis_preparation?.candidate_mask_sha256),
  );
  const maskOverlayAvailable = maskCandidateAvailable && !maskOverlayLoadError;
  const analysisAreaUrl = item ? `/v1/images/${encodeURIComponent(item.image_id)}/analysis-area` : '';
  const maskOverlayUrl = item ? `/v1/images/${encodeURIComponent(item.image_id)}/mask-overlay` : '';
  const hasRecordedEvidence = Boolean(item?.global || item?.lesion);
  const manualOnly = !hasRecordedEvidence && (
    item?.modality === 'UWF'
      || item?.source_origin === 'WORKSPACE'
      || modelUnavailable
      || models.length === 0
  );

  if (!imageId) {
    return (
      <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
        <PageHeader pathname={pathname} title="Review" />
        <Section title="Select an admitted case" description="Choose an image from the Worklist to open Review." action={<Button as={Link} to="/worklist">Open Worklist</Button>}>
          <Text color="text.secondary">No image was selected.</Text>
        </Section>
      </Box>
    );
  }

  if (loading && !item) return <Center minH="360px"><Spinner color="action.primary" /></Center>;

  if (error || !item) {
    return (
      <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
        <PageHeader pathname={pathname} title="Review" />
        <Alert status="error"><AlertIcon /><Text>{error ?? 'Case unavailable.'}</Text></Alert>
        <Button mt={4} leftIcon={<ArrowLeft size={15} />} onClick={() => navigate('/worklist')}>Back to Worklist</Button>
      </Box>
    );
  }

  return (
    <Box as="main" maxW="1440px" minW={0} overflowX="hidden" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader
        pathname={pathname}
        title="Review"
        subtitle={`${item.display_name} - optional model evidence for clinician inspection`}
        actions={<Button onClick={() => void leaveToWorklist()} leftIcon={<ArrowLeft size={15} />}>Back to Worklist</Button>}
      />
      <HStack mb={5} spacing={2} aria-label="Patient and eye context">
        <Text fontSize="xs" color="text.secondary" textTransform="uppercase" letterSpacing="0.04em">Patient/Eye</Text>
        <Text fontSize="sm" fontWeight="semibold">{patientEyeContext(item)}</Text>
      </HStack>
      <Stack spacing={3} mb={5}>
        <CaseNavigation imageId={item.image_id} guarded={!caseComplete(item)} confirm={confirm} />
        <NextActionHint item={item} models={models} />
      </Stack>
      <Grid templateColumns={{ base: '1fr', laptop: 'minmax(0, 1.35fr) minmax(320px, 0.65fr)' }} gap={5} alignItems="start" minW={0}>
        <Section title="Retinal preview" description={`${item.width} x ${item.height}px · ${item.modality === 'UWF' ? 'Ultra-widefield' : item.modality === 'CFP' ? 'Conventional fundus photograph' : 'Image type needs confirmation'}`}>
          {item.modality === 'UWF' && (
            <Stack spacing={2} mb={3}>
              <Text fontSize="sm" color={item.analysis_preparation?.status === 'READY' ? 'status.success' : 'status.warning'}>
                {item.analysis_preparation?.status === 'READY' ? 'Masked Analysis prepared' : item.analysis_preparation?.status === 'NEEDS_REVIEW' ? 'Masked Analysis needs review' : 'Masked Analysis unavailable'}
              </Text>
              <Text id="uwf-analysis-status" fontSize="xs" color="text.secondary">
                {analysisPreparationNote(item)}
              </Text>
            </Stack>
          )}
          {item.image_url ? <RetinalCanvas
            item={imageView === 'analysis-area' && analysisCandidateAvailable ? { ...item, image_url: analysisAreaUrl } : item}
            maskOverlayUrl={imageView === 'mask-overlay' && maskOverlayAvailable ? maskOverlayUrl : null}
            onMaskOverlayError={handleMaskOverlayError}
            showAi={imageView === 'ai-evidence'}
            visibleLesionLabels={lesionFilter === 'ALL' ? undefined : [lesionFilter]}
            showHuman={false}
          /> : (
            <Alert status="error"><AlertIcon /><Text>{item.admission_ui?.note ?? 'This file has no readable image preview.'}</Text></Alert>
          )}
          {imageView === 'explainability' && <Alert status={item.explainability?.status === 'AVAILABLE' ? 'info' : 'warning'} mt={3}>
            <AlertIcon />
            <Stack spacing={1}><Text fontWeight="semibold">Explainability</Text><Text fontSize="sm">{item.explainability?.note ?? 'Explainability evidence is unavailable. It is model evidence, not lesion localization or a clinical probability.'}</Text></Stack>
          </Alert>}
          {item.spatial_ai_display?.status === 'BLOCKED' && <Alert status="warning" mt={3}><AlertIcon /><Text fontSize="sm">{item.spatial_ai_display.note}</Text></Alert>}
          <Stack spacing={3} mt={4} minW={0}>
            <HStack spacing={1} flexWrap="wrap" aria-label="Viewer modes">
              <Button size="sm" variant={imageView === 'original' ? 'solid' : 'outline'} aria-pressed={imageView === 'original'} onClick={() => setImageView('original')}>Original</Button>
              {item.modality === 'UWF' && <Button size="sm" variant={imageView === 'analysis-area' ? 'solid' : 'outline'} aria-describedby="uwf-analysis-status" aria-pressed={imageView === 'analysis-area'} isDisabled={!analysisCandidateAvailable} onClick={() => setImageView('analysis-area')}>Analysis area</Button>}
              {item.modality === 'UWF' && <Button size="sm" variant={imageView === 'mask-overlay' ? 'solid' : 'outline'} aria-describedby="uwf-analysis-status" aria-pressed={imageView === 'mask-overlay'} isDisabled={!maskOverlayAvailable} onClick={() => setImageView('mask-overlay')}>Mask preview</Button>}
              <Button size="sm" variant={imageView === 'ai-evidence' ? 'solid' : 'outline'} aria-pressed={imageView === 'ai-evidence'} isDisabled={item.spatial_ai_display?.status !== 'AVAILABLE' || (!item.global && !item.lesion)} onClick={() => setImageView('ai-evidence')}>AI evidence</Button>
              <Button size="sm" variant={imageView === 'explainability' ? 'solid' : 'outline'} aria-pressed={imageView === 'explainability'} onClick={() => setImageView('explainability')}>Explainability</Button>
            </HStack>
            {imageView === 'ai-evidence' && (
              <Select
                aria-label="Filter lesion overlays"
                size="sm"
                maxW="190px"
                value={lesionFilter}
                onChange={(event) => setLesionFilter(event.target.value as LesionLabel | 'ALL')}
              >
                <option value="ALL">All lesion classes</option>
                <option value="MICROANEURYSM">MA · Microaneurysm</option>
                <option value="HEMORRHAGE">HE · Hemorrhage</option>
                <option value="HARD_EXUDATE">EX · Hard exudate</option>
                <option value="SOFT_EXUDATE">SE · Soft exudate</option>
              </Select>
            )}
            {maskOverlayLoadError && (
              <Alert status="warning" mt={1}>
                <AlertIcon />
                <Text fontSize="sm">Mask preview unavailable. This candidate could not be loaded for this source. The original image remains available for review.</Text>
              </Alert>
            )}
            {item.modality === 'UWF' && !maskCandidateAvailable && !maskOverlayLoadError && (
              <Alert status="warning" mt={1}>
                <AlertIcon />
                <Text fontSize="sm">Mask preview unavailable. No safe mask representation is recorded for this case; the original image remains available for manual review.</Text>
              </Alert>
            )}
            <Text fontSize="xs" color="text.secondary">
              {imageView === 'ai-evidence' ? `Active overlays ${displayedLesions(item).length} of ${item.lesion_review?.raw_count ?? item.lesion?.lesions.length ?? 0} raw AI suggestions` : imageView === 'mask-overlay' ? 'Mask preview is processing evidence only; it is not a clinical gradability decision or approval of model input.' : 'Original image remains the review source.'}
            </Text>
            {imageView === 'mask-overlay' && <MaskLegend />}
            <LesionLegend />
          </Stack>
          <SimpleGrid columns={{ base: 1, tablet: 3 }} spacing={3} mt={4} fontSize="sm" minW={0}>
            <Stack spacing={1}><Text color="text.secondary">Image ID</Text><Code fontSize="xs" whiteSpace="normal">{item.image_id}</Code></Stack>
            <Stack spacing={1}><Text color="text.secondary">Dimensions</Text><Text>{item.width} x {item.height}px</Text></Stack>
            <Stack spacing={1}><Text color="text.secondary">Source</Text><Text>{item.source}</Text></Stack>
          </SimpleGrid>
        </Section>
        <Stack spacing={5} minW={0}>
          {manualOnly ? (
            <Section title="AI assistance" description="Model evidence is optional; manual review remains available.">
              <Alert status="info" variant="subtle">
                <AlertIcon />
                <Stack spacing={1}>
                  <Text fontWeight="semibold">{item.modality === 'UWF' ? 'Unavailable for UWF in this configuration.' : 'Unavailable for this image and configuration.'}</Text>
                  <Text fontSize="sm">Manual review remains available. No unqualified model result is shown.</Text>
                </Stack>
              </Alert>
            </Section>
          ) : (
            <>
              <Section
                title="Analysis"
                description="Optional model evidence; manual review remains available."
                action={<Button variant="solid" leftIcon={<Play size={15} />} onClick={() => void analyze()} isLoading={analyzing} loadingText="Analyzing" isDisabled={analyzing || !analysisAllowed}>{item.global || item.lesion ? 'Analyze again' : 'Analyze'}</Button>}
              >
                {analyzing && <HStack color="status.info" mb={3}><Spinner size="sm" /><Text fontSize="sm">{progress}</Text></HStack>}
                {modelUnavailable && hasRecordedEvidence && <Alert status="warning" mb={3}><AlertIcon /><Text fontSize="sm">New analysis is unavailable. Recorded model evidence remains visible with its provenance and warnings.</Text></Alert>}
                {analysisError && <Alert status="error"><AlertIcon /><Stack spacing={2}><Text>{analysisError}</Text><Button size="sm" variant="outline" onClick={() => void analyze()}>Retry</Button></Stack></Alert>}
                {item.modality === 'UNKNOWN' && (
                  <Alert status="warning"><AlertIcon /><Text>Confirm the image type in Worklist before AI analysis. Clinical review can continue.</Text></Alert>
                )}
                {!analysisError && !analyzing && item.modality === 'CFP' && !admissionReady && (
                  <Alert status="warning">
                    <AlertIcon />
                    <Stack spacing={2}>
                      <Text fontWeight="semibold">Needs image review</Text>
                      <Text fontSize="sm">Resolve this case from the Worklist before analysis.</Text>
                      <Button as={Link} to="/worklist" size="sm" variant="outline" alignSelf="flex-start">Open Worklist</Button>
                    </Stack>
                  </Alert>
                )}
                {!analysisError && !analyzing && item.modality === 'CFP' && admissionReady && (
                  item.global || item.lesion ? <Text fontSize="sm" color="text.secondary">Actual returned results are shown below.</Text> : (
                    <HStack spacing={2}>
                      <StatusBadge tone="success">Ready for analysis</StatusBadge>
                      <Text fontSize="sm" color="text.secondary">Not analyzed</Text>
                    </HStack>
                  )
                )}
              </Section>
              {item.global && <Section title="DR assessment"><Assessment item={item} /></Section>}
              {item.lesion && <Section title="Lesion suggestions"><LesionSuggestions item={item} /></Section>}
            </>
          )}
          <Section title="Explainability" description="Case-specific model evidence, separate from processing provenance.">
            <Stack spacing={3}>
              <Text fontSize="sm" color="text.secondary">
                {item.explainability?.status === 'AVAILABLE'
                  ? item.explainability.note
                  : 'Explainability evidence is unavailable. It is not lesion localization or a clinical probability.'}
              </Text>
              <Box borderWidth="1px" borderColor="border.subtle" borderRadius="md" p={3} bg="surface.subtle">
                <Stack spacing={1}>
                  <Text fontSize="xs" fontWeight="semibold">{processingPathRecorded ? 'Recorded processing path' : 'Documented processing path (when approved)'}</Text>
                  <Text fontSize="sm">Original -&gt; Analysis area -&gt; provider transform -&gt; actual model input</Text>
                  <Text fontSize="xs" color="text.secondary">
                    {processingPathRecorded
                      ? 'Analysis area and Mask preview are case-local processing evidence. Provider-specific transforms may still change the actual model input.'
                      : 'This case does not have an approved analysis preparation recorded. A candidate mask remains inspection-only; Original and manual review remain available.'}
                  </Text>
                </Stack>
              </Box>
            </Stack>
          </Section>
          <Stack spacing={2}>
            <Button as={Link} to={`/clinician-review/${encodeURIComponent(item.image_id)}`} leftIcon={<UserRound size={15} />} variant="solid" alignSelf="flex-start">Continue to clinician review</Button>
            <Text fontSize="xs" color="text.secondary">No clinical decision is recorded on this page. The DR grade is confirmed in Clinician Review.</Text>
          </Stack>
        </Stack>
      </Grid>
      <Box mt={5}>
        <Section
          title="Processing details"
          description="Read-only provenance for the source, derived representation, mapping, and model-domain state."
          action={<Button size="sm" variant="ghost" rightIcon={processingOpen ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />} aria-expanded={processingOpen} aria-controls="processing-details-panel" onClick={() => setProcessingOpen((open) => !open)}>{processingOpen ? 'Hide details' : 'Show details'}</Button>}
        >
          <Collapse in={processingOpen} animateOpacity>
            <Box id="processing-details-panel">
              <SimpleGrid columns={{ base: 1, tablet: 2, laptop: 4 }} spacing={3} fontSize="sm">
                <Stack spacing={1}><Text color="text.secondary">Source origin</Text><Text>{sourceOriginLabel(item.source_origin)}</Text></Stack>
                <Stack spacing={1}><Text color="text.secondary">Visit / capture</Text><Text>{item.visit_context?.visit_key ?? 'Unknown'}{item.visit_context?.captured_at ? ` · ${item.visit_context.captured_at}` : ''}</Text></Stack>
                <Stack spacing={1}><Text color="text.secondary">Analysis representation</Text><Text>{item.analysis_preparation?.derivative?.representation_version ?? 'Not used or not recorded'}</Text></Stack>
                <Stack spacing={1}><Text color="text.secondary">Spatial AI display</Text><Text>{item.spatial_ai_display?.status === 'AVAILABLE' ? 'Available in original-image pixels' : item.spatial_ai_display?.status === 'BLOCKED' ? 'Blocked until provenance matches' : 'Unavailable'}</Text></Stack>
                <Stack spacing={1}><Text color="text.secondary">Selected mask / fallback</Text><Text>{selectedMaskLabel(item)}</Text>{(processingAudit(item)?.valid_retina_mask_sha256 ?? item.analysis_preparation?.candidate_mask_sha256) && <Code fontSize="xs" whiteSpace="normal">{processingAudit(item)?.valid_retina_mask_sha256 ?? item.analysis_preparation?.candidate_mask_sha256}</Code>}{item.analysis_preparation?.candidate_mask_representation_version && <Text fontSize="xs" color="text.muted">{item.analysis_preparation.candidate_mask_representation_version}</Text>}</Stack>
                <Stack spacing={1}><Text color="text.secondary">Analysis transform</Text><Text>{analysisTransformLabel(item)}</Text></Stack>
                <Stack spacing={1}><Text color="text.secondary">Model transform</Text><Text>{modelTransformLabel(item)}</Text></Stack>
                <Stack spacing={1}><Text color="text.secondary">Model / domain warning</Text><Text>{modelDomainWarningLabel(item)}</Text></Stack>
              </SimpleGrid>
              {item.analysis_preparation?.status === 'FAILED' && <Alert status="warning" mt={4}><AlertIcon /><Text>Masked Analysis could not be prepared. Original and manual grading remain available.</Text></Alert>}
              {item.explainability?.status !== 'AVAILABLE' && <Text mt={4} fontSize="sm" color="text.secondary">Explainability unavailable. No attention map or clinical probability is fabricated.</Text>}
            </Box>
          </Collapse>
        </Section>
      </Box>
      <Box mt={5}><ModelStatus models={models} error={modelError} /></Box>
      {allWarnings.length > 0 && <ResultWarnings item={item} />}
      {confirmDialog}
    </Box>
  );
}
