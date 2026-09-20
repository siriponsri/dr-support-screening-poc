import { useEffect, useState } from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Center,
  Code,
  HStack,
  Image,
  Spinner,
  Stack,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from '@chakra-ui/react';
import { Link, useLocation } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';
import { admissionApi, apiJson, type CaseRecord } from '@/lib/api';
import { FileImage, RefreshCw, ScanLine } from '@/lib/icons';

function analysisStatus(item: CaseRecord): { label: string; tone: StatusTone } {
  if (item.global && item.lesion) return { label: 'Complete', tone: 'success' };
  if (item.global || item.lesion) return { label: 'Partial', tone: 'warning' };
  return { label: 'Not analyzed', tone: 'neutral' };
}

function reviewStatus(item: CaseRecord): { label: string; tone: StatusTone } {
  if (item.state === 'REVIEWED') return { label: 'Reviewed', tone: 'success' };
  if (item.state === 'NEEDS_CORRECTION') return { label: 'Needs correction', tone: 'danger' };
  if (item.state === 'ESCALATED') return { label: 'Escalated', tone: 'warning' };
  return { label: 'Pending review', tone: 'neutral' };
}

function admissionStatus(item: CaseRecord): { label: string; tone: StatusTone; note: string } {
  if (!item.admission_ui) return { label: 'Needs review', tone: 'warning', note: 'Please confirm this image before analysis.' };
  return {
    label: item.admission_ui.label,
    tone: item.admission_ui.tone,
    note: item.admission_ui.note,
  };
}

export function WorklistPage() {
  const { pathname } = useLocation();
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanNotice, setScanNotice] = useState<string | null>(null);

  const loadCases = async () => {
    setLoading(true);
    setError(null);
    try {
      setCases(await apiJson<CaseRecord[]>('/v1/cases'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load admitted cases.');
    } finally {
      setLoading(false);
    }
  };

  const scanInput = async () => {
    if (scanning) return;
    setScanning(true);
    setError(null);
    setScanNotice(null);
    try {
      const result = await admissionApi.scan();
      await loadCases();
      setScanNotice(result.warnings.length ? result.warnings.join(' ') : `Scanned ${result.records.length} input files.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The input folder could not be scanned.');
    } finally {
      setScanning(false);
    }
  };

  useEffect(() => {
    void loadCases();
  }, []);

  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} subtitle="Admitted retinal images for clinician review" />
      <Section
        title="Admitted cases"
        description="Select an image to inspect the retinal preview and run the configured remote models."
        action={
          <HStack spacing={2}>
            <Button leftIcon={<ScanLine size={15} />} onClick={() => void scanInput()} isLoading={scanning}>
              Scan input folder
            </Button>
            <Button variant="outline" leftIcon={<RefreshCw size={15} />} onClick={() => void loadCases()} isLoading={loading}>
              Refresh
            </Button>
          </HStack>
        }
      >
        {error && (
          <Alert status="error" mb={4}>
            <AlertIcon />
            <Text>{error}</Text>
          </Alert>
        )}
        {scanNotice && <Alert status="info" mb={4}><AlertIcon /><Text>{scanNotice}</Text></Alert>}
        {loading && cases.length === 0 ? (
          <Center py={12}>
            <VStack spacing={3}>
              <Spinner color="action.primary" />
              <Text color="text.secondary">Loading admitted cases...</Text>
            </VStack>
          </Center>
        ) : cases.length === 0 ? (
          <Text color="text.secondary">No admitted images are available.</Text>
        ) : (
          <TableContainer>
            <Table variant="clinical" size="sm">
              <Thead>
                <Tr>
                  <Th>Preview</Th>
                  <Th>Image ID</Th>
                  <Th>AI grade</Th>
                  <Th>Review status</Th>
                  <Th>Image admission</Th>
                  <Th>Analysis status</Th>
                  <Th isNumeric>Review action</Th>
                </Tr>
              </Thead>
              <Tbody>
                {cases.map((item) => {
                  const analysis = analysisStatus(item);
                  const review = reviewStatus(item);
                  const admission = admissionStatus(item);
                  return (
                    <Tr key={item.image_id} data-testid={`case-row-${item.display_name}`}>
                      <Td>
                        {item.image_url ? (
                          <Image
                            src={item.image_url}
                            alt={`${item.display_name} retinal preview`}
                            w="88px"
                            h="64px"
                            objectFit="contain"
                            bg="surface.viewer"
                            borderRadius="sm"
                          />
                        ) : (
                          <Box aria-label="No image preview" w="88px" h="64px" bg="surface.subtle" borderRadius="sm" display="flex" alignItems="center" justifyContent="center" flexDirection="column" gap={1}>
                            <FileImage size={18} aria-hidden="true" />
                            <Text fontSize="xxs">No preview</Text>
                          </Box>
                        )}
                      </Td>
                      <Td>
                        <Stack spacing={1}>
                          <Text fontWeight="semibold">{item.display_name}</Text>
                          <Code fontSize="xxs" color="text.secondary" bg="transparent">
                            {item.image_id}
                          </Code>
                        </Stack>
                      </Td>
                      <Td>
                        {item.global && item.global.grade !== null ? (
                          <Stack spacing={1}>
                            <Text fontWeight="semibold">Grade {item.global.grade}</Text>
                            <Text fontSize="xs" color="text.secondary">Suggestion available</Text>
                          </Stack>
                        ) : (
                          <Text color="text.secondary">Not analyzed</Text>
                        )}
                      </Td>
                      <Td><StatusBadge tone={review.tone}>{review.label}</StatusBadge></Td>
                      <Td>
                        <Stack spacing={1}>
                          <StatusBadge tone={admission.tone}>{admission.label}</StatusBadge>
                          <Text fontSize="xs" color="text.secondary" maxW="220px">{admission.note}</Text>
                        </Stack>
                      </Td>
                      <Td><StatusBadge tone={analysis.tone}>{analysis.label}</StatusBadge></Td>
                      <Td isNumeric>
                        <Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} variant="secondary" size="sm">
                          Review
                        </Button>
                      </Td>
                    </Tr>
                  );
                })}
              </Tbody>
            </Table>
          </TableContainer>
        )}
      </Section>
      <HStack mt={4} spacing={2} color="text.muted" fontSize="xs">
        <Text>AI suggestions require clinician review.</Text>
      </HStack>
    </Box>
  );
}
