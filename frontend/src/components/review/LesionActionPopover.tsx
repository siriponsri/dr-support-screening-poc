import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  FormControl,
  FormLabel,
  HStack,
  Popover,
  PopoverArrow,
  PopoverBody,
  PopoverCloseButton,
  PopoverContent,
  PopoverHeader,
  PopoverTrigger,
  Select,
  Stack,
  Text,
} from '@chakra-ui/react';
import { humanAnnotationApi, lesionReviewApi, type CaseRecord, type HumanAnnotation, type LesionLabel } from '@/lib/api';
import { getDefaultReviewer } from '@/lib/reviewerPreference';
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
  reviewer?: string;
}

export function LesionActionPopover({ item, selectedLesionId, onSaved, onDerived, onClose, reviewer: reviewerProp }: LesionActionPopoverProps) {
  const lesion = useMemo(
    () => displayedLesions(item).find((entry) => entry.detection_id === selectedLesionId) ?? null,
    [item, selectedLesionId],
  );
  const evidence = aiEvidenceForLesion(item, selectedLesionId);
  const [label, setLabel] = useState<LesionLabel>('MICROANEURYSM');
  const [rectangle, setRectangle] = useState<[number, number, number, number]>([0, 0, 1, 1]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!lesion) return;
    setLabel(labelInfo(lesion.canonical_label).value);
    setRectangle(lesion.rectangle);
    setError(null);
  }, [lesion?.detection_id]);

  if (!lesion || !selectedLesionId) return null;

  const current = labelInfo(lesion.canonical_label);
  const originalScore = evidence?.original_score ?? lesion.originalScore ?? lesion.score;
  const reviewer = reviewerProp?.trim() || getDefaultReviewer() || 'Clinician';
  const rectangleChanged = rectangle.some((value, index) => value !== lesion.rectangle[index]);
  const classChanged = label !== lesion.canonical_label;

  const confirm = async () => {
    if (saving) return;
    if (rectangle[0] < 0 || rectangle[1] < 0 || rectangle[2] <= rectangle[0] || rectangle[3] <= rectangle[1]) {
      setError('ROI geometry must have positive width and height.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const reviewed = await lesionReviewApi.review(item.image_id, {
        revision: item.revision,
        reviewer,
        detection_id: selectedLesionId,
        action: classChanged || rectangleChanged ? 'CORRECT' : 'CONFIRM',
        label: classChanged || rectangleChanged ? label : undefined,
        rectangle: classChanged || rectangleChanged ? rectangle : undefined,
      });
      const intent = classChanged || rectangleChanged ? 'CORRECT_AS_HUMAN' : 'USE_AS_HUMAN';
      const saved = await humanAnnotationApi.deriveFromAi(item.image_id, {
        revision: reviewed.revision,
        reviewer,
        detection_id: selectedLesionId,
        intent,
      });
      const annotation = saved.human_annotations?.find((entry) => entry.source_detection_id === selectedLesionId);
      if (!annotation) throw new Error('The human annotation could not be loaded. Refresh the case and try again.');
      onDerived(saved, annotation, intent);
      onClose();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The optional ROI change could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await lesionReviewApi.review(item.image_id, {
        revision: item.revision,
        reviewer,
        detection_id: selectedLesionId,
        action: 'REJECT',
      });
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
            <FormControl>
              <FormLabel htmlFor="ai-roi-class" fontSize="sm">Lesion class</FormLabel>
              <Select id="ai-roi-class" size="sm" value={label} onChange={(event) => setLabel(event.target.value as LesionLabel)}>
                {LABELS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </Select>
            </FormControl>
            <Text fontSize="sm"><strong>Model score:</strong> {originalScore.toFixed(2)}</Text>
            <Text fontSize="xs" color="text.secondary">Model score, not a clinical probability.</Text>
            <Text fontSize="sm"><strong>Model:</strong> PRISM-DR</Text>
            <Text fontSize="xs" color="text.secondary">The original AI class, score, geometry, and model remain in the review record.</Text>
            <HStack spacing={2}>
              {(['x1', 'y1', 'x2', 'y2'] as const).map((name, index) => (
                <FormControl key={name}>
                  <FormLabel htmlFor={`ai-roi-${name}`} fontSize="xs">{name}</FormLabel>
                  <input
                    id={`ai-roi-${name}`}
                    aria-label={`ROI ${name}`}
                    type="number"
                    value={rectangle[index]}
                    onChange={(event) => setRectangle((currentRectangle) => currentRectangle.map((value, valueIndex) => valueIndex === index ? Number(event.target.value) : value) as [number, number, number, number])}
                    style={{ width: '100%', border: '1px solid var(--chakra-colors-border-default)', borderRadius: '4px', padding: '4px' }}
                  />
                </FormControl>
              ))}
            </HStack>
            {classChanged || rectangleChanged ? <Text fontSize="xs" color="text.secondary">This correction will be recorded as a human annotation without the AI score.</Text> : null}
            {error && <Text role="alert" fontSize="sm" color="status.danger">{error}</Text>}
            <Stack spacing={2}>
              <Button size="sm" variant="solid" onClick={() => void confirm()} isLoading={saving}>Confirm</Button>
              <Button size="sm" variant="danger" onClick={() => void remove()} isLoading={saving}>Remove</Button>
              <Button size="sm" variant="ghost" onClick={onClose} isDisabled={saving}>Close</Button>
            </Stack>
          </Stack>
        </PopoverBody>
      </PopoverContent>
    </Popover>
  );
}
