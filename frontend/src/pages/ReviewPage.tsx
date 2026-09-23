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
  FormControl,
  FormLabel,
  Grid,
  Heading,
  HStack,
  SimpleGrid,
  Select,
  Spinner,
  Stack,
  Switch,
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
  type CaseRecord,
  type LesionLabel,
  type ModelDescriptor,
} from '@/lib/api';
import { ArrowLeft, Pencil, Play, UserRound } from '@/lib/icons';

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
          <Heading size="lg">{item.global.grade === null ? item.global.state : `Grade ${item.global.grade}`}</Heading>
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

export function ReviewPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { imageId } = useParams<{ imageId: string }>();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [models, setModels] = useState<ModelDescriptor[]>([]);
  const [showAi, setShowAi] = useState(true);
  const [lesionFilter, setLesionFilter] = useState<LesionLabel | 'ALL'>('ALL');
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

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
  }, [loadCase, loadModels]);

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
  const remoteNotConfigured = models.some((model) => (
    ['retfound-aptos5', 'prism-dr-5fold'].includes(model.model_id)
      && model.status === 'REMOTE_NOT_CONFIGURED'
  ));
  const admissionReady = admissionAllowsAnalysis(item);
  const analysisAllowed = admissionReady && !remoteNotConfigured;

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
        actions={<Button as={Link} to="/worklist" leftIcon={<ArrowLeft size={15} />}>Back to Worklist</Button>}
      />
      <HStack mb={5} spacing={2} aria-label="Patient and eye context">
        <Text fontSize="xs" color="text.secondary" textTransform="uppercase" letterSpacing="0.04em">Patient/Eye</Text>
        <Text fontSize="sm" fontWeight="semibold">{patientEyeContext(item)}</Text>
      </HStack>
      <Stack spacing={3} mb={5}>
        <CaseNavigation imageId={item.image_id} />
        <NextActionHint item={item} models={models} />
      </Stack>
      <Grid templateColumns={{ base: '1fr', laptop: 'minmax(0, 1.35fr) minmax(320px, 0.65fr)' }} gap={5} alignItems="start" minW={0}>
        <Section title="Retinal preview" description={`${item.width} x ${item.height}px - ${item.modality}`}>
          {item.image_url ? <RetinalCanvas item={item} showAi={showAi} visibleLesionLabels={lesionFilter === 'ALL' ? undefined : [lesionFilter]} showHuman={false} /> : (
            <Alert status="error"><AlertIcon /><Text>{item.admission_ui?.note ?? 'This file has no readable image preview.'}</Text></Alert>
          )}
          <Stack spacing={3} mt={4} minW={0}>
            <HStack justify="space-between" align="center" flexWrap="wrap" gap={2}>
              <FormControl display="flex" alignItems="center" w="auto">
                <Switch id="show-ai-suggestions" isChecked={showAi} onChange={(event) => setShowAi(event.target.checked)} mr={2} />
                <FormLabel htmlFor="show-ai-suggestions" mb={0} fontSize="sm">Show AI suggestions</FormLabel>
              </FormControl>
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
              <Text fontSize="xs" color="text.secondary">
                Active overlays {displayedLesions(item).length} of {item.lesion_review?.raw_count ?? item.lesion?.lesions.length ?? 0} raw AI suggestions
              </Text>
            </HStack>
          <LesionLegend />
          </Stack>
          <SimpleGrid columns={{ base: 1, tablet: 3 }} spacing={3} mt={4} fontSize="sm" minW={0}>
            <Stack spacing={1}><Text color="text.secondary">Image ID</Text><Code fontSize="xs" whiteSpace="normal">{item.image_id}</Code></Stack>
            <Stack spacing={1}><Text color="text.secondary">Dimensions</Text><Text>{item.width} x {item.height}px</Text></Stack>
            <Stack spacing={1}><Text color="text.secondary">Source</Text><Text>{item.source}</Text></Stack>
          </SimpleGrid>
        </Section>
        <Stack spacing={5} minW={0}>
          <Section
            title="Analysis"
            description="Run both existing remote inference contracts on this admitted image."
            action={<Button variant="solid" leftIcon={<Play size={15} />} onClick={() => void analyze()} isLoading={analyzing} loadingText="Analyzing" isDisabled={analyzing || !analysisAllowed}>{item.global || item.lesion ? 'Analyze again' : 'Analyze'}</Button>}
          >
            {analyzing && <HStack color="status.info" mb={3}><Spinner size="sm" /><Text fontSize="sm">{progress}</Text></HStack>}
            {analysisError && <Alert status="error"><AlertIcon /><Stack spacing={2}><Text>{analysisError}</Text><Button size="sm" variant="outline" onClick={() => void analyze()}>Retry</Button></Stack></Alert>}
            {!analysisError && !analyzing && !admissionReady && (
              <Alert status="warning">
                <AlertIcon />
                <Stack spacing={2}>
                  <Text fontWeight="semibold">Needs image review</Text>
                  <Text fontSize="sm">Resolve this case from the Worklist before analysis.</Text>
                  <Button as={Link} to="/worklist" size="sm" variant="outline" alignSelf="flex-start">Open Worklist</Button>
                </Stack>
              </Alert>
            )}
            {!analysisError && !analyzing && admissionReady && (
              remoteNotConfigured ? <Text fontSize="sm" color="text.secondary">AI analysis is not available.</Text> : item.global || item.lesion ? <Text fontSize="sm" color="text.secondary">Actual returned results are shown below.</Text> : (
                <HStack spacing={2}>
                  <StatusBadge tone="success">Ready for analysis</StatusBadge>
                  <Text fontSize="sm" color="text.secondary">Not analyzed</Text>
                </HStack>
              )
            )}
          </Section>
          <Section title="DR assessment"><Assessment item={item} /></Section>
          <Section title="Lesion suggestions"><LesionSuggestions item={item} /></Section>
          <HStack spacing={2} flexWrap="wrap">
            <Button as={Link} to={`/edit/${encodeURIComponent(item.image_id)}`} leftIcon={<Pencil size={15} />} variant="secondary">Edit annotations</Button>
            <Button as={Link} to={`/clinician-review/${encodeURIComponent(item.image_id)}`} leftIcon={<UserRound size={15} />} variant="outline">Clinician review</Button>
          </HStack>
        </Stack>
      </Grid>
      <Box mt={5}><ModelStatus models={models} error={modelError} /></Box>
      {allWarnings.length > 0 && <ResultWarnings item={item} />}
    </Box>
  );
}
