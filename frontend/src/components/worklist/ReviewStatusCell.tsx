import { Stack, Text } from '@chakra-ui/react';
import type { CaseRecord } from '@/lib/api';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';
import { reviewState, reviewStateLabel } from './worklistModel';

export function reviewStatus(item: CaseRecord): { label: string; tone: StatusTone } {
  const state = reviewState(item);
  const tone: StatusTone = state === 'complete' ? 'success'
    : state === 'reviewed' ? 'info'
      : state === 'needs-annotation' || state === 'escalated' ? 'warning' : 'neutral';
  return { label: reviewStateLabel(state), tone };
}

export function ReviewStatusCell({ item }: { item: CaseRecord }) {
  const status = reviewStatus(item);
  const state = reviewState(item);
  return (
    <Stack spacing={0.5} align="flex-start">
      <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
      {state === 'complete' && <Text fontSize="xs" color="text.secondary">DR grade confirmed · Annotations confirmed</Text>}
      {state === 'reviewed' && <Text fontSize="xs" color="text.secondary">Annotations pending</Text>}
    </Stack>
  );
}
