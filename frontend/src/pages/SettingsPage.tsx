import { useLocation } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Placeholder } from '@/components/common/Placeholder';
import { Box, Stack, Text } from '@chakra-ui/react';
import { Settings2 } from '@/lib/icons';

export function SettingsPage() {
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
          icon={Settings2}
          title="Settings (reserved)"
          message="Workspace, runtime, and clinician preferences will land here in a later round. Behavior and remote provider state remain on the FastAPI backend until then."
        />
        <Text fontSize="xs" color="text.muted">
          Round 2 deliverable · no backend changes · preferences remain server-side environment variables.
        </Text>
      </Stack>
    </Box>
  );
}
