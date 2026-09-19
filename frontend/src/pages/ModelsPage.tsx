import { useLocation } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Placeholder } from '@/components/common/Placeholder';
import { Box, Stack, Text } from '@chakra-ui/react';
import { Activity } from '@/lib/icons';

export function ModelsPage() {
  const { pathname } = useLocation();
  return (
    <Box
      as="main"
      maxW="1440px"
      mx="auto"
      px={{ base: 4, tablet: 5, laptop: 7 }}
      py={{ base: 5, tablet: 6 }}
    >
      <PageHeader pathname={pathname} />
      <Stack spacing={4}>
        <Placeholder
          icon={Activity}
          title="Models &amp; Audit (reserved)"
          message="Provider readiness, provenance, and remote-runtime metadata will be migrated after Worklist. Provider state is intentionally NOT claimed healthy without backend confirmation."
        />
        <Text fontSize="xs" color="text.muted">
          Round 2 deliverable · runtime pill in the header reads /health; it never assumes a healthy state without a successful response.
        </Text>
      </Stack>
    </Box>
  );
}
