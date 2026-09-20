import { useLocation } from 'react-router-dom';
import { Box } from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { WorkspaceManager } from '@/components/workspace/WorkspaceManager';
import { ModelConnectionSettings } from '@/components/settings/ModelConnectionSettings';

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
      <PageHeader
        pathname={pathname}
        title="Settings"
        subtitle="Manage the local workspace used by this review station"
      />
      <WorkspaceManager />
      <Box mt={5}>
        <ModelConnectionSettings />
      </Box>
    </Box>
  );
}
