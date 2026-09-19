import { useLocation } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Placeholder } from '@/components/common/Placeholder';
import { Box, Stack, Text } from '@chakra-ui/react';
import { ListChecks } from '@/lib/icons';

export function WorklistPage() {
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
          icon={ListChecks}
          title="Worklist (reserved)"
          message="The existing clinical worklist will be migrated in the next round. Routing, navigation state, and shell chrome are now wired up."
        />
        <Text fontSize="xs" color="text.muted">
          Round 2 deliverable · shell + routing only · worklist migration pending owner review.
        </Text>
      </Stack>
    </Box>
  );
}
