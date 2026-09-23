import { Button, HStack, Text } from '@chakra-ui/react';
import { useNavigate } from 'react-router-dom';
import { useCaseNeighbors } from '@/lib/caseNavigation';
import { ArrowLeft, ArrowRight } from '@/lib/icons';

interface CaseNavigationProps {
  imageId: string;
  dirty?: boolean;
  onBeforeNavigate?: () => boolean;
  onSaveAndNext?: (nextId: string | null) => void;
  saveAndNextLabel?: string;
  saveAtEndLabel?: string;
  actionDisabled?: boolean;
  routePrefix?: string;
}

export function CaseNavigation({ imageId, dirty = false, onBeforeNavigate, onSaveAndNext, saveAndNextLabel = 'Save & Next Case', saveAtEndLabel = 'Complete case', actionDisabled = false, routePrefix = 'review' }: CaseNavigationProps) {
  const navigate = useNavigate();
  const { previousId, nextId, position, total, loading } = useCaseNeighbors(imageId);

  const move = (target: string | null) => {
    if (!target) return;
    if (dirty && onBeforeNavigate && !onBeforeNavigate()) return;
    navigate(`/${routePrefix}/${encodeURIComponent(target)}`);
  };

  return (
    <HStack spacing={2} justify="space-between" flexWrap="wrap" aria-label="Case navigation">
      <Button
        size="sm"
        variant="ghost"
        leftIcon={<ArrowLeft size={14} />}
        onClick={() => move(previousId)}
        isDisabled={loading || !previousId}
        aria-label="Previous case"
      >
        Previous
      </Button>
      <Text fontSize="sm" color="text.secondary" aria-live="polite">
        {loading ? 'Loading cases…' : position && total ? `${position} of ${total}` : 'Case'}
      </Text>
      {onSaveAndNext ? (
        <Button size="sm" variant="solid" onClick={() => onSaveAndNext(nextId)} isDisabled={loading || actionDisabled}>
          {nextId ? saveAndNextLabel : saveAtEndLabel}
        </Button>
      ) : (
        <Button
          size="sm"
          variant="ghost"
          rightIcon={<ArrowRight size={14} />}
          onClick={() => move(nextId)}
          isDisabled={loading || !nextId}
          aria-label="Next case"
        >
          Next
        </Button>
      )}
    </HStack>
  );
}
