import { useState } from 'react';
import { Checkbox, FormControl, FormLabel, Input, Text } from '@chakra-ui/react';
import { Section } from '@/components/common/Section';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';
import { getHintsEnabled, setHintsEnabled } from '@/lib/hintPreference';

export function ReviewerPreference() {
  const [reviewer, setReviewer] = useState(() => getDefaultReviewer());
  const [hintsEnabled, setHintsEnabledState] = useState(() => getHintsEnabled());

  const updateReviewer = (value: string) => {
    setReviewer(value);
    setDefaultReviewer(value);
  };

  return (
    <Section title="Review preferences" description="Set a workstation default for new review records. It is editable and is not an authenticated identity.">
      <FormControl maxW={{ base: '100%', tablet: '420px' }}>
        <FormLabel htmlFor="default-reviewer">Default reviewer</FormLabel>
        <Input
          id="default-reviewer"
          value={reviewer}
          onChange={(event) => updateReviewer(event.target.value)}
          placeholder="Enter reviewer name"
          autoComplete="name"
        />
        <Text mt={2} fontSize="xs" color="text.secondary">
          New or unattributed review forms use this value. Clear it for a blank form; previously saved reviewers are unchanged.
        </Text>
      </FormControl>
      <FormControl mt={5} maxW={{ base: '100%', tablet: '420px' }}>
        <Checkbox
          isChecked={hintsEnabled}
          onChange={(event) => { const checked = event.target.checked; setHintsEnabledState(checked); setHintsEnabled(checked); }}
        >
          Show next action hints
        </Checkbox>
        <Text mt={2} fontSize="xs" color="text.secondary">Hints are guidance only. They do not change clinical state and are stored on this workstation.</Text>
      </FormControl>
    </Section>
  );
}
