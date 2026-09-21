import { useEffect, useMemo, useState } from 'react';
import { Alert, AlertIcon, Button, HStack, Input, FormControl, FormLabel, Modal, ModalBody, ModalCloseButton, ModalContent, ModalFooter, ModalHeader, ModalOverlay, Stack, Text } from '@chakra-ui/react';
import type { AdmissionReviewAction, CaseRecord } from '@/lib/api';
import { admissionApi } from '@/lib/api';

interface ReadinessDialogProps {
  item: CaseRecord | null;
  onClose: () => void;
  onSaved: (item: CaseRecord) => void;
}

function actionsFor(item: CaseRecord): Array<{ action: AdmissionReviewAction; label: string }> {
  if (!item.admission) return [];
  const actions: Array<{ action: AdmissionReviewAction; label: string }> = [];
  if (item.admission.modality_admission === 'NEEDS_REVIEW') {
    actions.push({ action: 'ACCEPT_RETINAL', label: 'Accept as retinal image' });
    actions.push({ action: 'MARK_NON_FUNDUS', label: 'Mark as not a retinal image' });
  }
  if (item.admission.quality_state === 'NEEDS_REVIEW') {
    actions.push({ action: 'QUALITY_ACCEPTABLE', label: 'Mark image quality acceptable' });
    actions.push({ action: 'QUALITY_INADEQUATE', label: 'Mark image quality inadequate' });
  }
  if (item.admission.quality_state === 'UNGRADABLE') {
    actions.push({ action: 'QUALITY_ACCEPTABLE', label: 'Mark image quality acceptable' });
  }
  return actions;
}

export function ReadinessDialog({ item, onClose, onSaved }: ReadinessDialogProps) {
  const [reviewer, setReviewer] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [savingAction, setSavingAction] = useState<AdmissionReviewAction | null>(null);
  const actions = useMemo(() => item ? actionsFor(item) : [], [item]);

  useEffect(() => {
    if (!item) return;
    setReviewer('');
    setError(null);
    setSavingAction(null);
  }, [item]);

  const save = async (action: AdmissionReviewAction) => {
    if (!item || !reviewer.trim()) {
      setError('Reviewer name is required before saving.');
      return;
    }
    setSavingAction(action);
    setError(null);
    try {
      const saved = await admissionApi.review(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        action,
      });
      onSaved(saved);
      onClose();
    } catch {
      setError('Image readiness could not be updated. Reload the case and try again.');
    } finally {
      setSavingAction(null);
    }
  };

  return (
    <Modal isOpen={Boolean(item)} onClose={onClose} isCentered>
      <ModalOverlay /><ModalContent>
        <ModalHeader>Resolve image readiness</ModalHeader><ModalCloseButton />
        <ModalBody><Stack spacing={4}>
          {error && <Alert status="error"><AlertIcon /><Text>{error}</Text></Alert>}
          <Stack spacing={1}><Text fontWeight="semibold">{item?.filename ?? item?.display_name}</Text><Text fontSize="sm" color="text.secondary">{item?.admission_ui?.note ?? 'Confirm whether this image can be used for analysis.'}</Text></Stack>
          {actions.length === 0 && <Text fontSize="sm" color="text.secondary">No corrective action is available for this case.</Text>}
          <FormControl isRequired><FormLabel htmlFor="worklist-readiness-reviewer">Reviewer</FormLabel><Input id="worklist-readiness-reviewer" value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Reviewer name" /></FormControl>
          {actions.length > 0 && <Text fontSize="xs" color="text.secondary">The selected action is recorded in the existing admission history.</Text>}
        </Stack></ModalBody>
        <ModalFooter><HStack spacing={2} flexWrap="wrap" justify="flex-end"><Button variant="ghost" onClick={onClose} isDisabled={Boolean(savingAction)}>Cancel</Button>{actions.map((entry) => <Button key={entry.action} variant="solid" onClick={() => void save(entry.action)} isLoading={savingAction === entry.action} isDisabled={Boolean(savingAction) && savingAction !== entry.action}>{entry.label}</Button>)}</HStack></ModalFooter>
      </ModalContent>
    </Modal>
  );
}
