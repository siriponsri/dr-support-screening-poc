import { Link as RouterLink, useLocation } from 'react-router-dom';
import { Box, Button, Stack, Text } from '@chakra-ui/react';
import { Compass } from '@/lib/icons';
import { PageHeader } from '@/components/common/PageHeader';

export function NotFoundPage() {
  const { pathname } = useLocation();
  return (
    <Box
      as="main"
      maxW="720px"
      mx="auto"
      px={{ base: 4, tablet: 5, laptop: 7 }}
      py={{ base: 6, tablet: 10 }}
    >
      <PageHeader
        title="Route not found"
        subtitle={`No shell route matches "${pathname}".`}
        kicker="404"
      />
      <Stack spacing={4} mt={4}>
        <Text fontSize="sm" color="text.secondary">
          Use the navigation to continue.
        </Text>
        <Stack direction={{ base: 'column', tablet: 'row' }} spacing={3}>
          <Button as={RouterLink} to="/worklist" leftIcon={<Compass size={14} strokeWidth={2.25} />}>
            Go to worklist
          </Button>
          <Button as={RouterLink} to="/datasets" variant="outline">
            Browse datasets
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}
