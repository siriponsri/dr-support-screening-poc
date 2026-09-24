import { Button, HStack, Text } from '@chakra-ui/react';
import { useNavigate } from 'react-router-dom';
import { useCaseNeighbors } from '@/lib/caseNavigation';
import { ArrowLeft, ArrowRight } from '@/lib/icons';
import { SWITCH_IMAGE_DIALOG, type ConfirmDialogOptions } from './ConfirmDialog';

interface CaseNavigationProps {
  imageId: string;
  /**
   * True while the current image is not complete or the current stage has
   * unconfirmed edits. Previous/Next then asks once before switching.
   */
  guarded?: boolean;
  /** Shared page dialog; required when `guarded` can be true. */
  confirm?: (options: ConfirmDialogOptions) => Promise<boolean>;
  /** Called after the clinician accepts a guarded switch, before navigation. */
  onBeforeSwitch?: () => Promise<boolean> | boolean;
}

/**
 * Previous/Next between Worklist images. Switching always opens the other
 * case at Review after its persisted Confirm Image milestone.
 */
export function CaseNavigation({ imageId, guarded = false, confirm, onBeforeSwitch }: CaseNavigationProps) {
  const navigate = useNavigate();
  const { previousId, nextId, previousImageConfirmed, nextImageConfirmed, position, total, loading } = useCaseNeighbors(imageId);

  const move = async (target: string | null, imageConfirmed: boolean) => {
    if (!target) return;
    if (guarded && confirm) {
      const accepted = await confirm(SWITCH_IMAGE_DIALOG);
      if (!accepted) return;
    }
    if (onBeforeSwitch && !(await onBeforeSwitch())) return;
    if (imageConfirmed) navigate(`/review/${encodeURIComponent(target)}`);
    else navigate('/worklist', { state: { openConfirmImage: target } });
  };

  return (
    <HStack spacing={2} justify="space-between" flexWrap="wrap" aria-label="Case navigation">
      <Button
        size="sm"
        variant="ghost"
        leftIcon={<ArrowLeft size={14} />}
        onClick={() => void move(previousId, previousImageConfirmed)}
        isDisabled={loading || !previousId}
        aria-label="Previous case"
      >
        Previous
      </Button>
      <Text fontSize="sm" color="text.secondary" aria-live="polite">
        {loading ? 'Loading cases…' : position && total ? `Image ${position} of ${total}` : 'Case'}
      </Text>
      <Button
        size="sm"
        variant="ghost"
        rightIcon={<ArrowRight size={14} />}
        onClick={() => void move(nextId, nextImageConfirmed)}
        isDisabled={loading || !nextId}
        aria-label="Next case"
      >
        Next
      </Button>
    </HStack>
  );
}
