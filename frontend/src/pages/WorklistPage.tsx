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
import { apiJson, type CaseRecord } from '@/lib/api';
import { RefreshCw } from '@/lib/icons';

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

export function WorklistPage() {
  const { pathname } = useLocation();
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
          <Button leftIcon={<RefreshCw size={15} />} onClick={() => void loadCases()} isLoading={loading}>
            Refresh
          </Button>
        }
      >
        {error && (
          <Alert status="error" mb={4}>
            <AlertIcon />
            <Text>{error}</Text>
          </Alert>
        )}
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
                  <Th>Analysis status</Th>
                  <Th isNumeric>Review action</Th>
                </Tr>
              </Thead>
              <Tbody>
                {cases.map((item) => {
                  const analysis = analysisStatus(item);
                  const review = reviewStatus(item);
                  return (
                    <Tr key={item.image_id} data-testid={`case-row-${item.display_name}`}>
                      <Td>
                        <Image
                          src={item.image_url}
                          alt={`${item.display_name} retinal preview`}
                          w="88px"
                          h="64px"
                          objectFit="contain"
                          bg="surface.viewer"
                          borderRadius="sm"
                        />
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
                            <Text fontSize="xs" color="text.secondary">{item.global.state}</Text>
                          </Stack>
                        ) : (
                          <Text color="text.secondary">Not analyzed</Text>
                        )}
                      </Td>
                      <Td><StatusBadge tone={review.tone}>{review.label}</StatusBadge></Td>
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
