import {
  Button,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  HStack,
  SimpleGrid,
  Stack,
  Switch,
  Text,
} from '@chakra-ui/react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { drGradeLabel, type CaseRecord } from '@/lib/api';
import { RetinalCanvas } from '@/components/review/RetinalCanvas';
import { StatusBadge } from '@/components/common/StatusBadge';
import { patientLabel, hasInternalPatientKey } from '@/lib/patientPresentation';
import { finalGradeKey, lesionReviewState } from './worklistModel';
import { reviewStatus } from './ReviewStatusCell';

function findingsSummary(item: CaseRecord): string {
  const state = lesionReviewState(item);
  const count = item.human_annotations.length;
  // An empty reviewed set means "reviewed", never "no lesions".
  if (state === 'reviewed-none') return 'Reviewed, none recorded';
  if (count > 0) return `${count} finding${count === 1 ? '' : 's'} recorded`;
  return state === 'in-progress' ? 'Review in progress' : 'Not reviewed yet';
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <Stack spacing={0.5} minW={0}>
      <Text fontSize="xs" color="text.secondary">{label}</Text>
      <Text fontWeight="semibold" overflowWrap="anywhere">{value}</Text>
    </Stack>
  );
}

/** Read-only look at one Worklist image without leaving the list. */
export function QuickLookDrawer({ item, onClose }: { item: CaseRecord | null; onClose: () => void }) {
  const [showAi, setShowAi] = useState(true);
  const [showHuman, setShowHuman] = useState(true);
  useEffect(() => { setShowAi(true); setShowHuman(true); }, [item?.image_id]);

  const finalGrade = item ? finalGradeKey(item) : null;
  const gradeText = finalGrade === 'U' ? 'Ungradable' : finalGrade != null ? `Grade ${finalGrade}: ${drGradeLabel(Number(finalGrade))}` : 'Not recorded';
  const patient = item ? (hasInternalPatientKey(item) ? patientLabel(item) : item.patient_key ?? 'Not linked') : '';
  const eye = item?.laterality === 'LEFT' ? 'Left' : item?.laterality === 'RIGHT' ? 'Right' : 'Not confirmed';
  const hasAi = Boolean(item?.lesion_review?.lesions?.length);

  return (
    <Drawer isOpen={Boolean(item)} onClose={onClose} placement="right" size="lg">
      <DrawerOverlay />
      <DrawerContent aria-label="Quick look">
        <DrawerCloseButton />
        {item && (
          <>
            <DrawerHeader pr={12}>
              <Stack spacing={1}>
                <Text fontSize="lg" fontWeight="semibold" overflowWrap="anywhere">{item.filename ?? item.display_name}</Text>
                <HStack spacing={2}><StatusBadge tone={reviewStatus(item).tone}>{reviewStatus(item).label}</StatusBadge><Text fontSize="sm" color="text.secondary">{patient} / {eye}</Text></HStack>
              </Stack>
            </DrawerHeader>
            <DrawerBody>
              <Stack spacing={4}>
                <RetinalCanvas item={item} showAi={showAi && hasAi} showHuman={showHuman} />
                <HStack spacing={5} flexWrap="wrap">
                  <HStack as="label" spacing={2}><Switch isChecked={showAi && hasAi} isDisabled={!hasAi} onChange={(event) => setShowAi(event.target.checked)} /><Text fontSize="sm">AI suggestions{hasAi ? '' : ' (none shown)'}</Text></HStack>
                  <HStack as="label" spacing={2}><Switch isChecked={showHuman} onChange={(event) => setShowHuman(event.target.checked)} /><Text fontSize="sm">Clinician findings</Text></HStack>
                </HStack>
                <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={4} borderTopWidth="1px" borderColor="border.subtle" pt={4}>
                  <Fact label="Final DR grade" value={gradeText} />
                  <Fact label="Findings" value={findingsSummary(item)} />
                  <Fact label="Reviewer" value={item.clinician_review?.reviewer ?? 'Not recorded'} />
                  <Fact label="Image type" value={item.modality === 'UNKNOWN' ? 'Not confirmed' : item.modality} />
                </SimpleGrid>
                <Text fontSize="xs" color="text.muted">View only. AI suggestions are optional evidence; the clinician record is authoritative.</Text>
              </Stack>
            </DrawerBody>
            <DrawerFooter gap={2}>
              <Button variant="ghost" onClick={onClose}>Close</Button>
              {item.queue_state !== 'EXCLUDED' && <Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} variant="solid">Open review</Button>}
            </DrawerFooter>
          </>
        )}
      </DrawerContent>
    </Drawer>
  );
}
