import { useLocation } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Placeholder } from '@/components/common/Placeholder';
import { Box, Stack, Text } from '@chakra-ui/react';
import { Database } from '@/lib/icons';

export function DatasetsPage() {
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
          icon={Database}
          title="Datasets (reserved)"
          message="Dataset Workspace is intentionally deferred. The sidebar workspace card previews the selection surface used here."
        />
        <Text fontSize="xs" color="text.muted">
          Round 2 deliverable · dataset workspace backend unchanged · migration pending owner review.
        </Text>
      </Stack>
    </Box>
  );
}
