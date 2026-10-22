import { Alert, AlertIcon, Button, Checkbox, HStack, Stack, Text } from '@chakra-ui/react';
import { useEffect, useRef, useState } from 'react';
import type { CaseRecord } from '@/lib/api';
import { apiJson } from '@/lib/api';
import { artifactViewCurrent } from '@/lib/artifactRoiAssist';

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
    <Text fontSize="sm">Annotation assist · {view.status === 'SHADOW_ONLY'
      ? previewProposals ? 'Experimental visibility preview · proposed ROIs hidden locally' : 'Experimental overlay · all AI suggestions shown'
      : current ? `${count} artifact ROI suggestions filtered` : 'Artifact view unavailable · all AI suggestions shown'}</Text>
    {view.evidence_kind && <Text fontSize="xs">{view.evidence_kind === 'PROVEN_TECHNICAL_PADDING_ONLY'
      ? 'Technical padding only' : view.evidence_kind === 'EMPIRICAL_RIM_SHADOW_NOT_CERTIFIED'
        ? 'Empirical proposal · no automatic hiding' : view.evidence_kind === 'CACHED_OFFLINE_ARTIFACT_REPLAY_NOT_CERTIFIED'
          ? 'Cached source-bound replay · not a validated detector or new inference'
          : view.evidence_kind === 'GENERIC_IMAGE_ONLY_EMPIRICAL_NOT_CERTIFIED'
            ? 'Image-only empirical candidates · uncertainty retained; quality not validated' : 'Annotation-assist test view'}</Text>}
    <Text fontSize="xs">Orange marks artifact proposals; other areas are retained or uncertain. This is not retina segmentation or a negative label. Raw AI detections are retained.</Text>
    <HStack flexWrap="wrap">
      {view.status === 'SHADOW_ONLY' && onPreviewProposals ? <Checkbox isChecked={previewProposals && current}
        isDisabled={!current || !view.shadow_proposals?.length}
        onChange={(event) => onPreviewProposals(event.target.checked)}>Preview hiding proposed artifact ROIs</Checkbox>
        : <Checkbox isChecked={showFiltered} isDisabled={Boolean(error) || view.status === 'SHADOW_ONLY'}
          onChange={(event) => onShowFiltered(event.target.checked)}>Show filtered artifact ROIs</Checkbox>}
      <Checkbox isChecked={showOverlay && current} isDisabled={!current || !view.overlay_url}
        onChange={(event) => onShowOverlay(event.target.checked)}>Show artifact overlay</Checkbox>
      <Button size="sm" isDisabled={!current || (count === 0 && !previewProposals)} isLoading={busy}
        onClick={() => previewProposals ? onPreviewProposals?.(false) : void restore()}>Restore all filtered ROIs</Button>
    </HStack>
    {error && <Alert status="warning"><AlertIcon />{error}</Alert>}
  </Stack>;
}
