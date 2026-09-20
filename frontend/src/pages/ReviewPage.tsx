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
  Input,
  Select,
  SimpleGrid,
  Spinner,
  Stack,
  Switch,
  Text,
  Textarea,
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { StatusBadge } from '@/components/common/StatusBadge';
import { RetinalCanvas, LESION_COLORS } from '@/components/review/RetinalCanvas';
import {
  admissionApi,
  apiJson,
  resolverApi,
  type AdmissionReviewAction,
  type CaseRecord,
  type Laterality,
  type ModelDescriptor,
} from '@/lib/api';
import { ArrowLeft, CheckCircle2, Pencil, Play, UserRound } from '@/lib/icons';

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'The request could not be completed.';
}

function ResultWarnings({ item }: { item: CaseRecord }) {
  const warnings = [...(item.global?.warnings ?? []), ...(item.lesion?.warnings ?? [])];
  if (warnings.length === 0) return null;
  return (
    <Alert status="warning" mt={4}>
      <AlertIcon />
      <Stack spacing={1}>
        <Text fontWeight="semibold">Model warnings</Text>
        {warnings.map((warning, index) => <Text key={`${warning}-${index}`} fontSize="sm">{warning}</Text>)}
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
                {model.status ?? 'Unknown'}
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
        <StatusBadge tone={item.global.state === 'AI_SUGGESTION' ? 'info' : 'warning'}>{item.global.state}</StatusBadge>
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
  const review = item.lesion_review;
  const lesions = review?.lesions ?? item.lesion.lesions;
  const counts = lesions.reduce<Record<string, number>>((result, lesion) => {
    result[lesion.canonical_label] = (result[lesion.canonical_label] ?? 0) + 1;
    return result;
  }, {});
  return (
    <Stack spacing={3}>
      <HStack justify="space-between">
        <Text color="text.secondary">Displayed suggestions</Text>
        <Text fontWeight="semibold">{review ? `${review.suggestion_count} of ${review.raw_count}` : lesions.length}</Text>
      </HStack>
      <Stack spacing={2}>
        <Text fontSize="sm" color="text.secondary">Suggested classes</Text>
        {Object.keys(counts).length ? Object.entries(counts).map(([label, count]) => (
          <HStack key={label} justify="space-between"><Text>{label}</Text><Badge variant="info">{count}</Badge></HStack>
        )) : <Text color="text.secondary">No lesion suggestions</Text>}
      </Stack>
      <Text fontSize="xs" color="text.muted">Model: {item.lesion.model_id} - {item.lesion.model_version}</Text>
    </Stack>
  );
}

function LesionLegend() {
  return (
    <HStack spacing={3} flexWrap="wrap" fontSize="xs" color="text.secondary">
      {Object.entries(LESION_COLORS).map(([label, color]) => (
        <HStack key={label} spacing={1}>
          <Box w="9px" h="9px" borderRadius="sm" bg={color} />
          <Text>{label.replace(/_/g, ' ')}</Text>
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

function ResolverReview({ item, onSaved }: { item: CaseRecord; onSaved: (saved: CaseRecord) => void }) {
  const ui = item.resolver_ui;
  const [reviewer, setReviewer] = useState('');
  const [patientKey, setPatientKey] = useState(item.patient_key ?? item.patient_candidate ?? '');
  const [laterality, setLaterality] = useState<Laterality>(item.laterality ?? 'UNKNOWN');
  const [saving, setSaving] = useState<'patient' | 'eye' | 'unlinked' | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPatientKey(item.patient_key ?? item.patient_candidate ?? '');
    setLaterality(item.laterality ?? 'UNKNOWN');
  }, [item.image_id, item.revision, item.patient_key, item.patient_candidate, item.laterality]);

  if (!ui) return null;

  const submit = async (kind: 'patient' | 'eye' | 'unlinked') => {
    if (saving) return;
    if (!reviewer.trim()) {
      setError('Reviewer name is required.');
      return;
    }
    setSaving(kind);
    setError(null);
    try {
      const confirmsCandidate = Boolean(
        kind === 'patient' &&
        item.patient_candidate &&
        !item.patient_key &&
        patientKey.trim() === item.patient_candidate,
      );
      const saved = await resolverApi.review(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        patient_action: kind === 'unlinked' ? 'LEAVE_UNLINKED' : kind === 'patient' ? (confirmsCandidate ? 'CONFIRM' : 'SET') : 'KEEP',
        patient_key: kind === 'patient' ? patientKey.trim() : undefined,
        laterality_action: kind === 'eye' ? 'SET' : 'KEEP',
        laterality: kind === 'eye' ? laterality : undefined,
      });
      onSaved(saved);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(null);
    }
  };

  const hasCandidate = Boolean(item.patient_candidate && !item.patient_key);
  return (
    <Section title="Patient and eye" description="Use a pseudonymous patient key. Patient assignment and eye side are saved independently.">
      <Stack spacing={3}>
        <HStack align="flex-start" spacing={3}>
          <Stack spacing={1} flex={1}>
            <StatusBadge tone={ui.patient.tone}>{ui.patient.label}</StatusBadge>
            <Text fontSize="sm" color="text.secondary">{ui.patient.note}</Text>
            {item.patient_key && <Text fontSize="sm">Current patient key: <strong>{item.patient_key}</strong></Text>}
            {!item.patient_key && ui.patient.candidate && <Text fontSize="sm">Suggested key: <strong>{ui.patient.candidate}</strong></Text>}
          </Stack>
        </HStack>
        <FormControl isRequired>
          <FormLabel>Pseudonymous patient key</FormLabel>
          <Input id="resolver-patient-key" value={patientKey} onChange={(event) => setPatientKey(event.target.value.toUpperCase())} placeholder="PAT0001" />
        </FormControl>
        <FormControl isRequired>
          <FormLabel>Reviewer name</FormLabel>
          <Input id="resolver-reviewer" value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Enter reviewer name" />
        </FormControl>
        <HStack spacing={2} flexWrap="wrap">
          <Button onClick={() => void submit('patient')} isLoading={saving === 'patient'} isDisabled={Boolean(saving)}>
            {hasCandidate ? 'Confirm patient' : 'Save patient assignment'}
          </Button>
          <Button variant="ghost" onClick={() => void submit('unlinked')} isLoading={saving === 'unlinked'} isDisabled={Boolean(saving)}>
            Leave patient unlinked
          </Button>
        </HStack>
        <Box borderTopWidth="1px" borderColor="border.subtle" pt={3}>
          <Stack spacing={2}>
            <HStack justify="space-between" align="flex-start">
              <Stack spacing={1}>
                <StatusBadge tone={ui.laterality.tone}>{ui.laterality.label}</StatusBadge>
                <Text fontSize="sm" color="text.secondary">{ui.laterality.note}</Text>
              </Stack>
            </HStack>
            <FormControl>
              <FormLabel>Eye side</FormLabel>
              <Select value={laterality} onChange={(event) => setLaterality(event.target.value as Laterality)}>
                <option value="UNKNOWN">Unknown</option>
                <option value="LEFT">Left</option>
                <option value="RIGHT">Right</option>
              </Select>
            </FormControl>
            <Button alignSelf="flex-start" variant="secondary" onClick={() => void submit('eye')} isLoading={saving === 'eye'} isDisabled={Boolean(saving)}>
              Save eye side
            </Button>
          </Stack>
        </Box>
        {error && <Alert status="error"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
      </Stack>
    </Section>
  );
}

function AdmissionReview({ item, onSaved }: { item: CaseRecord; onSaved: (saved: CaseRecord) => void }) {
  const [reviewer, setReviewer] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState<AdmissionReviewAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const admission = item.admission;
  const ui = item.admission_ui;
  const isReadable = Boolean(item.image_url && admission && admission.modality_admission !== 'REJECTED_INVALID');

  const submit = async (action: AdmissionReviewAction) => {
    if (!admission || saving) return;
    if (!reviewer.trim()) {
      setError('Reviewer name is required.');
      return;
    }
    setSaving(action);
    setError(null);
    try {
      const saved = await admissionApi.review(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        action,
        note: note.trim(),
      });
      onSaved(saved);
      setNote('');
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(null);
    }
  };

  if (!ui || !admission) return null;
  return (
    <Section title="Image admission" description="Confirm that this file is suitable for retinal DR analysis before running models.">
      <Stack spacing={3}>
        <HStack align="flex-start" spacing={3}>
          <CheckCircle2 size={18} aria-hidden="true" />
          <Stack spacing={1}>
            <StatusBadge tone={ui.tone}>{ui.label}</StatusBadge>
            <Text fontSize="sm" color="text.secondary">{ui.note}</Text>
          </Stack>
        </HStack>
        {isReadable && (
          <>
            <FormControl isRequired>
              <FormLabel>Reviewer name</FormLabel>
              <Input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Enter reviewer name" />
            </FormControl>
            <FormControl>
              <FormLabel>Review note</FormLabel>
              <Textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add a short reason" rows={3} />
            </FormControl>
            {error && <Alert status="error"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
            <Stack spacing={2}>
              {admission.modality_admission !== 'FUNDUS_ACCEPTED' && (
                <Button variant="solid" onClick={() => void submit('ACCEPT_RETINAL')} isLoading={saving === 'ACCEPT_RETINAL'} isDisabled={Boolean(saving)}>
                  Accept as retinal fundus image
                </Button>
              )}
              {admission.modality_admission !== 'REJECTED_NON_FUNDUS' && (
                <Button variant="outline" onClick={() => void submit('MARK_NON_FUNDUS')} isLoading={saving === 'MARK_NON_FUNDUS'} isDisabled={Boolean(saving)}>
                  Mark as non-fundus
                </Button>
              )}
              <HStack spacing={2} flexWrap="wrap">
                <Button size="sm" variant="secondary" onClick={() => void submit('QUALITY_ACCEPTABLE')} isLoading={saving === 'QUALITY_ACCEPTABLE'} isDisabled={Boolean(saving)}>
                  Mark quality acceptable
                </Button>
                <Button size="sm" variant="outline" onClick={() => void submit('QUALITY_INADEQUATE')} isLoading={saving === 'QUALITY_INADEQUATE'} isDisabled={Boolean(saving)}>
                  Mark quality inadequate
                </Button>
              </HStack>
              {ui.action_required && (
                <Button size="sm" variant="ghost" onClick={() => void submit('LEAVE_UNRESOLVED')} isLoading={saving === 'LEAVE_UNRESOLVED'} isDisabled={Boolean(saving)}>
                  Leave unresolved
                </Button>
              )}
            </Stack>
          </>
        )}
      </Stack>
    </Section>
  );
}

export function ReviewPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { imageId } = useParams<{ imageId: string }>();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [models, setModels] = useState<ModelDescriptor[]>([]);
  const [showAi, setShowAi] = useState(true);
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
  const analysisAllowed = admissionAllowsAnalysis(item) && !remoteNotConfigured;

  if (!imageId) {
    return (
      <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
        <PageHeader pathname={pathname} title="AI Review" />
        <Section title="Select an admitted case" description="Choose an image from the Worklist to open AI review." action={<Button as={Link} to="/worklist">Open Worklist</Button>}>
          <Text color="text.secondary">No image was selected.</Text>
        </Section>
      </Box>
    );
  }

  if (loading && !item) return <Center minH="360px"><Spinner color="action.primary" /></Center>;

  if (error || !item) {
    return (
      <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
        <PageHeader pathname={pathname} title="AI Review" />
        <Alert status="error"><AlertIcon /><Text>{error ?? 'Case unavailable.'}</Text></Alert>
        <Button mt={4} leftIcon={<ArrowLeft size={15} />} onClick={() => navigate('/worklist')}>Back to Worklist</Button>
      </Box>
    );
  }

  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader
        pathname={pathname}
        title="AI Review"
        subtitle={`${item.display_name} - model suggestions for clinician inspection`}
        actions={<Button as={Link} to="/worklist" leftIcon={<ArrowLeft size={15} />}>Back to Worklist</Button>}
      />
      <Grid templateColumns={{ base: '1fr', laptop: 'minmax(0, 1.35fr) minmax(320px, 0.65fr)' }} gap={5} alignItems="start">
        <Section title="Retinal preview" description={`${item.width} x ${item.height}px - ${item.modality}`}>
          {item.image_url ? <RetinalCanvas item={item} showAi={showAi} showHuman={false} /> : (
            <Alert status="error"><AlertIcon /><Text>{item.admission_ui?.note ?? 'This file has no readable image preview.'}</Text></Alert>
          )}
          <Stack spacing={3} mt={4}>
            <HStack justify="space-between" align="center" flexWrap="wrap" gap={2}>
              <FormControl display="flex" alignItems="center" w="auto">
                <Switch id="show-ai-suggestions" isChecked={showAi} onChange={(event) => setShowAi(event.target.checked)} mr={2} />
                <FormLabel htmlFor="show-ai-suggestions" mb={0} fontSize="sm">Show AI suggestions</FormLabel>
              </FormControl>
              <Text fontSize="xs" color="text.secondary">
                Displayed {item.lesion_review?.suggestion_count ?? 0} of {item.lesion_review?.raw_count ?? 0} raw suggestions
              </Text>
            </HStack>
            <LesionLegend />
          </Stack>
          <SimpleGrid columns={{ base: 1, tablet: 3 }} spacing={3} mt={4} fontSize="sm">
            <Stack spacing={1}><Text color="text.secondary">Image ID</Text><Code fontSize="xs" whiteSpace="normal">{item.image_id}</Code></Stack>
            <Stack spacing={1}><Text color="text.secondary">Dimensions</Text><Text>{item.width} x {item.height}px</Text></Stack>
            <Stack spacing={1}><Text color="text.secondary">Source</Text><Text>{item.source}</Text></Stack>
          </SimpleGrid>
        </Section>
        <Stack spacing={5}>
          <Section
            title="Analysis"
            description="Run both existing remote inference contracts on this admitted image."
            action={<Button variant="solid" leftIcon={<Play size={15} />} onClick={() => void analyze()} isLoading={analyzing} loadingText="Analyzing" isDisabled={analyzing || !analysisAllowed}>{item.global || item.lesion ? 'Analyze again' : 'Analyze'}</Button>}
          >
            {analyzing && <HStack color="status.info" mb={3}><Spinner size="sm" /><Text fontSize="sm">{progress}</Text></HStack>}
            {analysisError && <Alert status="error"><AlertIcon /><Stack spacing={2}><Text>{analysisError}</Text><Button size="sm" variant="outline" onClick={() => void analyze()}>Retry</Button></Stack></Alert>}
            {!analysisError && !analyzing && <Text fontSize="sm" color="text.secondary">
              {!admissionAllowsAnalysis(item) ? 'Resolve the image admission review before analysis.' : remoteNotConfigured ? 'AI analysis is not available.' : item.global || item.lesion ? 'Actual returned results are shown below.' : 'Not analyzed'}
            </Text>}
          </Section>
          <ResolverReview item={item} onSaved={setItem} />
          <AdmissionReview item={item} onSaved={setItem} />
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
