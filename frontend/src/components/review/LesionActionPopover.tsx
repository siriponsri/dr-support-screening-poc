import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  HStack,
  Popover,
  PopoverArrow,
  PopoverBody,
  PopoverCloseButton,
  PopoverContent,
  PopoverHeader,
  PopoverTrigger,
  Stack,
  Text,
} from '@chakra-ui/react';
import { humanAnnotationApi, lesionReviewApi, type CaseRecord, type HumanAnnotation, type LesionLabel } from '@/lib/api';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';
import { ReviewerField } from '@/components/common/ReviewerField';
import { aiEvidenceForLesion, displayedLesions } from './lesionPresentation';

const LABELS: Array<{ value: LesionLabel; label: string; short: string }> = [
  { value: 'MICROANEURYSM', label: 'Microaneurysm', short: 'MA' },
  { value: 'HEMORRHAGE', label: 'Hemorrhage', short: 'HE' },
  { value: 'HARD_EXUDATE', label: 'Hard exudate', short: 'EX' },
  { value: 'SOFT_EXUDATE', label: 'Soft exudate', short: 'SE' },
];

function labelInfo(label: string | null | undefined) {
  return LABELS.find((option) => option.value === label) ?? { value: 'MICROANEURYSM' as LesionLabel, label: 'Unknown class', short: 'ROI' };
}

interface LesionActionPopoverProps {
  item: CaseRecord;
  selectedLesionId: string | null;
  onSaved: (item: CaseRecord) => void;
  onDerived: (item: CaseRecord, annotation: HumanAnnotation, intent: 'USE_AS_HUMAN' | 'CORRECT_AS_HUMAN') => void;
  onClose: () => void;
}

export function LesionActionPopover({ item, selectedLesionId, onSaved, onDerived, onClose }: LesionActionPopoverProps) {
  const lesion = useMemo(
    () => displayedLesions(item).find((entry) => entry.detection_id === selectedLesionId) ?? null,
    [item, selectedLesionId],
  );
  const evidence = aiEvidenceForLesion(item, selectedLesionId);
  const [reviewer, setReviewer] = useState(() => getDefaultReviewer());
  const [useAsDefault, setUseAsDefault] = useState(() => Boolean(getDefaultReviewer()));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!lesion) return;
    const defaultReviewer = getDefaultReviewer();
    setReviewer((current) => current || defaultReviewer);
    setUseAsDefault(Boolean(defaultReviewer));
    setError(null);
  }, [lesion?.detection_id]);

  if (!lesion || !selectedLesionId) return null;

  const original = labelInfo(evidence?.original_label ?? lesion.originalLabel ?? lesion.canonical_label);
  const current = labelInfo(lesion.canonical_label);
  const originalScore = evidence?.original_score ?? lesion.originalScore ?? lesion.score;

  const derive = async (intent: 'USE_AS_HUMAN' | 'CORRECT_AS_HUMAN') => {
    if (!reviewer.trim() || saving) {
      setError('Reviewer name is required to create a human annotation.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await humanAnnotationApi.deriveFromAi(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        detection_id: selectedLesionId,
        intent,
      });
      const annotation = saved.human_annotations?.find((entry) => entry.source_detection_id === selectedLesionId);
      if (!annotation) throw new Error('The human annotation could not be loaded. Refresh the case and try again.');
      setDefaultReviewer(useAsDefault ? reviewer : '');
      onDerived(saved, annotation, intent);
      onClose();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The optional ROI change could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!reviewer.trim() || saving) {
      setError('Reviewer name is required to record this change.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await lesionReviewApi.review(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        detection_id: selectedLesionId,
        action: 'REJECT',
      });
      setDefaultReviewer(useAsDefault ? reviewer : '');
      onSaved(saved);
      onClose();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The optional ROI change could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Popover isOpen onClose={onClose} closeOnBlur={false} placement="top-start">
      <PopoverTrigger>
        <Button size="sm" variant="secondary" aria-label={`Selected AI suggestion: ${current.short}`}>
          Selected: {current.short}{lesion.displayScore === null ? ' - clinician corrected' : ` - ${lesion.displayScore.toFixed(2)}`}
        </Button>
      </PopoverTrigger>
      <PopoverContent maxW="340px">
        <PopoverArrow />
        <PopoverCloseButton />
          <PopoverHeader fontWeight="semibold">AI suggestion</PopoverHeader>
          <PopoverBody>
            <Stack spacing={3}>
            <Text fontSize="sm"><strong>Lesion:</strong> {original.label}</Text>
            <Text fontSize="sm"><strong>Model score:</strong> {originalScore.toFixed(2)}</Text>
            <Text fontSize="xs" color="text.secondary">Model score, not a clinical probability.</Text>
            <Text fontSize="sm"><strong>Model:</strong> PRISM-DR</Text>
            <Text fontSize="xs" color="text.secondary">The original AI suggestion is retained in the review record.</Text>
            {lesion.reviewState === 'CLINICIAN_CORRECTED' && <Text fontSize="sm">Current reviewed class: {current.label}. The score remains with the original AI suggestion.</Text>}
            <ReviewerField id="roi-reviewer" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />
            {error && <Text role="alert" fontSize="sm" color="status.danger">{error}</Text>}
            <Stack spacing={2}>
              <Button size="sm" variant="solid" onClick={() => void derive('USE_AS_HUMAN')} isLoading={saving}>Use as human annotation</Button>
              <Button size="sm" variant="outline" onClick={() => void derive('CORRECT_AS_HUMAN')} isLoading={saving}>Correct annotation</Button>
              <Button size="sm" variant="danger" onClick={() => void remove()} isLoading={saving}>Remove from reviewed result</Button>
              <Button size="sm" variant="ghost" onClick={onClose} isDisabled={saving}>Close</Button>
            </Stack>
          </Stack>
        </PopoverBody>
      </PopoverContent>
    </Popover>
  );
}
