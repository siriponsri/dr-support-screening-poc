import { useLocation } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Placeholder } from '@/components/common/Placeholder';
import { Box, Stack, Text } from '@chakra-ui/react';
import { Eye } from '@/lib/icons';

export function ReviewPage() {
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
          icon={Eye}
          title="Review (reserved)"
          message="Clinician review surface (image viewer, AI panel, action bar) will be migrated after the Worklist. Mobile annotation UX is not part of this round."
        />
        <Text fontSize="xs" color="text.muted">
          Round 2 deliverable · review surface remains on the legacy /ui/ shell during migration.
        </Text>
      </Stack>
    </Box>
  );
}
