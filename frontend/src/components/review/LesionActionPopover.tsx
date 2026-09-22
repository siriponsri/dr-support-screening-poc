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
import { lesionReviewApi, type CaseRecord, type LesionLabel } from '@/lib/api';
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
  onClose: () => void;
}

export function LesionActionPopover({ item, selectedLesionId, onSaved, onClose }: LesionActionPopoverProps) {
  const lesion = useMemo(
    () => displayedLesions(item).find((entry) => entry.detection_id === selectedLesionId) ?? null,
    [item, selectedLesionId],
  );
  const evidence = aiEvidenceForLesion(item, selectedLesionId);
  const [reviewer, setReviewer] = useState(() => getDefaultReviewer());
  const [useAsDefault, setUseAsDefault] = useState(() => Boolean(getDefaultReviewer()));
  const [label, setLabel] = useState<LesionLabel>('MICROANEURYSM');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!lesion) return;
    setLabel(lesion.canonical_label as LesionLabel);
    const defaultReviewer = getDefaultReviewer();
    setReviewer((current) => current || defaultReviewer);
    setUseAsDefault(Boolean(defaultReviewer));
    setError(null);
  }, [lesion?.detection_id]);

  if (!lesion || !selectedLesionId) return null;

  const original = labelInfo(evidence?.original_label ?? lesion.originalLabel ?? lesion.canonical_label);
  const current = labelInfo(lesion.canonical_label);
  const originalScore = evidence?.original_score ?? lesion.originalScore ?? lesion.score;

  const save = async (action: 'CORRECT' | 'REJECT') => {
    if (!reviewer.trim() || saving) {
      setError('Reviewer name is required to record this optional change.');
      return;
    }
    if (action === 'CORRECT' && label === (evidence?.original_label ?? lesion.originalLabel)) {
      setError('Choose a different lesion class or cancel.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await lesionReviewApi.review(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        detection_id: selectedLesionId,
        action,
        label: action === 'CORRECT' ? label : undefined,
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
        <PopoverHeader fontWeight="semibold">Optional ROI action</PopoverHeader>
        <PopoverBody>
          <Stack spacing={3}>
            <Text fontSize="sm">
              AI suggestion: <strong>{original.label} · {originalScore.toFixed(2)}</strong>
            </Text>
            {lesion.reviewState === 'CLINICIAN_CORRECTED' && (
              <Text fontSize="xs" color="text.secondary">Current reviewed class: {current.label}. The AI score remains attached to the original class only.</Text>
            )}
            <FormControl>
              <FormLabel fontSize="sm">Change lesion class</FormLabel>
              <Select size="sm" value={label} onChange={(event) => setLabel(event.target.value as LesionLabel)}>
                {LABELS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </Select>
            </FormControl>
            <ReviewerField id="roi-reviewer" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />
            {error && <Text role="alert" fontSize="sm" color="status.danger">{error}</Text>}
            <HStack spacing={2} flexWrap="wrap">
              <Button size="sm" variant="secondary" onClick={() => void save('CORRECT')} isLoading={saving}>Save class correction</Button>
              <Button size="sm" variant="danger" onClick={() => void save('REJECT')} isLoading={saving}>Remove this detection</Button>
              <Button size="sm" variant="ghost" onClick={onClose} isDisabled={saving}>Cancel</Button>
            </HStack>
          </Stack>
        </PopoverBody>
      </PopoverContent>
    </Popover>
  );
}
