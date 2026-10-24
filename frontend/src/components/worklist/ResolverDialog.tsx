import { useEffect, useState } from 'react';
import { Alert, AlertIcon, Button, FormControl, FormLabel, HStack, Input, Modal, ModalBody, ModalCloseButton, ModalContent, ModalFooter, ModalHeader, ModalOverlay, Select, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord, Laterality } from '@/lib/api';
import { resolverApi } from '@/lib/api';
import { ReviewerField } from '@/components/common/ReviewerField';
import { hasInternalPatientKey, patientLabel } from '@/lib/patientPresentation';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';

export function ResolverDialog({ item, onClose, onSaved }: { item: CaseRecord | null; onClose: () => void; onSaved: (item: CaseRecord) => void }) {
  const [patientKey, setPatientKey] = useState('');
  const [replacePatient, setReplacePatient] = useState(false);
  const [unlinkPatient, setUnlinkPatient] = useState(false);
  const [laterality, setLaterality] = useState<Laterality>('UNKNOWN');
  const [reviewer, setReviewer] = useState('');
  const [useAsDefault, setUseAsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!item) return;
    setPatientKey(hasInternalPatientKey(item) ? '' : item.patient_key ?? item.patient_candidate ?? '');
    setReplacePatient(false);
    setUnlinkPatient(false);
    setLaterality(item.laterality ?? 'UNKNOWN');
    const defaultReviewer = getDefaultReviewer();
    setReviewer(defaultReviewer);
    setUseAsDefault(Boolean(defaultReviewer));
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
        patient_action: hasInternalPatientKey(item) && (!replacePatient || (!patientKey.trim() && !unlinkPatient)) ? 'KEEP' : patientKey.trim() ? (confirmsCandidate ? 'CONFIRM' : 'SET') : 'LEAVE_UNLINKED',
        patient_key: patientKey.trim() || undefined,
        laterality_action: 'SET',
        laterality,
      });
      onSaved(saved);
      setDefaultReviewer(useAsDefault ? reviewer : '');
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error && saveError.message === 'Patient key must be a short pseudonymous identifier'
        ? 'Use a pseudonymous key with 3-32 characters, starting with a letter and including a number.'
        : 'Patient and eye details could not be saved. Check your entries and try again.');
    } finally { setSaving(false); }
  };

  return (
    <Modal isOpen={Boolean(item)} onClose={onClose} isCentered>
      <ModalOverlay /><ModalContent><ModalHeader>Resolve patient and eye</ModalHeader><ModalCloseButton />
      <ModalBody><Stack spacing={4}>
        {error && <Alert status="error"><AlertIcon /><Text>{error}</Text></Alert>}
        <Text fontSize="sm" color="text.secondary">Changes are recorded in the existing patient and eye review history.</Text>
        {item && hasInternalPatientKey(item) && !replacePatient ? <Stack spacing={2}><Text>{patientLabel(item)} / workspace label</Text><Text fontSize="sm">The existing patient link will be kept.</Text><Button variant="outline" onClick={() => setReplacePatient(true)}>Change patient link</Button></Stack> : <>
        <FormControl><FormLabel htmlFor="worklist-patient-key">Pseudonymous patient key</FormLabel><Input id="worklist-patient-key" value={patientKey} onChange={(event) => { setPatientKey(event.target.value.toUpperCase()); setUnlinkPatient(false); }} placeholder="PAT0001" /></FormControl>
        {item && hasInternalPatientKey(item) && <><Text fontSize="sm">Enter an approved pseudonymous key to replace the link. A blank replacement keeps the current link. Workspace labels are not replacement keys.</Text><Button variant="outline" onClick={() => { setPatientKey(''); setUnlinkPatient(false); setReplacePatient(false); }}>Keep current patient link</Button><Button variant="ghost" onClick={() => { setPatientKey(''); setUnlinkPatient(true); }}>Leave this image unlinked</Button>{unlinkPatient && <Text fontSize="sm" color="status.warning">This image will be left unlinked when you save.</Text>}</>}
        </>}
        <FormControl><FormLabel htmlFor="worklist-eye">Eye</FormLabel><Select id="worklist-eye" value={laterality} onChange={(event) => setLaterality(event.target.value as Laterality)}><option value="LEFT">Left</option><option value="RIGHT">Right</option><option value="UNKNOWN">Unknown</option></Select></FormControl>
        <ReviewerField id="worklist-reviewer" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />
      </Stack></ModalBody>
      <ModalFooter><HStack spacing={2}><Button variant="ghost" onClick={onClose} isDisabled={saving}>Cancel</Button><Button variant="solid" onClick={() => void save()} isLoading={saving}>Save patient / eye</Button></HStack></ModalFooter>
      </ModalContent>
    </Modal>
  );
}
