import { useEffect, useRef, useState } from 'react';
import { Alert, AlertIcon, Button, HStack, Stack, Text } from '@chakra-ui/react';
import { Section } from '@/components/common/Section';
import { datasetApi, type DatasetSnapshotPreview } from '@/lib/api';
import { localTiming, type Outcome } from '@/lib/localTiming';

interface Props { workspaceId: string | null; exportAllowed: boolean; refreshToken?: string }
const GROUPS = ['Grade0', 'Grade1', 'Grade2', 'Grade3', 'Grade4', 'UNREVIEWED', 'UNGRADABLE', 'UNDETERMINED'];

export function GradingFolderSnapshot({ workspaceId, exportAllowed, refreshToken }: Props) {
  const context = JSON.stringify([workspaceId, exportAllowed, refreshToken]);
  const active = useRef(context);
  active.current = context;
  const action = useRef<AbortController | null>(null);
  const [preview, setPreview] = useState<{ context: string; data: DatasetSnapshotPreview } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ context: string; text: string; error: boolean } | null>(null);
  useEffect(() => {
    setBusy(false);
    setPreview(null);
    setMessage(null);
    return () => { action.current?.abort(); action.current = null; };
  }, [context]);
  const shown = preview?.context === context ? preview.data : null;
  const folders = shown?.grading_folders;
  const available = exportAllowed && Boolean(workspaceId);
  const canCreate = available && shown?.can_export && folders?.schema_version === 'grading-folders.v1'
    && folders.status === 'READY' && Number(folders.file_count) > 0 && /^[a-f0-9]{64}$/.test(folders.plan_sha256 ?? '');

  const run = async (create: boolean) => {
    if (!available || action.current || (create && !canCreate)) return;
    const controller = new AbortController();
    action.current = controller;
    setBusy(true);
    setMessage(null);
    const current = () => action.current === controller && active.current === context && !controller.signal.aborted;
    const timing = localTiming.folder(create ? 'folder_snapshot' : 'folder_preview');
    const cancelled = () => timing.end('ABORTED');
    controller.signal.addEventListener('abort', cancelled, { once: true });
    let outcome: Outcome = 'FAILED';
    try {
      if (create && shown && folders?.plan_sha256) {
        const result = await datasetApi.snapshot({ include_grade_folders: true, expected_workspace_id: workspaceId!,
          expected_source_state_digest: shown.source_state_digest.digest, expected_grading_plan_sha256: folders.plan_sha256 }, controller.signal);
        if (!current()) { outcome = 'STALE'; return; }
        if (result.workspace_id !== workspaceId || !result.manifest.grading_folders) throw new Error('Unverified snapshot response');
        outcome = 'COMPLETED';
        setPreview(null);
        setMessage({ context, error: false, text: `Grading-folder snapshot created: ${result.snapshot_id}. ${folders.file_count} original files copied into ${result.directory_name}/grading_folders. Earlier snapshots and originals remain unchanged.` });
      } else {
        const result = await datasetApi.snapshotPreview(true, controller.signal);
        if (!current()) { outcome = 'STALE'; return; }
        if (result.workspace_id !== workspaceId) throw new Error('Workspace changed');
        if (result.grading_folders?.schema_version !== 'grading-folders.v1') {
          setPreview(null);
          setMessage({ context, error: true, text: result.can_export ? 'Grading-folder snapshots are unavailable on this backend. No images were exported.' : 'Source export is restricted. Check source identity and authorization.' });
          return;
        }
        setPreview({ context, data: result });
        outcome = 'COMPLETED';
      }
    } catch {
      if (current()) {
        setPreview(null);
        setMessage({ context, error: true, text: create
          ? 'Snapshot creation could not be verified. Check Workspace output, then refresh the preview before another attempt. Source changes or authorization may block it.'
          : 'The grading-folder preview is unavailable. Refresh the Workspace and check source authorization.' });
      }
    } finally {
      controller.signal.removeEventListener('abort', cancelled);
      timing.end(outcome);
      if (action.current === controller) { action.current = null; setBusy(false); }
    }
  };

  return <Section title="Grading-folder snapshot" description="Copy original image bytes into a new canonical snapshot. Originals and earlier snapshots are never moved or updated.">
    <Stack spacing={3}>
      <Text fontSize="sm">Grade0-4 use current recorded clinician confirmations with matching source provenance. Unreviewed, ungradable and undetermined images stay separate. AI suggestions do not assign folders. Folder membership does not certify clinical roles or lesion-training readiness.</Text>
      {!available && <Text fontSize="sm" color="status.warning">{workspaceId ? 'Image export is restricted for this Workspace; check source identity and authorization.' : 'Open an authorized Workspace to preview grading folders.'}</Text>}
      <HStack flexWrap="wrap"><Button variant="outline" onClick={() => void run(false)} isDisabled={!available || busy}>Preview grading folders</Button>
        <Button onClick={() => void run(true)} isDisabled={!canCreate || busy}>Create grading-folder snapshot</Button></HStack>
      {busy && <Text role="status" fontSize="sm">Preparing snapshot…</Text>}
      {message?.context === context && <Alert status={message.error ? 'warning' : 'success'}><AlertIcon /><Text>{message.text}</Text></Alert>}
      {folders && <Stack spacing={2} aria-label="Grading-folder preview counts">
        <HStack flexWrap="wrap" spacing={3}>{GROUPS.map((group) => <Text key={group} fontSize="sm">{group}: {folders.group_counts?.[group] ?? 0}</Text>)}</HStack>
        <Text fontSize="sm">{folders.file_count ?? 0} unique files / {folders.record_count ?? 0} records; {((folders.copy_bytes ?? 0) / 1048576).toFixed(1)} MiB to copy; {folders.skipped_count ?? 0} skipped; {folders.duplicate_record_count ?? 0} duplicate records.</Text>
        {Object.entries(folders.skipped_reasons ?? {}).map(([reason, count]) => <Text key={reason} fontSize="xs" color="status.warning">{reason.replace(/_/g, ' ')}: {count}</Text>)}
        {folders.status !== 'READY' && <Text fontSize="sm" color="status.warning">No supported, source-verified images can be copied. Manual review and metadata snapshots remain available under their existing authorization rules.</Text>}
      </Stack>}
    </Stack>
  </Section>;
}
