import { Stack, Text } from '@chakra-ui/react';
import type { CaseRecord } from '@/lib/api';

export function AIResultCell({ item }: { item: CaseRecord }) {
  if (item.global?.grade !== null && item.global?.grade !== undefined) {
    return <Stack spacing={0.5}><Text fontWeight="semibold">Grade {item.global.grade}</Text><Text fontSize="xs" color="text.secondary">Suggestion available</Text></Stack>;
  }
  if (item.global || item.lesion) return <Text color="text.secondary">Partial result</Text>;
  return <Text color="text.secondary">{item.admission_ui?.label === 'Cannot analyze' ? 'AI unavailable' : 'Not analyzed'}</Text>;
}
