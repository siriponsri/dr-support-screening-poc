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
  Grid,
  Heading,
  HStack,
  Image,
  SimpleGrid,
  Spinner,
  Stack,
  Text,
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { StatusBadge } from '@/components/common/StatusBadge';
import { apiJson, type CaseRecord, type ModelDescriptor } from '@/lib/api';
import { ArrowLeft, Play } from '@/lib/icons';

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
      <Text fontSize="xs" color="text.muted">Model: {item.global.model_id} · {item.global.model_version}</Text>
    </Stack>
  );
}

function LesionSuggestions({ item }: { item: CaseRecord }) {
  if (!item.lesion) return <Text color="text.secondary">Not analyzed</Text>;
  const counts = item.lesion.lesions.reduce<Record<string, number>>((result, lesion) => {
    result[lesion.canonical_label] = (result[lesion.canonical_label] ?? 0) + 1;
    return result;
  }, {});
  return (
    <Stack spacing={3}>
      <HStack justify="space-between">
        <Text color="text.secondary">Suggestion count</Text>
        <Text fontWeight="semibold">{item.lesion.lesions.length}</Text>
      </HStack>
      <Stack spacing={2}>
        <Text fontSize="sm" color="text.secondary">Suggested classes</Text>
        {Object.keys(counts).length ? Object.entries(counts).map(([label, count]) => (
          <HStack key={label} justify="space-between"><Text>{label}</Text><Badge variant="info">{count}</Badge></HStack>
        )) : <Text color="text.secondary">No lesion suggestions</Text>}
      </Stack>
      <Text fontSize="xs" color="text.muted">Model: {item.lesion.model_id} · {item.lesion.model_version}</Text>
    </Stack>
  );
}

export function ReviewPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { imageId } = useParams<{ imageId: string }>();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [models, setModels] = useState<ModelDescriptor[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
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

  useEffect(() => {
    void loadCase();
    void apiJson<ModelDescriptor[]>('/v1/models')
      .then((loaded) => { setModels(loaded); setModelError(null); })
      .catch((err) => setModelError(errorText(err)));
  }, [loadCase]);

  const analyze = async () => {
    if (!item || analyzing) return;
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const request = (model_id: string) => apiJson<unknown>(
        `/v1/infer/${model_id === 'retfound-aptos5' ? 'global' : 'lesion-roi'}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_id: item.image_id, modality: item.modality, model_id }),
        },
      );
      await Promise.all([request('retfound-aptos5'), request('prism-dr-5fold')]);
      setItem(await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(item.image_id)}`));
      setModels(await apiJson<ModelDescriptor[]>('/v1/models'));
      setModelError(null);
    } catch (err) {
      setAnalysisError(errorText(err));
    } finally {
      setAnalyzing(false);
    }
  };

  const allWarnings = useMemo(() => item ? [...(item.global?.warnings ?? []), ...(item.lesion?.warnings ?? [])] : [], [item]);

  if (!imageId) {
    return (
      <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
        <PageHeader pathname={pathname} />
        <Section title="Select an admitted case" description="Choose an image from the Worklist to open review." action={<Button as={Link} to="/worklist">Open Worklist</Button>}>
          <Text color="text.secondary">No image was selected.</Text>
        </Section>
      </Box>
    );
  }

  if (loading && !item) return <Center minH="360px"><Spinner color="brand.500" /></Center>;

  if (error || !item) {
    return (
      <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
        <PageHeader pathname={pathname} />
        <Alert status="error"><AlertIcon /><Text>{error ?? 'Case unavailable.'}</Text></Alert>
        <Button mt={4} leftIcon={<ArrowLeft size={15} />} onClick={() => navigate('/worklist')}>Back to Worklist</Button>
      </Box>
    );
  }

  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} title={item.display_name} subtitle="Retinal image review and model suggestions" actions={<Button as={Link} to="/worklist" leftIcon={<ArrowLeft size={15} />}>Back to Worklist</Button>} />
      <Grid templateColumns={{ base: '1fr', laptop: 'minmax(0, 1.35fr) minmax(320px, 0.65fr)' }} gap={5} alignItems="start">
        <Section title="Retinal preview" description={`${item.width} × ${item.height}px · ${item.modality}`}>
          <Box bg="gray.950" borderRadius="md" minH={{ base: '280px', laptop: '520px' }} display="grid" placeItems="center" overflow="hidden">
            <Image src={item.image_url} alt={`${item.display_name} retinal image`} maxH="70vh" w="100%" objectFit="contain" />
          </Box>
          <SimpleGrid columns={{ base: 1, tablet: 3 }} spacing={3} mt={4} fontSize="sm">
            <Stack spacing={1}><Text color="text.secondary">Image ID</Text><Code fontSize="xs" whiteSpace="normal">{item.image_id}</Code></Stack>
            <Stack spacing={1}><Text color="text.secondary">Dimensions</Text><Text>{item.width} × {item.height}px</Text></Stack>
            <Stack spacing={1}><Text color="text.secondary">Source</Text><Text>{item.source}</Text></Stack>
          </SimpleGrid>
        </Section>
        <Stack spacing={5}>
          <Section title="Analysis" description="Run both existing remote inference contracts on this admitted image." action={<Button colorScheme="red" leftIcon={<Play size={15} />} onClick={() => void analyze()} isLoading={analyzing} loadingText="Analyzing" isDisabled={analyzing}>{item.global || item.lesion ? 'Analyze again' : 'Analyze'}</Button>}>
            {analyzing && <HStack color="status.info" mb={3}><Spinner size="sm" /><Text fontSize="sm">Running RETFound and PRISM-DR...</Text></HStack>}
            {analysisError && <Alert status="error"><AlertIcon /><Stack spacing={2}><Text>{analysisError}</Text><Button size="sm" variant="outline" onClick={() => void analyze()}>Retry</Button></Stack></Alert>}
            {!analysisError && !analyzing && <Text fontSize="sm" color="text.secondary">{item.global || item.lesion ? 'Returned results are shown below.' : 'Not analyzed'}</Text>}
          </Section>
          <Section title="DR assessment"><Assessment item={item} /></Section>
          <Section title="Lesion suggestions"><LesionSuggestions item={item} /></Section>
        </Stack>
      </Grid>
      <Box mt={5}><ModelStatus models={models} error={modelError} /></Box>
      {allWarnings.length > 0 && <ResultWarnings item={item} />}
    </Box>
  );
}
