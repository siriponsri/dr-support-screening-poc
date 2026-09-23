import { useState } from 'react';
import { Alert, AlertIcon, Button, HStack, Text } from '@chakra-ui/react';
import type { CaseRecord, ModelDescriptor } from '@/lib/api';
import { getHintsEnabled, setHintsEnabled } from '@/lib/hintPreference';
import { annotationsConfirmed, gradeConfirmed } from '@/lib/caseProgress';

function nextAction(item: CaseRecord, models: ModelDescriptor[] = []): string {
  if (item.admission_ui?.action_required || item.resolver_ui?.action_required) return 'Confirm image';
  if (!item.global && !item.lesion) {
    const unavailable = models.some((model) => ['retfound-aptos5', 'prism-dr-5fold'].includes(model.model_id) && model.status === 'REMOTE_NOT_CONFIGURED');
    return unavailable ? 'Review image manually' : 'Run optional AI analysis';
  }
  if (!gradeConfirmed(item)) return 'Clinician review - confirm DR grade';
  if (!annotationsConfirmed(item)) return 'Confirm annotation';
  return 'Review complete';
}

export function NextActionHint({ item, models = [] }: { item: CaseRecord; models?: ModelDescriptor[] }) {
  const [enabled, setEnabled] = useState(() => getHintsEnabled());
  if (!enabled) return null;
  return (
    <Alert status="info" variant="subtle" py={2} px={3} alignItems="center">
      <AlertIcon />
      <HStack justify="space-between" flex={1} spacing={3}>
        <Text fontSize="sm"><strong>Next action:</strong> {nextAction(item, models)}</Text>
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
