import { Stack, Text } from '@chakra-ui/react';
import type { CaseRecord } from '@/lib/api';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';
import { gradeConfirmed } from '@/lib/caseProgress';
import { reviewState, workStatus, workStatusLabel } from './worklistModel';

export function reviewStatus(item: CaseRecord): { label: string; tone: StatusTone } {
  const status = workStatus(item);
  const tone: StatusTone = status === 'done' ? 'success' : status === 'in-progress' ? 'info' : 'neutral';
  return { label: workStatusLabel(status), tone };
}

function nextStep(item: CaseRecord): string | undefined {
  const state = reviewState(item);
  if (state === 'needs-second-review') return 'Needs Second Review';
  if (state === 'needs-annotation') return 'Legacy correction record';
  if (state === 'escalated') return 'Legacy senior-review record';
  if (state === 'legacy-unknown') return 'Historical unknown grade';
  if (state === 'ungradable') return 'Ungradable';
  if (workStatus(item) !== 'in-progress') return undefined;
  return gradeConfirmed(item) ? 'Findings next' : 'Grade next';
}

export function ReviewStatusCell({ item }: { item: CaseRecord }) {
  const status = reviewStatus(item);
  const detail = nextStep(item);
  return (
    <Stack spacing={0.5} align="flex-start" minW={0} maxW="100%" title={detail ? `${status.label}: ${detail}` : status.label} aria-label={`Review status: ${status.label}${detail ? `. ${detail}` : ''}`}>
      <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
      {detail && <Text fontSize="xs" color="text.secondary" whiteSpace="normal" overflowWrap="anywhere">{detail}</Text>}
    </Stack>
  );
}
