import { Button, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord } from '@/lib/api';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';

export function PatientEyeCell({ item, onResolve }: { item: CaseRecord; onResolve: () => void }) {
  const ui = item.resolver_ui;
  const patientLabel = item.patient_key ?? ui?.patient.candidate ?? 'Patient not linked';
  const eyeLabel = item.laterality && item.laterality !== 'UNKNOWN' ? (item.laterality === 'LEFT' ? 'Left' : 'Right') : ui?.laterality.label ?? 'Eye not confirmed';
  const patientNeedsAction = !item.patient_key;
  const eyeNeedsAction = !item.laterality || item.laterality === 'UNKNOWN';
  const actionLabel = patientNeedsAction && eyeNeedsAction ? 'Link patient and confirm eye' : patientNeedsAction ? 'Link patient' : 'Confirm eye';
  return (
    <Stack spacing={1} minW={0}>
      <Text fontWeight="semibold" noOfLines={1} title={patientLabel}>{patientLabel}</Text>
      <Text fontSize="sm" color="text.secondary" noOfLines={1} title={eyeLabel}>{eyeLabel}</Text>
      {(patientNeedsAction || eyeNeedsAction) ? (
        <Button size="sm" variant="outline" alignSelf="flex-start" onClick={onResolve} aria-label={actionLabel}>{actionLabel}</Button>
      ) : (
        <StatusBadge tone={(ui?.tone ?? 'success') as StatusTone}>{ui?.label ?? 'Resolved'}</StatusBadge>
      )}
    </Stack>
  );
}
