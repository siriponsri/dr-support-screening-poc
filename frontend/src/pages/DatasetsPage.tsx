import { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Center,
  Code,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalHeader,
  ModalOverlay,
  Select,
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
import { StatusBadge } from '@/components/common/StatusBadge';
import {
  datasetApi,
  drGradeLabel,
  type DatasetImageRow,
  type DatasetManifestResponse,
  type WorkspaceDataDetail,
  type WorkspaceDataResponse,
} from '@/lib/api';
import { ChevronLeft, ChevronRight, Download, Eye, RefreshCw, Search } from '@/lib/icons';

type DatasetFilter = 'all' | 'dr-ready' | 'lesion-positive-ready' | 'needs-review' | 'excluded';

function patientEye(row: DatasetImageRow): string {
  const eye = row.laterality === 'LEFT' ? 'Left' : row.laterality === 'RIGHT' ? 'Right' : 'Eye not confirmed';
  return `${row.training_group_key ?? 'Patient group not confirmed'} / ${eye}`;
}

function annotationSummary(row: DatasetImageRow): string {
  const parts: string[] = [];
  if (row.human_annotation_count) parts.push(`${row.human_annotation_count} human`);
  if (row.ai_lesion_count) parts.push(`${row.ai_lesion_count} AI evidence`);
  if (row.cvat_annotation_count) parts.push(`${row.cvat_annotation_count} imported`);
  return parts.length ? parts.join(' / ') : 'No lesion records';
}

function readinessLabel(row: DatasetImageRow, kind: 'dr' | 'lesion'): string {
  if (kind === 'dr') return (row.dr_grade_training_ready ?? row.include_in_training) ? `Ready${row.clinician_grade === null ? '' : ` - ${drGradeLabel(row.clinician_grade)}`}` : (row.grade_eligibility_reason ?? 'Needs review').replace(/_/g, ' ');
  if (row.lesion_positive_training_ready ?? false) return 'Positive labels ready';
  if (row.core_completeness_state === 'REVIEWED_NONE_FOUND') return 'Core reviewed - none recorded';
  return (row.lesion_eligibility_reason ?? 'Needs review').replace(/_/g, ' ');
}

function WorkspaceDataTable({ records, onSelect }: { records: DatasetImageRow[]; onSelect: (imageId: string) => void }) {
  if (records.length === 0) {
    return <Box borderWidth="1px" borderStyle="dashed" borderColor="border.default" bg="surface.subtle" p={5}><Text color="text.secondary">No records match this view.</Text></Box>;
  }
  return (
    <TableContainer overflowX="auto" maxW="100%">
      <Table variant="clinical" size="sm" minW="980px">
        <Thead><Tr><Th>Case</Th><Th>Patient / eye</Th><Th>DR label</Th><Th>Lesion labels</Th><Th>Completeness</Th><Th>Source</Th><Th>View</Th></Tr></Thead>
        <Tbody>{records.map((row) => (
          <Tr key={row.image_id} data-testid={`dataset-row-${row.image_id}`}>
            <Td><Stack spacing={0.5}><Text fontWeight="semibold" noOfLines={1} title={row.filename}>{row.filename}</Text><Code fontSize="xxs" noOfLines={1}>{row.image_id}</Code></Stack></Td>
            <Td><Text fontSize="sm">{patientEye(row)}</Text></Td>
            <Td><StatusBadge tone={(row.dr_grade_training_ready ?? row.include_in_training) ? 'success' : 'warning'}>{readinessLabel(row, 'dr')}</StatusBadge></Td>
            <Td><Stack spacing={1} fontSize="xs"><Text>{annotationSummary(row)}</Text><Text color="text.secondary">{readinessLabel(row, 'lesion')}</Text></Stack></Td>
            <Td><Stack spacing={0.5} fontSize="xs"><Text>{row.core_completeness_state?.replace(/_/g, ' ') ?? 'Core not reviewed'}</Text><Text color="text.secondary">Advanced: {row.advanced_completeness_state?.replace(/_/g, ' ') ?? 'Not reviewed'}</Text></Stack></Td>
            <Td><Stack spacing={0.5} fontSize="xs"><Text>{row.source_origin ?? 'UNKNOWN'}{row.source_available === false ? ' - source unavailable' : ''}</Text><Text color={row.export_authorization?.startsWith('BLOCKED_') ? 'status.warning' : 'text.secondary'}>{row.export_authorization?.replace(/_/g, ' ')}</Text></Stack></Td>
            <Td><Button size="xs" variant="outline" leftIcon={<Eye size={13} />} onClick={() => onSelect(row.image_id)}>Details</Button></Td>
          </Tr>
        ))}</Tbody>
      </Table>
    </TableContainer>
  );
}

function DetailModal({ detail, onClose }: { detail: WorkspaceDataDetail | null; onClose: () => void }) {
  return (
    <Modal isOpen={Boolean(detail)} onClose={onClose} size="xl" scrollBehavior="inside">
      <ModalOverlay /><ModalContent>
        <ModalHeader>{detail?.record.filename ?? 'Workspace record'}</ModalHeader><ModalCloseButton />
        <ModalBody pb={6}>
          {detail && <Stack spacing={4}>
            <Stack spacing={1}><Text fontSize="sm" color="text.secondary">Case ID</Text><Code>{detail.record.image_id}</Code><Text fontSize="sm">Revision {detail.record.case_revision ?? 0} / {detail.record.source_origin ?? 'UNKNOWN'} / {detail.record.source_available === false ? 'Source unavailable' : 'Source available'}</Text></Stack>
            <Tabs variant="line" isLazy>
              <TabList><Tab>Review</Tab><Tab>Processing</Tab><Tab>AI evidence</Tab><Tab>Eligibility</Tab></TabList>
              <TabPanels>
                <TabPanel px={0}><Stack spacing={3}>{detail.completeness.map((item) => <Box key={item.group} borderWidth="1px" borderColor="border.subtle" p={3}><Text fontWeight="semibold">{item.group}</Text><Text fontSize="sm">{item.state.replace(/_/g, ' ')}</Text><Text fontSize="xs" color="text.secondary">{item.reviewer ?? 'No reviewer recorded'}{item.timestamp ? ` / ${item.timestamp}` : ''}</Text>{item.state === 'REVIEWED_NONE_FOUND' && <Text fontSize="xs" color="status.warning">Training negative: not authorized by current policy.</Text>}</Box>)}</Stack></TabPanel>
                <TabPanel px={0}><Stack spacing={2} fontSize="sm"><Text>Status: {String(detail.processing.status ?? 'UNAVAILABLE')}</Text><Text>Source SHA-256: {String(detail.processing.source_sha256 ?? 'Unavailable')}</Text><Text>Analysis SHA-256: {String(detail.processing.analysis_sha256 ?? 'Unavailable')}</Text><Text>Representation: {String(detail.processing.representation_version ?? 'Unavailable')}</Text><Text color="text.secondary">Processing details are recorded evidence only; Phase 4 does not recompute model results.</Text></Stack></TabPanel>
                <TabPanel px={0}><Stack spacing={2} fontSize="sm"><Text>Status: {detail.explainability.status}</Text><Text>Evidence identity: {detail.explainability.evidence_identity ?? 'Unavailable'}</Text><Text>AI evidence items: {detail.ai_evidence_counts.items} / unresolved {detail.ai_evidence_counts.unresolved}</Text><Text color="text.secondary">AI evidence is separate from gold labels and does not establish clinical accuracy.</Text></Stack></TabPanel>
                <TabPanel px={0}><Stack spacing={2} fontSize="sm"><Text>DR: {readinessLabel(detail.record, 'dr')}</Text><Text>Lesion-positive: {readinessLabel(detail.record, 'lesion')}</Text><Text>Gold DR rows: {detail.gold_label_counts.dr_grade}</Text><Text>Gold lesion rows: {detail.gold_label_counts.lesion_positive}</Text><Text>Training negatives: not authorized</Text><Text>Source authorization: {detail.record.export_authorization?.replace(/_/g, ' ')}</Text></Stack></TabPanel>
              </TabPanels>
            </Tabs>
          </Stack>}
        </ModalBody>
      </ModalContent>
    </Modal>
  );
}

export function DatasetsPage() {
  const { pathname } = useLocation();
  const [manifest, setManifest] = useState<DatasetManifestResponse | null>(null);
  const [data, setData] = useState<WorkspaceDataResponse | null>(null);
  const [filter, setFilter] = useState<DatasetFilter>('all');
  const [page, setPage] = useState(1);
  const [sourceOrigin, setSourceOrigin] = useState('');
  const [laterality, setLaterality] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportingGrouped, setExportingGrouped] = useState(false);
  const [snapshotting, setSnapshotting] = useState(false);
  const [groupedFormat, setGroupedFormat] = useState<'PNG' | 'JPEG'>('PNG');
  const [jpegQuality, setJpegQuality] = useState('90');
  const [detail, setDetail] = useState<WorkspaceDataDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const manifestResponse = await datasetApi.manifest();
      setManifest(manifestResponse);
      try {
        const dataResponse = await datasetApi.workspaceData({ page, limit: 25, readiness: filter, laterality, sourceOrigin, q: query });
        if (Array.isArray(dataResponse.records)) {
          setData(dataResponse);
        } else {
          throw new Error('Workspace Data compatibility fallback');
        }
      } catch {
        const normalized = manifestResponse.images.map((row) => ({
          ...row,
          dr_grade_training_ready: row.dr_grade_training_ready ?? row.include_in_training,
          lesion_positive_training_ready: row.lesion_positive_training_ready ?? false,
          source_origin: row.source_origin ?? (row.source_type as DatasetImageRow['source_origin']),
        }));
        const filtered = normalized.filter((row) => {
          if (filter === 'dr-ready' && !row.dr_grade_training_ready) return false;
          if (filter === 'lesion-positive-ready' && !row.lesion_positive_training_ready) return false;
          if (filter === 'excluded' && row.dataset_status !== 'Excluded') return false;
          if (filter === 'needs-review' && (row.include_in_training || row.dataset_status === 'Excluded')) return false;
          if (laterality && row.laterality !== laterality) return false;
          if (sourceOrigin && row.source_origin !== sourceOrigin) return false;
          if (query && !`${row.image_id} ${row.filename}`.toLowerCase().includes(query.toLowerCase())) return false;
          return true;
        });
        const start = (page - 1) * 25;
        setData({
          schema_version: 's4.workspace-data-compatibility.v1',
          workspace_id: manifestResponse.workspace_id,
          workspace_name: manifestResponse.workspace_name,
          page,
          limit: 25,
          total: filtered.length,
          has_next: start + 25 < filtered.length,
          source_state_digest: null,
          source_state_digest_version: 'unavailable',
          source_origin_summary: {},
          export_authorization_summary: {},
          records: filtered.slice(start, start + 25),
        });
      }
    } catch {
      setError('The dataset manifest could not be loaded. Try refreshing.');
    } finally {
      setLoading(false);
    }
  }, [filter, laterality, page, query, sourceOrigin]);

  useEffect(() => { void load(); }, [load]);

  const openDetail = async (imageId: string) => {
    try { setDetail(await datasetApi.workspaceDataDetail(imageId)); } catch { setError('Record details could not be loaded. Try refreshing.'); }
  };

  const createExport = async () => {
    if (!manifest?.can_export || exporting) return;
    setExporting(true); setError(null); setNotice(null);
    try { const result = await datasetApi.export(); setNotice(`Export created: ${result.image_count} images and ${result.annotation_count} annotations.`); } catch { setError('The dataset export could not be created.'); } finally { setExporting(false); }
  };

  const createSnapshot = async () => {
    if (snapshotting) return;
    setSnapshotting(true); setError(null); setNotice(null);
    try { const result = await datasetApi.snapshot(); setNotice(`Canonical snapshot created: ${result.snapshot_id}.`); } catch { setError('The canonical snapshot is blocked or could not be created. Review source authorization and Workspace state.'); } finally { setSnapshotting(false); }
  };

  const createGroupedExport = async () => {
    const quality = Number(jpegQuality);
    if (!manifest?.can_export || exportingGrouped || !Number.isInteger(quality) || quality < 1 || quality > 100) return;
    setExportingGrouped(true); setError(null); setNotice(null);
    try { const result = await datasetApi.exportGrouped(groupedFormat, quality); setNotice(`Grouped export created in ${result.directory_name}: ${result.copied_count} copied, ${result.identical_existing_count} already present, ${result.skipped_count} skipped.`); } catch { setError('The grouped image export could not be created.'); } finally { setExportingGrouped(false); }
  };

  return (
    <Box as="main" maxW="1600px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} title="Datasets" subtitle="A reproducible manifest of the active Workspace, with AI and clinician provenance kept separate. Workspace Data is read-only and bounded." actions={<HStack flexWrap="wrap"><Button leftIcon={<RefreshCw size={15} />} onClick={() => void load()} isLoading={loading}>Refresh</Button><Button leftIcon={<Download size={15} />} onClick={() => void createSnapshot()} isLoading={snapshotting}>Create canonical snapshot</Button></HStack>} />
      <Stack spacing={4}>
        {error && <Alert status="error"><AlertIcon /><Text>{error}</Text></Alert>}
        {notice && <Alert status="success"><AlertIcon /><Text>{notice}</Text></Alert>}
        {loading && !data ? <Center py={12}><Stack align="center" spacing={3}><Spinner color="action.primary" /><Text color="text.secondary">Loading Workspace Data...</Text></Stack></Center> : data && manifest ? <Section title="Workspace Data" description="Use filters to inspect bounded pages of persisted review records. No review actions are available here." action={<HStack fontSize="sm" color="text.secondary"><Text>{data.workspace_name ?? 'No active Workspace'}</Text><Text>{data.total} records</Text><Text>Digest {data.source_state_digest?.slice(0, 12) ?? 'unavailable'}</Text></HStack>}>
          <Stack spacing={4}>
            <HStack spacing={3} flexWrap="wrap" align="end">
              <FormControl maxW="220px"><FormLabel htmlFor="workspace-data-search" fontSize="sm">Case search</FormLabel><HStack><Input id="workspace-data-search" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="ID or filename" /><Search size={16} /></HStack></FormControl>
              <FormControl maxW="150px"><FormLabel htmlFor="workspace-data-laterality" fontSize="sm">Eye</FormLabel><Select id="workspace-data-laterality" value={laterality} onChange={(event) => { setLaterality(event.target.value); setPage(1); }}><option value="">All eyes</option><option value="LEFT">Left</option><option value="RIGHT">Right</option><option value="UNKNOWN">Unknown</option></Select></FormControl>
              <FormControl maxW="170px"><FormLabel htmlFor="workspace-data-origin" fontSize="sm">Source origin</FormLabel><Select id="workspace-data-origin" value={sourceOrigin} onChange={(event) => { setSourceOrigin(event.target.value); setPage(1); }}><option value="">All origins</option><option value="SYNTHETIC">Synthetic</option><option value="PUBLIC">Public</option><option value="WORKSPACE">Workspace</option><option value="UNKNOWN">Unknown</option></Select></FormControl>
            </HStack>
            <Tabs index={['all', 'dr-ready', 'lesion-positive-ready', 'needs-review', 'excluded'].indexOf(filter)} onChange={(index) => { setFilter(['all', 'dr-ready', 'lesion-positive-ready', 'needs-review', 'excluded'][index] as DatasetFilter); setPage(1); }} variant="line" isLazy>
              <TabList aria-label="Workspace Data views"><Tab>All</Tab><Tab>DR-ready</Tab><Tab>Lesion-positive ready</Tab><Tab>Needs review</Tab><Tab>Excluded</Tab></TabList>
              <TabPanels><TabPanel px={0} pt={4}><WorkspaceDataTable records={data.records} onSelect={(id) => void openDetail(id)} /></TabPanel><TabPanel px={0} pt={4}><WorkspaceDataTable records={data.records} onSelect={(id) => void openDetail(id)} /></TabPanel><TabPanel px={0} pt={4}><WorkspaceDataTable records={data.records} onSelect={(id) => void openDetail(id)} /></TabPanel><TabPanel px={0} pt={4}><WorkspaceDataTable records={data.records} onSelect={(id) => void openDetail(id)} /></TabPanel><TabPanel px={0} pt={4}><WorkspaceDataTable records={data.records} onSelect={(id) => void openDetail(id)} /></TabPanel></TabPanels>
            </Tabs>
            <HStack justify="space-between"><Text fontSize="sm" color="text.secondary">Page {data.page} of {Math.max(1, Math.ceil(data.total / data.limit))}</Text><HStack><Button size="sm" variant="outline" leftIcon={<ChevronLeft size={14} />} onClick={() => setPage((value) => Math.max(1, value - 1))} isDisabled={page <= 1}>Previous</Button><Button size="sm" variant="outline" rightIcon={<ChevronRight size={14} />} onClick={() => setPage((value) => value + 1)} isDisabled={!data.has_next}>Next</Button></HStack></HStack>
          </Stack>
        </Section> : null}
        <Section title="Export tools" description="Canonical snapshots contain metadata, physician-confirmed labels, completeness, and separate non-gold AI evidence. Source images are not copied.">
          <Stack spacing={3} align="flex-start">
            {!manifest?.can_export && <Text fontSize="sm" color="status.warning">Open an active Workspace to export a dataset manifest.</Text>}
            <HStack flexWrap="wrap"><Button leftIcon={<Download size={15} />} onClick={() => void createExport()} isLoading={exporting} isDisabled={!manifest?.can_export}>Export manifest</Button><Button variant="outline" onClick={() => void createGroupedExport()} isLoading={exportingGrouped} isDisabled={!manifest?.can_export}>Export grouped images</Button></HStack>
            <HStack role="group" aria-label="Grouped export image format" spacing={1}>{(['PNG', 'JPEG'] as const).map((format) => <Button key={format} size="sm" variant={groupedFormat === format ? 'solid' : 'outline'} aria-pressed={groupedFormat === format} onClick={() => setGroupedFormat(format)}>{format}</Button>)}</HStack>
            {groupedFormat === 'JPEG' && <FormControl maxW="180px"><FormLabel htmlFor="grouped-jpeg-quality" fontSize="sm">JPEG quality</FormLabel><Input id="grouped-jpeg-quality" type="number" min={1} max={100} step={1} value={jpegQuality} onChange={(event) => setJpegQuality(event.target.value)} /></FormControl>}
          </Stack>
        </Section>
      </Stack>
      <DetailModal detail={detail} onClose={() => setDetail(null)} />
    </Box>
  );
}
