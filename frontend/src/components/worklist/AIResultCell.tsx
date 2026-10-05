import { Stack, Text } from '@chakra-ui/react';
import { drGradeLabel, type CaseRecord, type ModelDescriptor } from '@/lib/api';
import { aiState } from './worklistModel';

export function AIResultCell({ item, models = [] }: { item: CaseRecord; models?: ModelDescriptor[] }) {
  if (item.source_origin === 'WORKSPACE') return <Text color="text.secondary">Manual review only</Text>;
  if (item.global?.grade !== null && item.global?.grade !== undefined) {
    return <Stack spacing={0.5}><Text fontWeight="semibold">{drGradeLabel(item.global.grade) ?? 'Grade available'}</Text><Text fontSize="xs" color="text.secondary">Suggestion available</Text></Stack>;
  }
  if (item.global || item.lesion) return <Text color="text.secondary">Partial result</Text>;
  const state = aiState(item, models);
  return <Text color="text.secondary">{state === 'model-available' ? 'Model available' : item.modality === 'UNKNOWN' ? 'Confirm image type' : 'Manual only'}</Text>;
}
