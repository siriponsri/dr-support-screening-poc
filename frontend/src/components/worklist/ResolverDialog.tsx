import { useEffect, useState } from 'react';
import { Alert, AlertIcon, Button, FormControl, FormLabel, HStack, Input, Modal, ModalBody, ModalCloseButton, ModalContent, ModalFooter, ModalHeader, ModalOverlay, Select, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord, Laterality } from '@/lib/api';
import { resolverApi } from '@/lib/api';

export function ResolverDialog({ item, onClose, onSaved }: { item: CaseRecord | null; onClose: () => void; onSaved: (item: CaseRecord) => void }) {
  const [patientKey, setPatientKey] = useState('');
  const [laterality, setLaterality] = useState<Laterality>('UNKNOWN');
  const [reviewer, setReviewer] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!item) return;
    setPatientKey(item.patient_key ?? item.patient_candidate ?? '');
    setLaterality(item.laterality ?? 'UNKNOWN');
    setReviewer('');
    setError(null);
  }, [item]);

  const save = async () => {
    if (!item || !reviewer.trim()) { setError('Reviewer name is required.'); return; }
    setSaving(true);
    setError(null);
    try {
      const confirmsCandidate = Boolean(item.patient_candidate && !item.patient_key && patientKey.trim() === item.patient_candidate);
      const saved = await resolverApi.review(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        patient_action: patientKey.trim() ? (confirmsCandidate ? 'CONFIRM' : 'SET') : 'LEAVE_UNLINKED',
        patient_key: patientKey.trim() || undefined,
        laterality_action: 'SET',
        laterality,
      });
      onSaved(saved);
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Patient and eye details could not be saved.');
    } finally { setSaving(false); }
  };

  return (
    <Modal isOpen={Boolean(item)} onClose={onClose} isCentered>
      <ModalOverlay /><ModalContent><ModalHeader>Resolve patient and eye</ModalHeader><ModalCloseButton />
      <ModalBody><Stack spacing={4}>
        {error && <Alert status="error"><AlertIcon /><Text>{error}</Text></Alert>}
        <Text fontSize="sm" color="text.secondary">Changes are recorded in the existing patient and eye review history.</Text>
        <FormControl><FormLabel htmlFor="worklist-patient-key">Pseudonymous patient key</FormLabel><Input id="worklist-patient-key" value={patientKey} onChange={(event) => setPatientKey(event.target.value.toUpperCase())} placeholder="PAT0001" /></FormControl>
        <FormControl><FormLabel htmlFor="worklist-eye">Eye</FormLabel><Select id="worklist-eye" value={laterality} onChange={(event) => setLaterality(event.target.value as Laterality)}><option value="LEFT">Left</option><option value="RIGHT">Right</option><option value="UNKNOWN">Unknown</option></Select></FormControl>
        <FormControl isRequired><FormLabel htmlFor="worklist-reviewer">Reviewer</FormLabel><Input id="worklist-reviewer" value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Reviewer name" /></FormControl>
      </Stack></ModalBody>
      <ModalFooter><HStack spacing={2}><Button variant="ghost" onClick={onClose} isDisabled={saving}>Cancel</Button><Button variant="solid" onClick={() => void save()} isLoading={saving}>Save patient / eye</Button></HStack></ModalFooter>
      </ModalContent>
    </Modal>
  );
}
