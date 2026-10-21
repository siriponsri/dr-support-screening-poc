import { useNavigationGuard } from '@/components/shell/NavigationGuard';
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
  const navigationGuard = useNavigationGuard();
  const { previousId, nextId, previousImageConfirmed, nextImageConfirmed, position, total, loading, error, retry } = useCaseNeighbors(imageId);

  const move = async (target: string | null, imageConfirmed: boolean) => {
    if (!target) return;
    if (navigationGuard.hasGuard()) {
      if (!(await navigationGuard.request('case'))) return;
    } else {
      if (guarded && confirm && !(await confirm(SWITCH_IMAGE_DIALOG))) return;
      if (onBeforeSwitch && !(await onBeforeSwitch())) return;
    }
    navigationGuard.approved(() => {
      if (imageConfirmed) navigate(`/review/${encodeURIComponent(target)}`);
      else navigate('/worklist', { state: { openConfirmImage: target } });
    });
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
        {error ? 'Worklist unavailable' : loading ? 'Loading cases…' : position && total ? `Image ${position} of ${total}` : 'Case'}
      </Text>
      {error && <Button size="sm" variant="outline" onClick={retry}>Retry Worklist</Button>}
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
