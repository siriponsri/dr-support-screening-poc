import { Badge, type BadgeProps } from '@chakra-ui/react';
import type { ReactNode } from 'react';

export type StatusTone = 'neutral' | 'brand' | 'info' | 'success' | 'warning' | 'danger';

interface StatusBadgeProps extends Omit<BadgeProps, 'children' | 'variant'> {
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

export function StatusBadge({ tone = 'neutral', children, ...props }: StatusBadgeProps) {
  return (
    <Badge
      variant={VARIANT_FOR_TONE[tone]}
      display="inline-flex"
      alignItems="center"
      gap={1}
      {...props}
    >
      {children}
    </Badge>
  );
}
