import { useT } from '@/lib/i18n';
import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Collapse,
  FormControl,
  FormErrorMessage,
  FormLabel,
  Grid,
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
import type { AdmissionReviewAction, CaseRecord, Laterality, RetinalModality } from '@/lib/api';
import { admissionApi } from '@/lib/api';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';
import { ReviewerField } from '@/components/common/ReviewerField';
import { GuideHint } from '@/components/common/GuideHint';
import { hasInternalPatientKey, patientLabel } from '@/lib/patientPresentation';
import { ChevronDown, ChevronUp, Pencil } from '@/lib/icons';
import { handleRadioArrowKeys, radioTabIndex } from '@/components/common/radioGroupKeys';

function filenameMethod(method?: string): boolean {
  return method === 'FILENAME' || method === 'FILENAME_AND_OCR';
}

function SummaryRow({ label, value, note, onEdit }: { label: string; value: string; note: string; onEdit: () => void }) {
  const t = useT();
  return (
    <HStack justify="space-between" align="flex-start" flexWrap="wrap" gap={2} borderWidth="1px" borderColor="border.subtle" borderRadius="md" px={3} py={2}>
      <Stack spacing={0} minW={0} flex="1 1 160px">
        <Text fontSize="sm" color="text.secondary">{label}</Text>
        <Text fontSize="md" fontWeight="semibold" overflowWrap="anywhere">{value || t('Unknown')}</Text>
      </Stack>
      <HStack spacing={2} flexShrink={0}>
        <Badge colorScheme="blue" variant="subtle">{t(note)}</Badge>
        <Button
          type="button"
          size="xs"
          variant="ghost"
          leftIcon={<Pencil size={12} aria-hidden="true" />}
          aria-label={`Edit ${label.toLowerCase()}`}
          onClick={onEdit}
        >
          {t('Edit')}
        </Button>
      </HStack>
    </HStack>
  );
}

type QualityChoice = '' | Extract<AdmissionReviewAction, 'QUALITY_ACCEPTABLE' | 'QUALITY_INADEQUATE'>;

function recordedQuality(item: CaseRecord | null): QualityChoice {
  const state = item?.admission?.quality_state;
  return state === 'GRADABLE' ? 'QUALITY_ACCEPTABLE' : state === 'UNGRADABLE' ? 'QUALITY_INADEQUATE' : '';
}

function QualityChoiceField({ value, onChange, allowClear }: { value: QualityChoice; onChange: (value: QualityChoice) => void; allowClear: boolean }) {
  const t = useT();
  const options: { value: Exclude<QualityChoice, ''>; label: string }[] = [
    { value: 'QUALITY_ACCEPTABLE', label: 'Usable' },
    { value: 'QUALITY_INADEQUATE', label: 'Not usable' },
  ];
  return (
    <Stack spacing={1.5}>
      <Text id="confirm-image-quality-label" fontSize="sm" color="text.secondary">{t('Image quality (optional)')}</Text>
      <HStack role="radiogroup" aria-labelledby="confirm-image-quality-label" spacing={2}
        onKeyDown={(event) => handleRadioArrowKeys(event, options.map((option) => option.value), value, (next) => onChange(next as QualityChoice))}>
        {options.map((option) => {
          const selected = value === option.value;
          return (
            <Button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={selected}
              tabIndex={radioTabIndex(options.map((entry) => entry.value), value, option.value)}
              size="sm"
              flex={1}
              variant={selected ? 'solid' : 'outline'}
              // A recorded quality is changed, never silently cleared.
              onClick={() => onChange(selected && allowClear ? '' : option.value)}
            >
              {t(option.label)}
            </Button>
          );
        })}
      </HStack>
    </Stack>
  );
}

export function ConfirmImageDialog({ item, onClose, onSaved }: { item: CaseRecord | null; onClose: () => void; onSaved: (item: CaseRecord) => void }) {
  const t = useT();
  const [patientKey, setPatientKey] = useState('');
  const [laterality, setLaterality] = useState<Laterality>('UNKNOWN');
  const [imageType, setImageType] = useState<RetinalModality>('UNKNOWN');
  const [visitKey, setVisitKey] = useState('');
  const [capturedAt, setCapturedAt] = useState('');
  const [captureSequence, setCaptureSequence] = useState('');
  const [device, setDevice] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [useAsDefault, setUseAsDefault] = useState(true);
  const [quality, setQuality] = useState<QualityChoice>('');
  // Set once Confirm Image is saved but the quality call failed; retries skip the confirm.
  const [confirmedRecord, setConfirmedRecord] = useState<CaseRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [patientError, setPatientError] = useState(false);
  const patientInputRef = useRef<HTMLInputElement | null>(null);
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [editImageType, setEditImageType] = useState(false);
  const [editPatient, setEditPatient] = useState(false);
  const [unlinkPatient, setUnlinkPatient] = useState(false);
  const [editEye, setEditEye] = useState(false);
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
    // Filename sequence stays evidence until the operator explicitly accepts or enters it.
    setCaptureSequence(item.visit_context?.capture_sequence == null ? '' : String(item.visit_context.capture_sequence));
    setDevice(item.visit_context?.device ?? '');
    setReviewer(defaultReviewer);
    setUseAsDefault(true);
    setQuality(recordedQuality(item));
    setConfirmedRecord(null);
    setMetadataOpen(false);
    setEditImageType(false);
    setEditPatient(false);
    setUnlinkPatient(false);
    setEditEye(false);
    setError(null);
    setPatientError(false);
  }, [item]);

  useEffect(() => {
    if (patientError) patientInputRef.current?.focus();
  }, [patientError]);

  const saveQuality = async (saved: CaseRecord) => {
    if (!quality || quality === recordedQuality(saved)) {
      onSaved(saved);
      onClose();
      return;
    }
    try {
      const updated = await admissionApi.review(saved.image_id, {
        revision: saved.revision, reviewer: reviewer.trim(), action: quality, note: 'Image quality recorded at Confirm Image.',
      });
      onSaved(updated);
      onClose();
    } catch {
      setConfirmedRecord(saved);
      setError('Image confirmed, but image quality was not saved. Try again, or continue without it.');
    }
  };

  const save = async () => {
    if (!item || !reviewer.trim()) { setError('Reviewer name is required.'); return; }
    setSaving(true);
    setError(null);
    if (confirmedRecord) {
      try { await saveQuality(confirmedRecord); } finally { setSaving(false); }
      return;
    }
    try {
      const saved = await admissionApi.confirmImage(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        patient_key: hasInternalPatientKey(item) && editPatient && !patientKey.trim() && !unlinkPatient
          ? item.patient_key ?? null : patientKey.trim() || null,
        laterality,
        retinal_modality: imageType,
        visit_key: visitKey.trim() || null,
        captured_at: capturedAt.trim() || null,
        capture_sequence: captureSequence.trim() ? Number(captureSequence) : null,
        device: device.trim() || null,
      });
      if (useAsDefault) setDefaultReviewer(reviewer);
      else setDefaultReviewer('');
      await saveQuality(saved);
    } catch (saveError) {
      if (saveError instanceof Error && saveError.message === 'Patient key must be a short pseudonymous identifier') {
        if (hasInternalPatientKey(item)) setPatientKey('');
        setEditPatient(true);
        setPatientError(true);
      } else {
        setError('Image confirmation could not be saved. Check your entries and try again.');
      }
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
    <Modal isOpen={Boolean(item)} onClose={onClose} isCentered scrollBehavior="inside" size="4xl" initialFocusRef={firstUnresolvedRef}>
      <ModalOverlay />
      <ModalContent
        as="form"
        fontSize="md"
        lineHeight="normal"
        my={4}
        maxH="calc(100dvh - 32px)"
        w="calc(100% - 32px)"
        sx={{
          '.chakra-form__label': { fontSize: 'sm', lineHeight: 'normal', mb: 1.5 },
          '.chakra-checkbox__label': { fontSize: 'sm', lineHeight: 'normal' },
        }}
        noValidate
        onSubmit={(event) => { event.preventDefault(); void save(); }}
      >
        <ModalHeader flexShrink={0}>Confirm Image</ModalHeader>
        <ModalCloseButton />
        <ModalBody minH={0} overflowY="auto">
          <Grid templateColumns={{ base: '1fr', tablet: 'minmax(0, 1.1fr) minmax(0, 1fr)' }} gap={5} alignItems="start">
          <Box
            bg="viewer.background"
            borderRadius="md"
            overflow="hidden"
            display="flex"
            alignItems="center"
            justifyContent="center"
            minH={{ base: '220px', tablet: '360px' }}
            position={{ tablet: 'sticky' }}
            top={0}
          >
            {item?.image_url && (
              <Box
                as="img"
                src={item.image_url}
                alt={`Retinal image ${item.filename ?? item.display_name}`}
                maxW="100%"
                maxH={{ base: '260px', tablet: '60vh' }}
                objectFit="contain"
              />
            )}
          </Box>
          <Stack spacing={4} minW={0}>
            <GuideHint step="confirm-image" />
            {error && <Alert status="error" bg="status.dangerSoft" color="status.danger" alignItems="flex-start"><AlertIcon /><Text fontSize="md" overflowWrap="anywhere">{t(error)}</Text></Alert>}
            <Stack spacing={1}>
              <Text fontSize="md" fontWeight="semibold" overflowWrap="anywhere">{item?.filename ?? item?.display_name}</Text>
              <Text fontSize="sm" color="text.secondary">{t('Only uncertain context needs confirmation. Filename and source metadata are evidence, not clinical truth.')}</Text>
            </Stack>
            {imageTypeResolved && !editImageType ? (
              <SummaryRow label={t('Image type')} value={t(imageType === 'UWF' ? 'Ultra-widefield' : 'Conventional fundus photograph')} note={imageTypeSource} onEdit={() => setEditImageType(true)} />
            ) : (
              <FormControl>
                <FormLabel htmlFor="confirm-image-type">{t('Image type')}</FormLabel>
                <Select ref={!imageTypeResolved || editImageType ? (node) => { initialFocusRef.current = node; } : undefined} id="confirm-image-type" value={imageType} onChange={(event) => setImageType(event.target.value as RetinalModality)}>
                  <option value="UNKNOWN">{t('Not sure yet')}</option>
                  <option value="CFP">{t('Conventional fundus photograph')}</option>
                  <option value="UWF">{t('Ultra-widefield')}</option>
                </Select>
                <Text fontSize="xs" color="text.secondary" mt={1}>{t('If unsure, keep Not sure yet. AI analysis requires a confirmed supported image type.')}</Text>
                {editImageType && imageTypeResolved && <Button type="button" size="xs" variant="ghost" mt={1} onClick={() => setEditImageType(false)}>{t('Done')}</Button>}
              </FormControl>
            )}
            {patientResolved && !editPatient ? (
              <SummaryRow label={t('Patient')} value={item && hasInternalPatientKey(item) ? patientLabel(item) : patientKey} note={item && hasInternalPatientKey(item) ? 'workspace label / existing link kept' : patientSource} onEdit={() => { if (item && hasInternalPatientKey(item)) setPatientKey(''); setEditPatient(true); }} />
            ) : (
              <FormControl isInvalid={patientError}>
                <FormLabel htmlFor="confirm-image-patient-key">{t('Patient')}</FormLabel>
                <Input ref={(node) => { patientInputRef.current = node; if (imageTypeResolved && (editPatient || !patientResolved)) initialFocusRef.current = node; }} id="confirm-image-patient-key" value={patientKey} onChange={(event) => { setPatientKey(event.target.value.toUpperCase()); setUnlinkPatient(false); setPatientError(false); }} placeholder={t('Enter a pseudonymous key or leave blank')} />
                <Text fontSize="xs" color="text.secondary" mt={1}>{t(item && hasInternalPatientKey(item) ? 'Enter an approved pseudonymous key to replace this link. Leaving it blank keeps the current link. Workspace labels are not replacement keys.' : item?.patient_candidate ? 'Suggested from available evidence; confirm or correct it.' : 'Unknown is allowed when no supported evidence is available.')}</Text>
                <FormErrorMessage fontSize="sm" color="status.danger">{t('Use a pseudonymous key with 3-32 characters, starting with a letter and including a number. Use only letters, numbers, hyphens, or underscores.')}</FormErrorMessage>
                {editPatient && item && hasInternalPatientKey(item) && <Button type="button" size="xs" variant="outline" onClick={() => { setPatientKey(item.patient_key ?? ''); setUnlinkPatient(false); setPatientError(false); setEditPatient(false); }}>{t('Keep current patient link')}</Button>}
                {editPatient && item && hasInternalPatientKey(item) && <><Button type="button" size="xs" variant="ghost" onClick={() => { setPatientKey(''); setUnlinkPatient(true); setPatientError(false); }}>{t('Leave this image unlinked')}</Button>{unlinkPatient && <Text fontSize="sm" color="status.warning">{t('This image will be left unlinked when you confirm.')}</Text>}</>}
                {editPatient && patientResolved && item && !hasInternalPatientKey(item) && <Button type="button" size="xs" variant="ghost" mt={1} isDisabled={patientError} onClick={() => setEditPatient(false)}>{t('Done')}</Button>}
              </FormControl>
            )}
            {eyeResolved && !editEye ? (
              <SummaryRow label={t('Eye')} value={t(laterality === 'LEFT' ? 'Left' : laterality === 'RIGHT' ? 'Right' : 'Unknown')} note={eyeSource} onEdit={() => setEditEye(true)} />
            ) : (
              <FormControl>
                <FormLabel htmlFor="confirm-image-eye">{t('Eye')}</FormLabel>
                <Select ref={imageTypeResolved && patientResolved && (editEye || !eyeResolved) ? (node) => { initialFocusRef.current = node; } : undefined} id="confirm-image-eye" value={laterality} onChange={(event) => setLaterality(event.target.value as Laterality)}>
                  <option value="LEFT">{t('Left')}</option>
                  <option value="RIGHT">{t('Right')}</option>
                  <option value="UNKNOWN">{t('Unknown')}</option>
                </Select>
                {editEye && eyeResolved && <Button type="button" size="xs" variant="ghost" mt={1} onClick={() => setEditEye(false)}>{t('Done')}</Button>}
              </FormControl>
            )}
            <QualityChoiceField value={quality} onChange={setQuality} allowClear={recordedQuality(confirmedRecord ?? item) === ''} />
            <ReviewerField compact id="confirm-image-reviewer" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />
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
                {metadataOpen ? t('Hide additional metadata') : t('Additional metadata')}
              </Button>
              <Collapse in={metadataOpen} animateOpacity>
                <Stack id="confirm-image-additional-metadata" spacing={3} mt={3}>
                  <Text fontSize="xs" color="text.secondary">{t('Optional acquisition details. Sequence numbers support evidence only; they do not prove before/after chronology.')}</Text>
                  <FormControl><FormLabel htmlFor="confirm-image-visit">{t('Visit key (optional)')}</FormLabel><Input id="confirm-image-visit" value={visitKey} onChange={(event) => setVisitKey(event.target.value)} placeholder={t('Leave blank when unknown')} /></FormControl>
                  <FormControl><FormLabel htmlFor="confirm-image-capture">{t('Capture date/time (optional)')}</FormLabel><Input id="confirm-image-capture" value={capturedAt} onChange={(event) => setCapturedAt(event.target.value)} placeholder={t('Leave blank when unknown')} /></FormControl>
                  <FormControl><FormLabel htmlFor="confirm-image-sequence">{t('Capture sequence (optional)')}</FormLabel><Input id="confirm-image-sequence" type="number" min={0} value={captureSequence} onChange={(event) => setCaptureSequence(event.target.value)} placeholder={t('Leave blank when unknown')} /></FormControl>
                  {filenameEvidence?.capture_sequence != null && (
                    <HStack align="flex-start" spacing={2}>
                      <Text fontSize="xs" color="text.secondary">{t('Sequence')} {filenameEvidence.capture_sequence} {t('was derived from the supported filename pattern. It is not a before/after claim.')}</Text>
                      {!captureSequence && <Button type="button" size="xs" variant="outline" flexShrink={0} onClick={() => setCaptureSequence(String(filenameEvidence.capture_sequence))}>{t('Use sequence')}</Button>}
                    </HStack>
                  )}
                  <FormControl><FormLabel htmlFor="confirm-image-device">{t('Camera / device (optional)')}</FormLabel><Input id="confirm-image-device" value={device} onChange={(event) => setDevice(event.target.value)} placeholder={t('Leave blank when unknown')} /></FormControl>
                </Stack>
              </Collapse>
            </Box>
          </Stack>
          </Grid>
        </ModalBody>
        <ModalFooter flexShrink={0}>
          <Stack direction={{ base: 'column-reverse', tablet: 'row' }} spacing={2} w="full" align={{ base: 'stretch', tablet: 'center' }} justify="flex-end">
            {confirmedRecord ? (
              <Button type="button" variant="ghost" onClick={() => { onSaved(confirmedRecord); onClose(); }} isDisabled={saving}>{t('Continue without quality')}</Button>
            ) : (
              <Button type="button" variant="ghost" onClick={onClose} isDisabled={saving}>{t('Cancel')}</Button>
            )}
            <Button type="submit" variant="solid" whiteSpace="normal" h="auto" minH="36px" py={2} isLoading={saving}>{confirmedRecord ? t('Save image quality') : t('Confirm image & continue')}</Button>
          </Stack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
