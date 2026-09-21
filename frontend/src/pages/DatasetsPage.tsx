import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Center,
  Code,
  HStack,
  Spinner,
  Stack,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';
import { datasetApi, type DatasetImageRow, type DatasetManifestResponse } from '@/lib/api';
import { Download, RefreshCw } from '@/lib/icons';

type DatasetFilter = 'all' | 'ready' | 'needs-review' | 'excluded';

function statusTone(status: DatasetImageRow['dataset_status']): StatusTone {
  if (status === 'Ready for dataset') return 'success';
  if (status === 'Excluded') return 'neutral';
  if (status === 'AI only') return 'info';
  return 'warning';
}

function patientEye(row: DatasetImageRow): string {
  const eye = row.laterality === 'LEFT' ? 'Left' : row.laterality === 'RIGHT' ? 'Right' : 'Eye not confirmed';
  return `${row.patient_key ?? 'Unlinked'} / ${eye}`;
}

function annotationSummary(row: DatasetImageRow): string {
  const parts: string[] = [];
  if (row.human_annotation_count) parts.push(`${row.human_annotation_count} human`);
  if (row.ai_lesion_count) parts.push(`${row.ai_lesion_count} AI`);
  if (row.cvat_annotation_count) parts.push(`${row.cvat_annotation_count} imported`);
  return parts.length ? parts.join(' / ') : 'None';
}

function filterRows(images: DatasetImageRow[], filter: DatasetFilter): DatasetImageRow[] {
  if (filter === 'ready') return images.filter((row) => row.include_in_training);
  if (filter === 'excluded') return images.filter((row) => row.dataset_status === 'Excluded');
  if (filter === 'needs-review') return images.filter((row) => !row.include_in_training && row.dataset_status !== 'Excluded');
  return images;
}

function DatasetTable({ images }: { images: DatasetImageRow[] }) {
  if (images.length === 0) {
    return <Box borderWidth="1px" borderStyle="dashed" borderColor="border.default" bg="surface.subtle" p={5}><Text color="text.secondary">No records match this view.</Text></Box>;
  }
  return (
    <TableContainer overflowX="auto" maxW="100%">
      <Table variant="clinical" size="sm" minW="760px">
        <Thead><Tr><Th>Image</Th><Th>Patient / eye</Th><Th>Clinician grade</Th><Th>Annotations</Th><Th>Dataset status</Th></Tr></Thead>
        <Tbody>{images.map((row) => (
          <Tr key={row.image_id} data-testid={`dataset-row-${row.image_id}`}>
            <Td><Stack spacing={0.5}><Text fontWeight="semibold" noOfLines={1} title={row.filename}>{row.filename}</Text><Code fontSize="xxs" noOfLines={1}>{row.image_id}</Code></Stack></Td>
            <Td><Text>{patientEye(row)}</Text></Td>
            <Td>{row.clinician_grade === null ? <Text color="text.secondary">No final grade</Text> : <Text fontWeight="semibold">Grade {row.clinician_grade}</Text>}</Td>
            <Td><Text fontSize="sm">{annotationSummary(row)}</Text></Td>
            <Td><StatusBadge tone={statusTone(row.dataset_status)}>{row.dataset_status}</StatusBadge></Td>
          </Tr>
        ))}</Tbody>
      </Table>
    </TableContainer>
  );
}

export function DatasetsPage() {
  const { pathname } = useLocation();
  const [manifest, setManifest] = useState<DatasetManifestResponse | null>(null);
  const [filter, setFilter] = useState<DatasetFilter>('all');
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadManifest = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setManifest(await datasetApi.manifest());
    } catch {
      setError('The dataset manifest could not be loaded. Try refreshing.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadManifest(); }, [loadManifest]);

  const visibleImages = useMemo(
    () => filterRows(manifest?.images ?? [], filter),
    [filter, manifest],
  );

  const createExport = async () => {
    if (!manifest?.can_export || exporting) return;
    setExporting(true);
    setError(null);
    setNotice(null);
    try {
      const result = await datasetApi.export();
      setNotice(`Export created: ${result.image_count} images and ${result.annotation_count} annotations.`);
    } catch {
      setError('The dataset export could not be created. Check the active Workspace and try again.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader
        pathname={pathname}
        title="Datasets"
        subtitle="A reproducible manifest of the active Workspace, with AI and clinician provenance kept separate."
        actions={<Button leftIcon={<Download size={15} />} onClick={() => void createExport()} isLoading={exporting} isDisabled={!manifest?.can_export}>Export manifest</Button>}
      />
      <Stack spacing={4}>
        {error && <Alert status="error"><AlertIcon /><Text>{error}</Text></Alert>}
        {notice && <Alert status="success"><AlertIcon /><Text>{notice}</Text></Alert>}
        {loading && !manifest ? (
          <Center py={12}><Stack align="center" spacing={3}><Spinner color="action.primary" /><Text color="text.secondary">Loading dataset manifest...</Text></Stack></Center>
        ) : manifest ? (
          <Section title="Dataset manifest" description="Export metadata only; source images and case records are never changed." action={<Button size="sm" variant="outline" leftIcon={<RefreshCw size={14} />} onClick={() => void loadManifest()} isLoading={loading}>Refresh</Button>}>
            <Stack spacing={4}>
              <HStack spacing={5} flexWrap="wrap" fontSize="sm">
                <Text><Text as="span" color="text.secondary">Scope</Text> <Text as="span" fontWeight="semibold">{manifest.workspace_name ?? 'No active Workspace'}</Text></Text>
                <Text><Text as="span" color="text.secondary">Images</Text> <Text as="span" fontWeight="semibold">{manifest.image_count}</Text></Text>
                <Text><Text as="span" color="text.secondary">Annotations</Text> <Text as="span" fontWeight="semibold">{manifest.annotation_count}</Text></Text>
                <Text><Text as="span" color="text.secondary">Training-ready</Text> <Text as="span" fontWeight="semibold">{manifest.training_ready_count}</Text></Text>
              </HStack>
              {!manifest.can_export && <Alert status="warning"><AlertIcon /><Text>Open an active Workspace to export a dataset manifest.</Text></Alert>}
              <Tabs index={['all', 'ready', 'needs-review', 'excluded'].indexOf(filter)} onChange={(index) => setFilter(['all', 'ready', 'needs-review', 'excluded'][index] as DatasetFilter)} variant="line" isLazy>
                <TabList aria-label="Dataset views"><Tab>All {manifest.image_count}</Tab><Tab>Training-ready {manifest.training_ready_count}</Tab><Tab>Needs review {manifest.needs_review_count}</Tab><Tab>Excluded {manifest.excluded_count}</Tab></TabList>
                <TabPanels>
                  <TabPanel px={0} pt={4}><DatasetTable images={visibleImages} /></TabPanel>
                  <TabPanel px={0} pt={4}><DatasetTable images={visibleImages} /></TabPanel>
                  <TabPanel px={0} pt={4}><DatasetTable images={visibleImages} /></TabPanel>
                  <TabPanel px={0} pt={4}><DatasetTable images={visibleImages} /></TabPanel>
                </TabPanels>
              </Tabs>
            </Stack>
          </Section>
        ) : null}
      </Stack>
    </Box>
  );
}
