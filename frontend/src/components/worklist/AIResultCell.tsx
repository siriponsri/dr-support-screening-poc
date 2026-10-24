import { Stack, Text } from '@chakra-ui/react';
import { drGradeLabel, type CaseRecord, type ModelDescriptor } from '@/lib/api';
import { aiState, finalGradeKey } from './worklistModel';

/**
 * Result column. The clinician's final grade shows once recorded; before that
 * only AI readiness is shown so the AI grade does not anchor the review.
 */
export function AIResultCell({ item, models = [] }: { item: CaseRecord; models?: ModelDescriptor[] }) {
  const finalGrade = finalGradeKey(item);
  if (finalGrade === 'U') return <Stack spacing={0.5}><Text fontWeight="semibold">Ungradable</Text><Text fontSize="xs" color="text.secondary">Clinician</Text></Stack>;
  if (finalGrade != null) {
    return <Stack spacing={0.5}><Text fontWeight="semibold">Grade {finalGrade}</Text><Text fontSize="xs" color="text.secondary" noOfLines={1}>{drGradeLabel(Number(finalGrade))}</Text></Stack>;
  }
  if (item.source_origin === 'WORKSPACE' || item.source_origin === 'UNKNOWN') return <Text color="text.secondary">Manual review only</Text>;
  if (item.global || item.lesion) return <Text color="text.secondary">AI ready</Text>;
  const state = aiState(item, models);
  return <Text color="text.secondary">{state === 'model-available' ? 'AI not run yet' : item.modality === 'UNKNOWN' ? 'Confirm image type' : 'Manual only'}</Text>;
}
