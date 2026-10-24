import { Button, IconButton, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord } from '@/lib/api';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';
import { Pencil } from '@/lib/icons';
import { patientLabel } from '@/lib/patientPresentation';

export function PatientEyeCell({ item, onResolve }: { item: CaseRecord; onResolve: () => void }) {
  const ui = item.resolver_ui;
  const patient = patientLabel(item);
  const eyeLabel = item.laterality && item.laterality !== 'UNKNOWN' ? (item.laterality === 'LEFT' ? 'Left' : 'Right') : ui?.laterality.label ?? 'Eye not confirmed';
  const patientNeedsAction = ui ? ui.patient.action_required : !item.patient_key;
  const eyeNeedsAction = ui
    ? ui.laterality.action_required
    : !item.laterality || (item.laterality === 'UNKNOWN' && item.laterality_resolution_state !== 'RESOLVED');
  const actionLabel = patientNeedsAction && eyeNeedsAction ? 'Link patient and confirm eye' : patientNeedsAction ? 'Link patient' : 'Confirm eye';
  const manuallyConfirmed = item.patient_resolution_method === 'MANUAL' || item.laterality_resolution_method === 'MANUAL';
  const assignmentStatus = manuallyConfirmed ? 'Confirmed' : 'Auto-linked';
  const assignmentTone: StatusTone = manuallyConfirmed ? 'success' : 'info';
  return (
    <Stack spacing={1} minW={0}>
      {patientNeedsAction || eyeNeedsAction ? (
        <>
          <Text fontWeight="semibold" noOfLines={1} title={patient}>{patient}</Text>
          <Text fontSize="sm" color="text.secondary" noOfLines={1} title={eyeLabel}>{eyeLabel}</Text>
        </>
      ) : (
        <>
          <Text fontWeight="semibold" noOfLines={1} title={`${patient} / ${eyeLabel}`}>{patient} / {eyeLabel}</Text>
          <Stack direction="row" spacing={1} align="center">
            <StatusBadge tone={assignmentTone}>{assignmentStatus}</StatusBadge>
            <IconButton
              size="xs"
              variant="ghost"
              icon={<Pencil size={14} />}
              aria-label="Edit patient and eye assignment"
              title="Edit patient and eye assignment"
              onClick={onResolve}
            />
          </Stack>
        </>
      )}
      {(patientNeedsAction || eyeNeedsAction) && (
        <Button size="sm" variant="outline" alignSelf="flex-start" onClick={onResolve} aria-label={actionLabel}>{actionLabel}</Button>
      )}
    </Stack>
  );
}
