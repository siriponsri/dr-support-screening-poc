import { Alert, AlertIcon, Box, Button, Checkbox, Code, HStack, Stack, Text } from '@chakra-ui/react';
import { useEffect, useRef, useState } from 'react';
import type { CaseRecord } from '@/lib/api';
import { apiJson } from '@/lib/api';
import { artifactViewCurrent, artifactVisibilityCounts } from '@/lib/artifactRoiAssist';

export function ArtifactRoiControls({ item, showFiltered, showOverlay, previewProposals = false,
  onPreviewProposals, onShowFiltered, onShowOverlay, onCaseChange }: {
  item: CaseRecord; showFiltered: boolean; showOverlay: boolean;
  onShowFiltered: (value: boolean) => void; onShowOverlay: (value: boolean) => void;
  onCaseChange: (value: CaseRecord) => void;
  previewProposals?: boolean; onPreviewProposals?: (value: boolean) => void;
}) {
  const view = item.artifact_roi_assist;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const currentItem = useRef(item);
  currentItem.current = item;
  useEffect(() => {
    generation.current += 1; setBusy(false); setError(null);
    onPreviewProposals?.(false);
    return () => { generation.current += 1; };
  }, [item.image_id, item.source_sha256, item.revision, view?.scope_sha256, view?.binding_sha256]);
  if (!view?.enabled) return null;
  const current = artifactViewCurrent(item) && !error;
  const count = current && view.status === 'READY' ? view.suppressed_ids.length : 0;
  const counts = artifactVisibilityCounts(item, showFiltered, Boolean(error), previewProposals);
  const visibility = !current ? 'Unavailable / all review suggestions retained'
    : view.status === 'SHADOW_ONLY'
      ? previewProposals ? `${counts.hiddenCount} proposed ROI${counts.hiddenCount === 1 ? '' : 's'} hidden in local preview` : 'Preview only / all review suggestions shown'
      : counts.hiddenCount > 0 ? `${counts.hiddenCount} ROI suggestion${counts.hiddenCount === 1 ? '' : 's'} hidden`
        : counts.filteredCount > 0 ? `${counts.filteredCount} filtered ROI suggestion${counts.filteredCount === 1 ? '' : 's'} shown for inspection`
          : 'All review suggestions shown';
  const restore = async () => {
    const currentGeneration = generation.current;
    const requestIsCurrent = () => {
      const latest = currentItem.current;
      return generation.current === currentGeneration && latest.image_id === item.image_id
        && latest.source_sha256 === item.source_sha256 && latest.revision === item.revision
        && latest.artifact_roi_assist?.scope_sha256 === view.scope_sha256
        && latest.artifact_roi_assist?.binding_sha256 === view.binding_sha256;
    };
    setBusy(true); setError(null);
    try {
      const saved = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(item.image_id)}/artifact-roi/restore`, {
        method: 'POST', body: JSON.stringify({ revision: item.revision, scope_sha256: view.scope_sha256,
          binding_sha256: view.binding_sha256, detection_ids: view.suppressed_ids }),
      });
      if (requestIsCurrent() && saved.image_id === item.image_id && saved.source_sha256 === item.source_sha256
          && saved.revision > item.revision && saved.artifact_roi_assist?.scope_sha256 === view.scope_sha256
          && saved.artifact_roi_assist?.binding_sha256 === view.binding_sha256) onCaseChange(saved);
    } catch {
      if (!requestIsCurrent()) return;
      setError('Artifact view changed or could not be saved. All AI suggestions are shown.');
      onShowFiltered(true); onShowOverlay(false);
    } finally { if (requestIsCurrent()) setBusy(false); }
  };
  return <Stack spacing={2} data-testid="artifact-roi-controls">
    <Text fontSize="sm" fontWeight="semibold">ROI post-filter: {visibility}</Text>
    <Text fontSize="xs">After inference: changes ROI visibility only. Original and model input are unchanged.</Text>
    <Text fontSize="xs">Review suggestions shown: {counts.shownCount} of {counts.reviewSuggestionCount}. Raw model ROIs retained: {counts.rawPredictionCount}.</Text>
    {view.evidence_kind && <Text fontSize="xs">{view.evidence_kind === 'PROVEN_TECHNICAL_PADDING_ONLY'
      ? 'Technical padding only' : view.evidence_kind === 'EMPIRICAL_RIM_SHADOW_NOT_CERTIFIED'
        ? 'Empirical proposal / no automatic hiding' : view.evidence_kind === 'CACHED_OFFLINE_ARTIFACT_REPLAY_NOT_CERTIFIED'
          ? 'Cached source-bound replay / not a validated detector or new inference'
          : view.evidence_kind === 'GENERIC_IMAGE_ONLY_EMPIRICAL_NOT_CERTIFIED'
            ? 'Image-only empirical candidates / uncertainty retained; quality not validated' : 'Annotation-assist test view'}</Text>}
    <Text fontSize="xs">Orange shows the saved post-filter field for this decision; other areas are retained or uncertain. This is not retina segmentation or a negative label. Raw AI detections are retained.</Text>
    <HStack flexWrap="wrap">
      {view.status === 'SHADOW_ONLY' && onPreviewProposals ? <Checkbox isChecked={previewProposals && current}
        isDisabled={!current || !view.shadow_proposals?.length}
        onChange={(event) => onPreviewProposals(event.target.checked)}>Preview hiding proposed artifact ROIs</Checkbox>
        : <Checkbox isChecked={showFiltered} isDisabled={Boolean(error) || view.status === 'SHADOW_ONLY'}
          onChange={(event) => onShowFiltered(event.target.checked)}>Show filtered artifact ROIs</Checkbox>}
      <Checkbox isChecked={showOverlay && current} isDisabled={!current || !view.overlay_url}
        onChange={(event) => onShowOverlay(event.target.checked)}>Show saved post-filter field</Checkbox>
      <Button size="sm" isDisabled={!current || (count === 0 && !previewProposals)} isLoading={busy}
        onClick={() => previewProposals ? onPreviewProposals?.(false) : void restore()}>Restore all filtered ROIs</Button>
    </HStack>
    <Box as="details" fontSize="xs">
      <Box as="summary" cursor="pointer">Post-filter decision details</Box>
      <Stack spacing={1} mt={1}>
        <Text>Saved visibility policy: <Code fontSize="inherit">{view.policy_version}</Code></Text>
        {current && view.binding_sha256 && <Text>Decision binding: <Code fontSize="inherit" whiteSpace="normal" overflowWrap="anywhere">{view.binding_sha256}</Code></Text>}
        <Text>{current && view.overlay_url ? 'The overlay uses the saved, source-bound decision field.' : 'A current saved field is unavailable; no exclusion area is asserted.'}</Text>
      </Stack>
    </Box>
    {error && <Alert status="warning"><AlertIcon />{error}</Alert>}
  </Stack>;
}
