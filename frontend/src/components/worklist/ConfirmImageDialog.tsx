import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Collapse,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  Stack,
  Text,
} from '@chakra-ui/react';
import type { CaseRecord, Laterality, RetinalModality } from '@/lib/api';
import { admissionApi } from '@/lib/api';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';
import { ReviewerField } from '@/components/common/ReviewerField';
import { ChevronDown, ChevronUp } from '@/lib/icons';

function filenameMethod(method?: string): boolean {
  return method === 'FILENAME' || method === 'FILENAME_AND_OCR';
}

function SummaryRow({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <HStack justify="space-between" align="flex-start" borderWidth="1px" borderColor="border.subtle" borderRadius="md" px={3} py={2}>
      <Stack spacing={0} minW={0}>
        <Text fontSize="sm" color="text.secondary">{label}</Text>
        <Text fontWeight="semibold" noOfLines={1}>{value || 'Unknown'}</Text>
      </Stack>
      <Badge colorScheme="blue" variant="subtle" flexShrink={0}>{note}</Badge>
    </HStack>
  );
}

export function ConfirmImageDialog({ item, onClose, onSaved }: { item: CaseRecord | null; onClose: () => void; onSaved: (item: CaseRecord) => void }) {
  const [patientKey, setPatientKey] = useState('');
  const [laterality, setLaterality] = useState<Laterality>('UNKNOWN');
  const [imageType, setImageType] = useState<RetinalModality>('UNKNOWN');
  const [visitKey, setVisitKey] = useState('');
  const [capturedAt, setCapturedAt] = useState('');
  const [captureSequence, setCaptureSequence] = useState('');
  const [device, setDevice] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [useAsDefault, setUseAsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [metadataOpen, setMetadataOpen] = useState(false);
  const initialFocusRef = useRef<HTMLElement | null>(null);

  const filenameEvidence = item?.resolver_evidence?.filename;
  const patientResolved = Boolean(item?.patient_key);
  const eyeResolved = Boolean(
    item?.laterality_resolution_state === 'RESOLVED'
      || (item?.laterality && item.laterality !== 'UNKNOWN'),
  );
  const imageTypeResolved = Boolean(imageType !== 'UNKNOWN');
  const patientSource = filenameMethod(item?.patient_resolution_method) ? 'suggested from filename' : 'confirmed';
  const eyeSource = filenameMethod(item?.laterality_resolution_method) ? 'suggested from filename' : 'confirmed';
  const imageTypeSource = item?.admission?.retinal_modality_method === 'DICOM_METADATA'
    ? 'detected from source metadata'
    : 'confirmed';

  useEffect(() => {
    if (!item) return;
    const defaultReviewer = getDefaultReviewer();
    setPatientKey(item.patient_key ?? item.patient_candidate ?? '');
    setLaterality(item.laterality ?? 'UNKNOWN');
    setImageType(item.admission?.retinal_modality ?? item.modality ?? 'UNKNOWN');
    setVisitKey(item.visit_context?.visit_key ?? '');
    setCapturedAt(item.visit_context?.captured_at ?? '');
    setCaptureSequence(item.visit_context?.capture_sequence == null
      ? item.resolver_evidence?.filename?.capture_sequence == null ? '' : String(item.resolver_evidence.filename.capture_sequence)
      : String(item.visit_context.capture_sequence));
    setDevice(item.visit_context?.device ?? '');
    setReviewer(defaultReviewer);
    setUseAsDefault(Boolean(defaultReviewer));
    setMetadataOpen(false);
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
        retinal_modality: imageType,
        visit_key: visitKey.trim() || null,
        captured_at: capturedAt.trim() || null,
        capture_sequence: captureSequence.trim() ? Number(captureSequence) : null,
        device: device.trim() || null,
      });
      if (useAsDefault) setDefaultReviewer(reviewer);
      else setDefaultReviewer('');
      onSaved(saved);
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Image confirmation could not be saved.');
    } finally { setSaving(false); }
  };

  const firstUnresolvedRef = !imageTypeResolved
    ? initialFocusRef
    : !patientResolved
      ? initialFocusRef
      : !eyeResolved
        ? initialFocusRef
        : undefined;

  return (
    <Modal isOpen={Boolean(item)} onClose={onClose} isCentered initialFocusRef={firstUnresolvedRef}>
      <ModalOverlay />
      <ModalContent as="form" noValidate onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <ModalHeader>Confirm Image</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <Stack spacing={4}>
            {error && <Alert status="error"><AlertIcon /><Text>{error}</Text></Alert>}
            <Stack spacing={1}>
              <Text fontWeight="semibold">{item?.filename ?? item?.display_name}</Text>
              <Text fontSize="sm" color="text.secondary">Only uncertain context needs confirmation. Filename and source metadata are evidence, not clinical truth.</Text>
            </Stack>
            {imageTypeResolved ? (
              <SummaryRow label="Image type" value={imageType === 'UWF' ? 'Ultra-widefield' : 'Conventional fundus photograph'} note={imageTypeSource} />
            ) : (
              <FormControl>
                <FormLabel htmlFor="confirm-image-type">Image type</FormLabel>
                <Select ref={!imageTypeResolved ? (node) => { initialFocusRef.current = node; } : undefined} id="confirm-image-type" value={imageType} onChange={(event) => setImageType(event.target.value as RetinalModality)}>
                  <option value="UNKNOWN">Not sure yet</option>
                  <option value="CFP">Conventional fundus photograph</option>
                  <option value="UWF">Ultra-widefield</option>
                </Select>
                <Text fontSize="xs" color="text.secondary" mt={1}>If unsure, keep Not sure yet. AI analysis requires a confirmed supported image type.</Text>
              </FormControl>
            )}
            {patientResolved ? (
              <SummaryRow label="Patient" value={patientKey} note={patientSource} />
            ) : (
              <FormControl>
                <FormLabel htmlFor="confirm-image-patient-key">Patient</FormLabel>
                <Input ref={imageTypeResolved ? (node) => { initialFocusRef.current = node; } : undefined} id="confirm-image-patient-key" value={patientKey} onChange={(event) => setPatientKey(event.target.value.toUpperCase())} placeholder="Enter a pseudonymous key or leave blank" />
                <Text fontSize="xs" color="text.secondary" mt={1}>{item?.patient_candidate ? 'Suggested from available evidence; confirm or correct it.' : 'Unknown is allowed when no supported evidence is available.'}</Text>
              </FormControl>
            )}
            {eyeResolved ? (
              <SummaryRow label="Eye" value={laterality === 'LEFT' ? 'Left' : 'Right'} note={eyeSource} />
            ) : (
              <FormControl>
                <FormLabel htmlFor="confirm-image-eye">Eye</FormLabel>
                <Select ref={imageTypeResolved && patientResolved ? (node) => { initialFocusRef.current = node; } : undefined} id="confirm-image-eye" value={laterality} onChange={(event) => setLaterality(event.target.value as Laterality)}>
                  <option value="LEFT">Left</option>
                  <option value="RIGHT">Right</option>
                  <option value="UNKNOWN">Unknown</option>
                </Select>
              </FormControl>
            )}
            <ReviewerField id="confirm-image-reviewer" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />
            <Box borderWidth="1px" borderColor="border.subtle" borderRadius="md" p={3}>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                px={0}
                rightIcon={metadataOpen ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                aria-expanded={metadataOpen}
                aria-controls="confirm-image-additional-metadata"
                onClick={() => setMetadataOpen((open) => !open)}
              >
                {metadataOpen ? 'Hide additional metadata' : 'Additional metadata'}
              </Button>
              <Collapse in={metadataOpen} animateOpacity>
                <Stack id="confirm-image-additional-metadata" spacing={3} mt={3}>
                  <Text fontSize="xs" color="text.secondary">Optional acquisition details. Sequence numbers support evidence only; they do not prove before/after chronology.</Text>
                  <FormControl><FormLabel htmlFor="confirm-image-visit">Visit key (optional)</FormLabel><Input id="confirm-image-visit" value={visitKey} onChange={(event) => setVisitKey(event.target.value)} placeholder="Leave blank when unknown" /></FormControl>
                  <FormControl><FormLabel htmlFor="confirm-image-capture">Capture date/time (optional)</FormLabel><Input id="confirm-image-capture" value={capturedAt} onChange={(event) => setCapturedAt(event.target.value)} placeholder="Leave blank when unknown" /></FormControl>
                  <FormControl><FormLabel htmlFor="confirm-image-sequence">Capture sequence (optional)</FormLabel><Input id="confirm-image-sequence" type="number" min={0} value={captureSequence} onChange={(event) => setCaptureSequence(event.target.value)} placeholder="Leave blank when unknown" /></FormControl>
                  {filenameEvidence?.capture_sequence != null && <Text fontSize="xs" color="text.secondary">Sequence {filenameEvidence.capture_sequence} was derived from the supported filename pattern. It is not a before/after claim.</Text>}
                  <FormControl><FormLabel htmlFor="confirm-image-device">Camera / device (optional)</FormLabel><Input id="confirm-image-device" value={device} onChange={(event) => setDevice(event.target.value)} placeholder="Leave blank when unknown" /></FormControl>
                </Stack>
              </Collapse>
            </Box>
          </Stack>
        </ModalBody>
        <ModalFooter>
          <HStack spacing={2}><Button type="button" variant="ghost" onClick={onClose} isDisabled={saving}>Cancel</Button><Button type="submit" variant="solid" isLoading={saving}>Confirm image &amp; continue</Button></HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
