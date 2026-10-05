import { useState } from 'react';
import { Alert, AlertIcon, Button, HStack, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord, ModelDescriptor } from '@/lib/api';
import { getHintsEnabled, setHintsEnabled } from '@/lib/hintPreference';
import { annotationsConfirmed, gradeConfirmed } from '@/lib/caseProgress';
import { aiState } from '@/components/worklist/worklistModel';

export function nextAction(item: CaseRecord, _models: ModelDescriptor[] = []): string {
  if (item.grade_status === 'UNGRADABLE') return 'Review case status';
  if (item.grade_status === 'NEEDS_SECOND_REVIEW' || item.state === 'NEEDS_SECOND_REVIEW') return 'Complete second review';
  if (!gradeConfirmed(item)) return 'Review image and choose a final DR grade';
  if (!annotationsConfirmed(item)) return 'Review findings and finish the case';
  return 'Open the next case from the Worklist';
}

export function contextWarnings(item: CaseRecord, models: ModelDescriptor[] = []): string[] {
  const warnings: string[] = [];
  if (item.resolver_ui?.action_required) warnings.push('Patient and eye context needs confirmation.');
  if (item.admission_ui?.action_required) warnings.push('Image context needs confirmation.');
  if (aiState(item, models) === 'manual-only' && !item.global && !item.lesion) {
    warnings.push('AI assistance is unavailable; manual review remains available.');
  }
  return warnings;
}

export function NextActionHint({ item, models = [] }: { item: CaseRecord; models?: ModelDescriptor[] }) {
  const [enabled, setEnabled] = useState(() => getHintsEnabled());
  if (!enabled) return null;
  const warnings = contextWarnings(item, models);
  return (
    <Alert status={warnings.length ? 'warning' : 'info'} variant="subtle" py={2} px={3} alignItems="flex-start">
      <AlertIcon />
      <HStack justify="space-between" flex={1} spacing={3} align="flex-start">
        <Stack spacing={1} fontSize="sm">
          <Text><strong>Workflow:</strong> {nextAction(item, models)}</Text>
          {warnings.length > 0 && <Text color="text.secondary"><strong>Context:</strong> {warnings.join(' ')}</Text>}
        </Stack>
        <Button
          size="xs"
          variant="ghost"
          onClick={() => { setHintsEnabled(false); setEnabled(false); }}
          aria-label="Dismiss next action hints"
        >
          Dismiss
        </Button>
      </HStack>
    </Alert>
  );
}
