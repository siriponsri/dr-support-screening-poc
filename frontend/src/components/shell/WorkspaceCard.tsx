import {
  Box,
  Button,
  HStack,
  Link as ChakraLink,
  Spinner,
  Text,
  VStack,
  type FlexProps,
} from '@chakra-ui/react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Folder, FolderOpen, Plus } from '@/lib/icons';
import { useWorkspace } from './workspace';

interface WorkspaceCardProps extends FlexProps {
  variant?: 'full' | 'compact';
}

export function WorkspaceCard({ variant = 'full', ...rest }: WorkspaceCardProps) {
  const workspaceState = useWorkspace();
  const { activeWorkspace, status } = workspaceState;

  if (variant === 'compact') {
    return (
      <ChakraLink
        as={Link}
        to="/settings"
        display="grid"
        placeItems="center"
        w="36px"
        h="36px"
        mx="auto"
        borderRadius="md"
        bg={activeWorkspace ? 'action.primarySoft' : 'surface.subtle'}
        color={activeWorkspace ? 'action.primaryHover' : 'text.secondary'}
        borderWidth="1px"
        borderColor={activeWorkspace ? 'action.primaryBorder' : 'border.subtle'}
        title={activeWorkspace ? activeWorkspace.name : 'Workspace manager'}
        aria-label={activeWorkspace ? `Current workspace: ${activeWorkspace.name}` : 'Open workspace manager'}
        _hover={{ borderColor: 'border.strong', bg: 'surface.subtle' }}
        _focusVisible={{ boxShadow: 'focus', outline: 'none' }}
      >
        {status === 'loading' ? <Spinner size="xs" /> : <Folder size={16} strokeWidth={2.25} aria-hidden="true" />}
      </ChakraLink>
    );
  }

  if (status === 'loading') {
    return (
      <Box aria-label="Loading workspace context" borderRadius="lg" borderWidth="1px" borderColor="border.subtle" bg="surface.subtle" p={3} {...rest}>
        <HStack spacing={2} color="text.secondary">
          <Spinner size="xs" />
          <Text fontSize="sm">Loading workspace context</Text>
        </HStack>
      </Box>
    );
  }

  if (activeWorkspace) return <ActiveWorkspaceCard workspace={activeWorkspace} {...rest} />;

  const degraded = status === 'error' || status === 'degraded';
  return (
    <Box
      role="group"
      aria-label="No active workspace"
      borderRadius="lg"
      borderWidth="1px"
      borderStyle="dashed"
      borderColor={degraded ? 'status.warningBorder' : 'border.default'}
      bg={degraded ? 'status.warningSoft' : 'surface.panel'}
      p={3}
      {...rest}
    >
      <HStack spacing={2} align="flex-start">
        <Box
          as="span"
          display="grid"
          placeItems="center"
          w="26px"
          h="26px"
          borderRadius="md"
          bg={degraded ? 'surface.panel' : 'surface.subtle'}
          color={degraded ? 'status.warning' : 'text.secondary'}
          flexShrink={0}
        >
          {degraded ? <AlertTriangle size={14} strokeWidth={2.25} aria-hidden="true" /> : <Plus size={14} strokeWidth={2.25} aria-hidden="true" />}
        </Box>
        <VStack align="flex-start" spacing={1} minW={0}>
          <Text fontSize="sm" fontWeight="semibold">
            {degraded ? 'Workspace unavailable' : 'No workspace open'}
          </Text>
          <Text fontSize="xs" color="text.secondary">
            {degraded ? 'Check the local API or open Settings to recover.' : 'Choose a workspace before reviewing cases.'}
          </Text>
          <Button as={Link} to="/settings" size="sm" variant="ghost" px={0} h="28px" color="action.primaryHover">
            Open workspace manager
          </Button>
        </VStack>
      </HStack>
    </Box>
  );
}

function ActiveWorkspaceCard({ workspace, ...rest }: { workspace: ReturnType<typeof useWorkspace>['activeWorkspace'] } & FlexProps) {
  if (!workspace) return null;
  return (
    <Box
      role="group"
      aria-label={`Current workspace: ${workspace.name}`}
      borderRadius="lg"
      borderWidth="1px"
      borderColor="action.primaryBorder"
      bg="action.primarySoft"
      p={3}
      {...rest}
    >
      <HStack spacing={2} align="center" mb={2}>
        <Box
          as="span"
          display="grid"
          placeItems="center"
          w="26px"
          h="26px"
          borderRadius="md"
          bg="surface.panel"
          color="action.primaryHover"
          flexShrink={0}
        >
          <FolderOpen size={14} strokeWidth={2.25} aria-hidden="true" />
        </Box>
        <Text
          as="span"
          fontSize="xxs"
          fontWeight="bold"
          textTransform="uppercase"
          letterSpacing="0.08em"
          color="action.primaryHover"
        >
          Active workspace
        </Text>
      </HStack>
      <Text fontSize="md" fontWeight="semibold" color="text.primary" noOfLines={1} title={workspace.name}>
        {workspace.name}
      </Text>
      <Text fontSize="xs" color="text.secondary" noOfLines={2} title={workspace.database_path} mt={1} fontFamily="mono">
        {workspace.database_path}
      </Text>
      <ChakraLink as={Link} to="/settings" display="inline-block" mt={2} fontSize="xs" fontWeight="semibold" color="action.primaryHover">
        Manage workspace
      </ChakraLink>
    </Box>
  );
}
