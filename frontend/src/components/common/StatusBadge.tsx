import { Badge } from '@chakra-ui/react';
import type { ReactNode } from 'react';

export type StatusTone = 'neutral' | 'brand' | 'info' | 'success' | 'warning' | 'danger';

interface StatusBadgeProps {
  tone?: StatusTone;
  children: ReactNode;
}

const VARIANT_FOR_TONE: Record<StatusTone, string> = {
  neutral: 'subtle',
  brand: 'brand',
  info: 'info',
  success: 'success',
  warning: 'warning',
  danger: 'danger',
};

export function StatusBadge({ tone = 'neutral', children }: StatusBadgeProps) {
  return <Badge variant={VARIANT_FOR_TONE[tone]}>{children}</Badge>;
}
