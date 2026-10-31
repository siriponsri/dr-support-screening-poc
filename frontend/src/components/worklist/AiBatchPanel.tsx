import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, AlertIcon, Box, Button, HStack, Progress, Stack, Text } from '@chakra-ui/react';
import { regularApi, type RegularBatch, type RegularStatus } from '@/lib/api';

const POLL_MS = 5000;

const SERVER_LABELS: Record<string, string> = {
  READY: 'AI server ready',
  STARTING: 'AI server starting',
  STOPPING: 'AI server stopping',
  STOPPED: 'AI server idle, starts when needed',
};

function hoursLabel(status: RegularStatus): string {
  if (status.quarantined || status.revoked) return 'AI analysis paused until the operator checks the server';
  if (!status.ai_open) return 'Outside AI hours (06:00 to 22:00, Thailand time)';
  return SERVER_LABELS[status.model_server ?? ''] ?? 'AI server status unknown';
}

/**
 * Daily AI batch on the shared model server: for each image the grader and
 * then PRISM run in the background, one stage at a time. An image counts as
 * complete only with both results. Hidden when the app is not on the shared
 * queue (the status route is absent).
 */
export function AiBatchPanel() {
  const [status, setStatus] = useState<RegularStatus | null>(null);
  const [batch, setBatch] = useState<RegularBatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [available, setAvailable] = useState(true);
  const loaded = useRef(false);

  const load = useCallback(async () => {
    try {
      const [nextStatus, batches] = await Promise.all([regularApi.status(), regularApi.batches()]);
      setStatus(nextStatus);
      setBatch(batches.batches.length ? batches.batches[batches.batches.length - 1] : null);
      setError(null);
    } catch (reason) {
      // Not on the shared queue (or never reached it): stay hidden; once shown, report the problem.
      if (!loaded.current) setAvailable(false);
      else setError(reason instanceof Error && reason.message ? reason.message : 'AI queue status is not available.');
      return;
    }
    loaded.current = true;
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  if (!available) return null;

  const start = async () => {
    setBusy(true);
    try {
      setBatch(await regularApi.startAll());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The AI batch could not start.');
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!batch) return;
    setBusy(true);
    try {
      setBatch(await regularApi.cancel(batch.batch_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The AI batch could not be stopped.');
    } finally {
      setBusy(false);
    }
  };

  const grader: Record<string, number> = batch?.counts.grader ?? {};
  const prism: Record<string, number> = batch?.counts.prism ?? {};
  const total = batch?.total ?? 0;
  const settled = (counts: Record<string, number>) => total - (counts.PENDING ?? 0) - (counts.RUNNING ?? 0);
  const stageText = (name: string, counts: Record<string, number>) => [
    `${name}: ${counts.SAVED ?? 0} saved`,
    counts.RUNNING ? '1 running' : '',
    counts.PENDING ? `${counts.PENDING} waiting` : '',
    counts.NEEDS_ACTION ? `${counts.NEEDS_ACTION} need action` : '',
    counts.NOT_ELIGIBLE ? `${counts.NOT_ELIGIBLE} not run` : '',
    counts.NEEDS_CONFIRM_IMAGE ? `${counts.NEEDS_CONFIRM_IMAGE} need Confirm Image` : '',
  ].filter(Boolean).join(', ');

  return (
    <Box borderWidth="1px" borderColor="border.default" bg="surface.subtle" p={4} mb={4} data-testid="ai-batch-panel">
      <Stack spacing={3}>
        <HStack justifyContent="space-between" flexWrap="wrap" spacing={3}>
          <Stack spacing={0}>
            <Text fontWeight="semibold">AI batch</Text>
            {status && (
              <Text fontSize="sm" color="text.secondary" data-testid="ai-batch-status">
                {hoursLabel(status)}. Analyses left today: {status.invocations_available ?? 0} of {status.invocations_cap ?? 0}.
              </Text>
            )}
          </Stack>
          <HStack spacing={2}>
            {batch?.active && <Button size="sm" variant="outline" onClick={() => void cancel()} isLoading={busy}>Stop waiting images</Button>}
            {!batch?.active && <Button size="sm" onClick={() => void start()} isLoading={busy}>Run AI on confirmed images</Button>}
          </HStack>
        </HStack>
        {batch && (
          <Stack spacing={1} data-testid="ai-batch-progress">
            <Progress value={total ? ((settled(grader) + settled(prism)) / (2 * total)) * 100 : 0} size="sm" aria-label="AI batch progress" />
            <Text fontSize="sm" fontWeight="semibold">{batch.complete} of {total} images have both AI results.</Text>
            <Text fontSize="sm">{stageText('Grade', grader)}.</Text>
            <Text fontSize="sm">{stageText('PRISM', prism)}.</Text>
            {batch.note && <Text fontSize="sm" color="text.secondary">{batch.note}</Text>}
          </Stack>
        )}
        {error && <Alert status="warning" py={2}><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
      </Stack>
    </Box>
  );
}
