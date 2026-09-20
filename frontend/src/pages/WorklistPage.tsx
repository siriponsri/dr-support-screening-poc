import { useEffect, useState } from 'react';
import { Alert, AlertIcon, Box, Button, Center, HStack, Spinner, Stack, Text, VStack } from '@chakra-ui/react';
import { useLocation } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { admissionApi, apiJson, queueApi, type CaseRecord } from '@/lib/api';
import { RefreshCw, ScanLine } from '@/lib/icons';
import { ResolverDialog } from '@/components/worklist/ResolverDialog';
import { WorklistTable } from '@/components/worklist/WorklistTable';

export function WorklistPage() {
  const { pathname } = useLocation();
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanNotice, setScanNotice] = useState<string | null>(null);
  const [resolverCase, setResolverCase] = useState<CaseRecord | null>(null);

  const loadCases = async () => {
    setLoading(true);
    setError(null);
    try { setCases(await apiJson<CaseRecord[]>('/v1/cases')); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to load cases.'); }
    finally { setLoading(false); }
  };

  const scanInput = async () => {
    if (scanning) return;
    setScanning(true); setError(null); setScanNotice(null);
    try {
      const result = await admissionApi.scan();
      await loadCases();
      setScanNotice(result.warnings.length ? result.warnings.join(' ') : `Scanned ${result.records.length} input files.`);
    } catch (err) { setError(err instanceof Error ? err.message : 'The input folder could not be scanned.'); }
    finally { setScanning(false); }
  };

  const updateQueue = async (item: CaseRecord, action: 'EXCLUDE' | 'RESTORE') => {
    setError(null);
    try {
      const saved = await queueApi.update(item.image_id, { revision: item.revision, action });
      setCases((current) => current.map((entry) => entry.image_id === saved.image_id ? saved : entry));
    } catch (err) { setError(err instanceof Error ? err.message : 'The queue state could not be updated.'); }
  };

  useEffect(() => { void loadCases(); }, []);

  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} subtitle="Admitted retinal images for clinician review" />
      <Section title="Worklist" description="Review admitted images, resolve patient and eye identity, and keep AI assistance separate from the clinician decision." action={<HStack spacing={2} width={{ base: '100%', tablet: 'auto' }} justifyContent={{ base: 'flex-start', tablet: 'flex-end' }} flexWrap="wrap"><Button leftIcon={<ScanLine size={15} />} onClick={() => void scanInput()} isLoading={scanning}>Scan input folder</Button><Button variant="outline" leftIcon={<RefreshCw size={15} />} onClick={() => void loadCases()} isLoading={loading}>Refresh</Button></HStack>}>
        {error && <Alert status="error" mb={4}><AlertIcon /><Text>{error}</Text></Alert>}
        {scanNotice && <Alert status="info" mb={4}><AlertIcon /><Text>{scanNotice}</Text></Alert>}
        {loading && cases.length === 0 ? (
          <Center py={12}><VStack spacing={3}><Spinner color="action.primary" /><Text color="text.secondary">Loading cases...</Text></VStack></Center>
        ) : cases.length === 0 ? (
          <Box borderWidth="1px" borderStyle="dashed" borderColor="border.default" bg="surface.subtle" p={5}><Stack spacing={1}><Text fontWeight="semibold">No images in this workspace</Text><Text fontSize="sm" color="text.secondary">Add images to the input folder, then scan the folder.</Text></Stack></Box>
        ) : (
          <WorklistTable cases={cases} onResolve={setResolverCase} onQueueAction={(item, action) => void updateQueue(item, action)} />
        )}
      </Section>
      <HStack mt={4} spacing={2} color="text.muted" fontSize="xs"><Text>AI suggestions require clinician review.</Text></HStack>
      <ResolverDialog item={resolverCase} onClose={() => setResolverCase(null)} onSaved={(saved) => setCases((current) => current.map((entry) => entry.image_id === saved.image_id ? saved : entry))} />
    </Box>
  );
}
