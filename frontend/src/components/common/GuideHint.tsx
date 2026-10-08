import { useEffect, useState } from 'react';
import { Box, Button, Flex, Text } from '@chakra-ui/react';
import {
  clearGuideOfferPending,
  getGuideModeEnabled,
  getGuideOfferPending,
  setGuideModeEnabled,
} from '@/lib/hintPreference';

export type GuideStep = 'confirm-image' | 'review' | 'grade' | 'findings';

const STEP_HINTS: Record<GuideStep, string> = {
  'confirm-image': 'Check patient, eye, and image type, then confirm.',
  review: 'Review the retinal image and AI evidence. Continue when ready.',
  grade: 'Choose the final physician grade; AI is only a suggestion.',
  findings: 'Correct or reject AI, add missing findings; Finish saves and opens the next case.',
};

function GuideMessage({ offer, onTurnOff, onDismiss }: {
  offer: boolean;
  onTurnOff: () => void;
  onDismiss: () => void;
}) {
  return (
    <Flex
      data-testid="guide-hint"
      minH="36px"
      align="center"
      flexWrap="wrap"
      columnGap={3}
      rowGap={1}
      py={1}
    >
      <Text flex="1 1 240px" minW={0} fontSize="sm" color="text.secondary">
        {offer ? 'First review complete. Turn off Guide mode?' : null}
      </Text>
      {offer && <Button size="xs" variant="ghost" onClick={onDismiss}>Not now</Button>}
      <Button size="xs" variant="ghost" onClick={onTurnOff}>Turn off Guide mode</Button>
    </Flex>
  );
}

export function GuideHint({ step, offerOnly = false }: { step: GuideStep; offerOnly?: boolean }) {
  const [enabled, setEnabled] = useState(() => getGuideModeEnabled());
  const [offer, setOffer] = useState(() => getGuideOfferPending());

  useEffect(() => {
    if (enabled && offer) clearGuideOfferPending();
  }, [enabled, offer]);

  const turnOff = () => {
    setGuideModeEnabled(false);
    clearGuideOfferPending();
    setOffer(false);
    setEnabled(false);
  };

  const dismissOffer = () => {
    clearGuideOfferPending();
    setOffer(false);
  };

  if (offerOnly && (!enabled || !offer)) return null;
  if (!enabled) return <Box minH="36px" visibility="hidden" aria-hidden="true" />;

  if (offer) {
    return <GuideMessage offer onTurnOff={turnOff} onDismiss={dismissOffer} />;
  }

  if (offerOnly) return null;

  return (
    <Flex
      data-testid="guide-hint"
      minH="36px"
      align="center"
      flexWrap="wrap"
      columnGap={3}
      rowGap={1}
      py={1}
    >
      <Text flex="1 1 240px" minW={0} fontSize="sm" color="text.secondary">{STEP_HINTS[step]}</Text>
      <Button size="xs" variant="ghost" onClick={turnOff}>Turn off Guide mode</Button>
    </Flex>
  );
}

export function GuideCompletionOffer() {
  return <GuideHint step="review" offerOnly />;
}
