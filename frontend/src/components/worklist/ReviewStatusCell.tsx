import { Stack, Text } from '@chakra-ui/react';
import type { CaseRecord } from '@/lib/api';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';
import { reviewState, reviewStateLabel } from './worklistModel';

export function reviewStatus(item: CaseRecord): { label: string; tone: StatusTone } {
  const state = reviewState(item);
  const tone: StatusTone = state === 'complete' ? 'success'
    : state === 'reviewed' ? 'info'
    : state === 'needs-annotation' || state === 'escalated' || state === 'needs-second-review' || state === 'ungradable' ? 'warning' : 'neutral';
  return { label: reviewStateLabel(state), tone };
}

export function ReviewStatusCell({ item }: { item: CaseRecord }) {
  const status = reviewStatus(item);
  const state = reviewState(item);
  const detail = state === 'complete'
    ? 'Grade confirmed · Findings confirmed'
    : state === 'reviewed'
      ? 'Findings pending'
      : state === 'needs-annotation'
        ? 'Legacy correction record'
        : state === 'escalated'
          ? 'Legacy senior-review record'
          : undefined;
  return (
    <Stack spacing={0.5} align="flex-start" minW={0} maxW="100%" title={detail ? `${status.label}: ${detail}` : status.label} aria-label={`Review status: ${status.label}${detail ? `. ${detail}` : ''}`}>
      <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
      {detail && <Text fontSize="xs" color="text.secondary" whiteSpace="normal" overflowWrap="anywhere">{state === 'complete' ? 'Grade ✓ · Findings ✓' : detail}</Text>}
    </Stack>
  );
}
