import { useEffect, useState } from 'react';
import { Alert, AlertIcon, Button, HStack, Input, FormControl, FormLabel, Modal, ModalBody, ModalCloseButton, ModalContent, ModalFooter, ModalHeader, ModalOverlay, Select, Stack, Text } from '@chakra-ui/react';
import type { CaseRecord, Laterality } from '@/lib/api';
import { admissionApi } from '@/lib/api';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';
import { ReviewerField } from '@/components/common/ReviewerField';

export function ConfirmImageDialog({ item, onClose, onSaved }: { item: CaseRecord | null; onClose: () => void; onSaved: (item: CaseRecord) => void }) {
  const [patientKey, setPatientKey] = useState('');
  const [laterality, setLaterality] = useState<Laterality>('UNKNOWN');
  const [reviewer, setReviewer] = useState('');
  const [useAsDefault, setUseAsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!item) return;
    const defaultReviewer = getDefaultReviewer();
    setPatientKey(item.patient_key ?? item.patient_candidate ?? '');
    setLaterality(item.laterality ?? 'UNKNOWN');
    setReviewer(defaultReviewer);
    setUseAsDefault(Boolean(defaultReviewer));
    setError(null);
  }, [item]);

  const save = async () => {
    if (!item || !reviewer.trim()) { setError('Reviewer name is required.'); return; }
    setSaving(true);
    setError(null);
    try {
      const saved = await admissionApi.confirmImage(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        patient_key: patientKey.trim() || null,
        laterality,
      });
      if (useAsDefault) setDefaultReviewer(reviewer);
      else setDefaultReviewer('');
      onSaved(saved);
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Image confirmation could not be saved.');
    } finally { setSaving(false); }
  };

  return (
    <Modal isOpen={Boolean(item)} onClose={onClose} isCentered>
      <ModalOverlay /><ModalContent><ModalHeader>Confirm Image</ModalHeader><ModalCloseButton />
      <ModalBody><Stack spacing={4}>
        {error && <Alert status="error"><AlertIcon /><Text>{error}</Text></Alert>}
        <Stack spacing={1}><Text fontWeight="semibold">{item?.filename ?? item?.display_name}</Text><Text fontSize="sm" color="text.secondary">Review the image context before analysis or clinical review. Filename suggestions remain evidence until you confirm them.</Text></Stack>
        <FormControl><FormLabel htmlFor="confirm-image-patient-key">Pseudonymous patient key</FormLabel><Input id="confirm-image-patient-key" value={patientKey} onChange={(event) => setPatientKey(event.target.value.toUpperCase())} placeholder="PAT0001" /></FormControl>
        <FormControl><FormLabel htmlFor="confirm-image-eye">Eye</FormLabel><Select id="confirm-image-eye" value={laterality} onChange={(event) => setLaterality(event.target.value as Laterality)}><option value="LEFT">Left</option><option value="RIGHT">Right</option><option value="UNKNOWN">Unknown</option></Select></FormControl>
        <ReviewerField id="confirm-image-reviewer" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />
      </Stack></ModalBody>
      <ModalFooter><HStack spacing={2}><Button variant="ghost" onClick={onClose} isDisabled={saving}>Cancel</Button><Button variant="solid" onClick={() => void save()} isLoading={saving}>Confirm image & continue</Button></HStack></ModalFooter>
      </ModalContent>
    </Modal>
  );
}
