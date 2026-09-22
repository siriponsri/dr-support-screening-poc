import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Code,
  Center,
  HStack,
  Select,
  SimpleGrid,
  Spinner,
  Stack,
  Text,
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { StatusBadge } from '@/components/common/StatusBadge';
import { RetinalCanvas } from '@/components/review/RetinalCanvas';
import { apiJson, type CaseRecord, type GlobalResult, type LesionResult, type ModelDescriptor, type Provenance } from '@/lib/api';

function errorText(err: unknown) {
  return err instanceof Error ? err.message : 'The request could not be completed.';
}

function Metadata({ result, descriptor }: { result: GlobalResult | LesionResult | null; descriptor?: ModelDescriptor }) {
  const provenance: Provenance | undefined = result?.provenance;
  return (
    <Stack spacing={2} fontSize="sm">
      <HStack justify="space-between"><Text color="text.secondary">Model id</Text><Text fontWeight="semibold">{result?.model_id ?? descriptor?.model_id ?? 'Not reported'}</Text></HStack>
      <HStack justify="space-between"><Text color="text.secondary">Revision</Text><Text>{result?.model_version ?? descriptor?.revision ?? 'Not reported'}</Text></HStack>
      <HStack justify="space-between"><Text color="text.secondary">Task</Text><Text>{descriptor?.task ?? (result && 'lesions' in result ? 'lesion-roi' : 'global')}</Text></HStack>
      <HStack justify="space-between"><Text color="text.secondary">Runtime / status</Text><Text>{descriptor?.runtime ?? 'remote'} - {descriptor?.status ?? result?.state ?? 'Not reported'}</Text></HStack>
      <HStack justify="space-between" align="flex-start"><Text color="text.secondary">Preprocessing</Text><Text textAlign="right" maxW="65%">{provenance?.preprocessing ?? descriptor?.preprocessing ?? 'Not reported by the current contract'}</Text></HStack>
      {provenance && <HStack justify="space-between" align="flex-start"><Text color="text.secondary">Provenance</Text><Text textAlign="right" maxW="65%" fontSize="xs">{provenance.source_type} - {provenance.source_revision} - image {provenance.image_sha256.slice(0, 12)}...</Text></HStack>}
    </Stack>
  );
}

function Warnings({ warnings }: { warnings: string[] }) {
  return warnings.length ? <Alert status="warning" mt={4}><AlertIcon /><Stack spacing={1}>{warnings.map((warning, index) => <Text key={`${warning}-${index}`} fontSize="sm">{warning}</Text>)}</Stack></Alert> : null;
}

function eventValue(event: Record<string, unknown>, key: string) {
  const value = event[key];
  return typeof value === 'string' || typeof value === 'number' ? String(value) : null;
}

function CaseLineage({ item }: { item: CaseRecord }) {
  const sourceSha = item.source_sha256 ?? item.review_evidence?.source_sha256 ?? null;
  const analysisSha = item.analysis_derivative?.analysis_sha256 ?? item.review_evidence?.analysis_sha256 ?? null;
  const inferenceEvents = (item.events ?? []).filter((event) => event.action === 'INFERENCE');
  const aiCount = item.lesion?.lesions.length ?? item.review_evidence?.items.filter((entry) => entry.source === 'AI').length ?? 0;
  const cvatCount = item.annotations?.length ?? 0;

  return (
    <Section title="Case lineage & annotation provenance" description="Read-only evidence for this case. Hashes identify the source and exact analysis bytes; counts do not establish accuracy.">
      <Stack spacing={4} minW={0}>
        <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={3}>
          <Stack spacing={1} minW={0}>
            <Text fontSize="sm" color="text.secondary">Source SHA-256</Text>
            {sourceSha ? <Code fontSize="xs" whiteSpace="normal" wordBreak="break-all">{sourceSha}</Code> : <Text fontSize="sm">Not recorded</Text>}
          </Stack>
          <Stack spacing={1} minW={0}>
            <Text fontSize="sm" color="text.secondary">Analysis SHA-256</Text>
            {analysisSha ? <Code fontSize="xs" whiteSpace="normal" wordBreak="break-all">{analysisSha}</Code> : <Text fontSize="sm">Not recorded</Text>}
          </Stack>
        </SimpleGrid>
        <SimpleGrid columns={{ base: 1, tablet: 3 }} spacing={3}>
          <Stack spacing={1}><Text fontSize="sm" color="text.secondary">AI visual evidence</Text><Text fontSize="xl" fontWeight="semibold">{aiCount}</Text></Stack>
          <Stack spacing={1}><Text fontSize="sm" color="text.secondary">Human annotations</Text><Text fontSize="xl" fontWeight="semibold">{item.human_annotations.length}</Text></Stack>
          <Stack spacing={1}><Text fontSize="sm" color="text.secondary">CVAT imported</Text><Text fontSize="xl" fontWeight="semibold">{cvatCount}</Text></Stack>
        </SimpleGrid>
        <Stack spacing={2} minW={0}>
          <Text fontSize="sm" color="text.secondary">Inference metadata</Text>
          {inferenceEvents.length ? inferenceEvents.map((event, index) => {
            const modelId = eventValue(event, 'model_id') ?? 'Model not reported';
            const model = modelId === item.global?.model_id ? item.global : modelId === item.lesion?.model_id ? item.lesion : null;
            const revision = model?.model_version ?? 'Revision not reported';
            const runtime = eventValue(event, 'runtime');
            const latency = eventValue(event, 'latency_ms');
            const timestamp = eventValue(event, 'timestamp');
            return (
              <Box key={`${modelId}-${index}`} borderWidth="1px" borderColor="border.subtle" borderRadius="md" p={3} minW={0}>
                <HStack justify="space-between" align="flex-start" flexWrap="wrap" gap={2}>
                  <Text fontWeight="semibold">{modelId}</Text>
                  <Text fontSize="sm" color="text.secondary">{revision}</Text>
                </HStack>
                <Text fontSize="xs" color="text.muted">
                  {[runtime && `Runtime ${runtime}`, latency && `Latency ${latency} ms`, timestamp && new Date(timestamp).toLocaleString()].filter(Boolean).join(' - ') || 'Event metadata recorded without runtime details.'}
                </Text>
              </Box>
            );
          }) : <Text fontSize="sm" color="text.secondary">No inference events recorded for this case.</Text>}
        </Stack>
        {item.analysis_derivative && <Stack spacing={1} minW={0}>
          <Text fontSize="sm" color="text.secondary">Analysis transform</Text>
          <Text fontSize="sm">{item.analysis_derivative.transform_id} - {item.analysis_derivative.lineage.coordinate_space}</Text>
          <Text fontSize="xs" color="text.muted">{item.analysis_derivative.transform_description}</Text>
        </Stack>}
      </Stack>
    </Section>
  );
}

function ProbabilityBars({ result }: { result: GlobalResult }) {
  if (!result.probabilities.length) return <Text color="text.secondary">No probability distribution returned.</Text>;
  return (
    <Stack spacing={2}>
      {result.probabilities.map((probability, grade) => (
        <HStack key={grade} spacing={3}>
          <Text w="52px" fontSize="sm">Grade {grade}</Text>
          <Box flex={1} h="8px" bg="surface.muted" borderRadius="sm" overflow="hidden"><Box h="100%" w={`${probability * 100}%`} bg={grade === result.grade ? 'action.primary' : 'status.info'} /></Box>
          <Text w="48px" textAlign="right" fontSize="sm">{(probability * 100).toFixed(1)}%</Text>
        </HStack>
      ))}
    </Stack>
  );
}

function ModelDescriptorGrid({ models }: { models: ModelDescriptor[] }) {
  const relevant = models.filter((model) => ['retfound-aptos5', 'prism-dr-5fold'].includes(model.model_id));
  return (
    <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={3}>
      {relevant.map((model) => (
        <Box key={model.model_id} borderWidth="1px" borderColor="border.subtle" borderRadius="md" p={3}>
          <HStack justify="space-between" align="flex-start"><Text fontWeight="semibold">{model.model_id}</Text><StatusBadge tone={model.status === 'LOADED' ? 'success' : 'warning'}>{model.status ?? 'Unknown'}</StatusBadge></HStack>
          <Text mt={1} fontSize="xs" color="text.secondary">{model.task} - {model.runtime ?? 'runtime not reported'}</Text>
          {model.warnings?.length ? <Text mt={2} fontSize="xs" color="text.secondary">{model.warnings[0]}</Text> : null}
        </Box>
      ))}
    </SimpleGrid>
  );
}

function PrismEvidence({ item, result }: { item: CaseRecord; result: LesionResult | null }) {
  if (!result) return <Text color="text.secondary">No PRISM result is available for this case.</Text>;
  const bounded = item.lesion_review?.lesions ?? result.lesions;
  const counts = bounded.reduce<Record<string, number>>((all, lesion) => {
    all[lesion.canonical_label] = (all[lesion.canonical_label] ?? 0) + 1;
    return all;
  }, {});
  const scores = bounded.map((lesion) => lesion.score);
  return (
    <Stack spacing={4}>
      <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={4}>
        <Stack spacing={2}><Text color="text.secondary">Raw lesion count</Text><Text fontSize="2xl" fontWeight="semibold">{result.lesions.length}</Text></Stack>
        <Stack spacing={2}><Text color="text.secondary">Bounded review count</Text><Text fontSize="2xl" fontWeight="semibold">{item.lesion_review?.suggestion_count ?? bounded.length}</Text></Stack>
      </SimpleGrid>
      <Stack spacing={2}><Text fontSize="sm" color="text.secondary">Lesion count by class</Text>{Object.keys(counts).length ? Object.entries(counts).map(([label, count]) => <HStack key={label} justify="space-between"><Text>{label}</Text><Badge variant="info">{count}</Badge></HStack>) : <Text color="text.secondary">No localized lesions.</Text>}</Stack>
      <Stack spacing={2}><Text fontSize="sm" color="text.secondary">Score information</Text><Text fontSize="sm">{scores.length ? `Bounded score range ${(Math.min(...scores) * 100).toFixed(1)}-${(Math.max(...scores) * 100).toFixed(1)}%` : 'No lesion scores returned.'}</Text></Stack>
      <Box><Text fontSize="sm" color="text.secondary" mb={2}>Localized visual evidence</Text><RetinalCanvas item={item} showAi humanAnnotations={[]} showHuman={false} /></Box>
      <Warnings warnings={result.warnings} />
    </Stack>
  );
}

export function ModelsPage() {
  const { pathname } = useLocation();
  const [models, setModels] = useState<ModelDescriptor[]>([]);
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([
      apiJson<ModelDescriptor[]>('/v1/models'),
      apiJson<CaseRecord[]>('/v1/cases'),
    ]).then(([loadedModels, loadedCases]) => {
      setModels(loadedModels);
      setCases(loadedCases);
      setSelectedId((current) => current || loadedCases[0]?.image_id || '');
    }).catch((err) => setError(errorText(err)));
  }, []);

  const item = useMemo(() => cases.find((entry) => entry.image_id === selectedId) ?? cases[0], [cases, selectedId]);
  const retfound = models.find((model) => model.model_id === 'retfound-aptos5');
  const prism = models.find((model) => model.model_id === 'prism-dr-5fold');
  const globalWarnings = item?.global?.warnings ?? [];

  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} title="Model Audit & Explainability" subtitle="Actual model metadata, case results, and bounded visual evidence" />
      {error && <Alert status="error" mb={5}><AlertIcon /><Text>{error}</Text></Alert>}
      <Stack spacing={5} minW={0}>
        <Section title="Model readiness" description="Metadata is read from the existing /v1/models contract; unavailable remote state is shown honestly.">
          <ModelDescriptorGrid models={models} />
        </Section>
        <Section title="Case context" description="Choose a returned case to inspect its actual inference metadata and results.">
          {cases.length ? <Select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{cases.map((entry) => <option key={entry.image_id} value={entry.image_id}>{entry.display_name} - {entry.image_id}</option>)}</Select> : <Center py={8}><Spinner color="action.primary" /></Center>}
        </Section>
        {item && (
          <SimpleGrid columns={{ base: 1, laptop: 2 }} spacing={5} minW={0}>
            <Section title="RETFound - Score-level decision context" description="No saliency explanation is produced by the current RETFound bridge.">
              <Stack spacing={4}>
                <Metadata result={item.global} descriptor={retfound} />
                {item.global ? <>
                  <HStack justify="space-between"><Text color="text.secondary">Predicted grade</Text><Text fontSize="xl" fontWeight="semibold">{item.global.grade === null ? item.global.state : `Grade ${item.global.grade}`}</Text></HStack>
                  <HStack justify="space-between"><Text color="text.secondary">Confidence / model score</Text><Text fontWeight="semibold">{item.global.confidence === null ? 'Not returned' : `${(item.global.confidence * 100).toFixed(1)}%`}</Text></HStack>
                  <Box><Text fontSize="sm" color="text.secondary" mb={2}>Probability distribution - Grades 0-4</Text><ProbabilityBars result={item.global} /></Box>
                  <Warnings warnings={globalWarnings} />
                </> : <Text color="text.secondary">Not analyzed for this case.</Text>}
              </Stack>
            </Section>
            <Section title="PRISM-DR - Localized visual evidence" description="Bounded clinician-facing lesion suggestions are shown without changing raw provider output.">
              <Metadata result={item.lesion} descriptor={prism} />
              <PrismEvidence item={item} result={item.lesion} />
            </Section>
          </SimpleGrid>
        )}
        {item && <CaseLineage item={item} />}
        <Alert status="info"><AlertIcon /><Text fontSize="sm">AI outputs support clinician review and are not ground truth.</Text></Alert>
      </Stack>
    </Box>
  );
}
