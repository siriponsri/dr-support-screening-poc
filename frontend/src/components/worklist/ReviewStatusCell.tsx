import type { CaseRecord } from '@/lib/api';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';

export function reviewStatus(item: CaseRecord): { label: string; tone: StatusTone } {
  if (item.queue_state === 'EXCLUDED') return { label: 'Excluded', tone: 'neutral' };
  if (item.state === 'REVIEWED') return { label: 'Verified', tone: 'success' };
  if (item.state === 'NEEDS_CORRECTION') return { label: 'Needs annotation', tone: 'danger' };
  if (item.state === 'ESCALATED') return { label: 'Escalated', tone: 'warning' };
  return { label: 'Pending review', tone: 'neutral' };
}

export function ReviewStatusCell({ item }: { item: CaseRecord }) {
  const status = reviewStatus(item);
  return <StatusBadge tone={status.tone}>{status.label}</StatusBadge>;
}
