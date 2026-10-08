import { useState } from 'react';
import { Checkbox, FormControl, FormLabel, Input, Text } from '@chakra-ui/react';
import { Section } from '@/components/common/Section';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';
import { getGuideModeEnabled, setGuideModeEnabled } from '@/lib/hintPreference';

export function ReviewerPreference() {
  const [reviewer, setReviewer] = useState(() => getDefaultReviewer());
  const [guideEnabled, setGuideEnabled] = useState(() => getGuideModeEnabled());

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
          isChecked={guideEnabled}
          onChange={(event) => { const checked = event.target.checked; setGuideEnabled(checked); setGuideModeEnabled(checked); }}
        >
          Guide mode
        </Checkbox>
        <Text mt={2} fontSize="xs" color="text.secondary">Brief step hints only.</Text>
      </FormControl>
    </Section>
  );
}
