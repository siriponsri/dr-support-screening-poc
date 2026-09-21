import type { CaseRecord } from '@/lib/api';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';
import { reviewState, reviewStateLabel } from './worklistModel';

export function reviewStatus(item: CaseRecord): { label: string; tone: StatusTone } {
  const state = reviewState(item);
  const tone: StatusTone = state === 'reviewed' ? 'success' : state === 'needs-annotation' ? 'danger' : state === 'escalated' ? 'warning' : 'neutral';
  return { label: reviewStateLabel(state), tone };
}

export function ReviewStatusCell({ item }: { item: CaseRecord }) {
  const status = reviewStatus(item);
  return <StatusBadge tone={status.tone}>{status.label}</StatusBadge>;
}
