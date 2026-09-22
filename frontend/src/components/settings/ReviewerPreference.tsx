import { useState } from 'react';
import { FormControl, FormLabel, Input, Text } from '@chakra-ui/react';
import { Section } from '@/components/common/Section';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';

export function ReviewerPreference() {
  const [reviewer, setReviewer] = useState(() => getDefaultReviewer());

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
    </Section>
  );
}
