/**
 * Workspace card — the "CURRENT WORKSPACE" panel pinned mid-sidebar.
 *
 * Two visual states:
 *  - empty (no workspace selected) — minimal call-to-action.
 *  - populated (one workspace) — name, modality, case counts.
 *
 * The compact variant fits the icon-only collapsed sidebar and only shows
 * a single highlighted dot + tooltip.
 */
import {
  Box,
  HStack,
  Text,
  VStack,
  type FlexProps,
} from '@chakra-ui/react';
import { Folder, FolderOpen, Plus } from '@/lib/icons';
import { useWorkspace, type WorkspaceSummary } from './workspace';

interface WorkspaceCardProps extends FlexProps {
  variant?: 'full' | 'compact';
}

export function WorkspaceCard({ variant = 'full', ...rest }: WorkspaceCardProps) {
  const { workspace } = useWorkspace();

  if (variant === 'compact') {
    return workspace ? <CompactWorkspaceChip workspace={workspace} /> : null;
  }
  return workspace ? <FullWorkspaceCard workspace={workspace} {...rest} /> : <EmptyWorkspaceHint {...rest} />;
}

function FullWorkspaceCard({ workspace, ...rest }: { workspace: WorkspaceSummary } & FlexProps) {
  return (
    <Box
      role="group"
      aria-label={`Current workspace: ${workspace.label}`}
      borderRadius="lg"
      borderWidth="1px"
      borderColor="border.subtle"
      bg="surface.subtle"
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
          bg="brand.50"
          color="brand.700"
          flexShrink={0}
        >
          <FolderOpen size={14} strokeWidth={2.25} aria-hidden="true" />
        </Box>
        <VStack align="flex-start" spacing={0} minW={0} flex={1}>
          <Text
            as="span"
            fontSize="xs"
            fontWeight="bold"
            textTransform="uppercase"
            letterSpacing="0.08em"
            color="text.secondary"
          >
            Current workspace
          </Text>
        </VStack>
      </HStack>
      <Text fontSize="md" fontWeight="semibold" color="text.primary" noOfLines={1}>
        {workspace.label}
      </Text>
      <Text fontSize="xs" color="text.secondary" noOfLines={1} mb={2}>
        {workspace.modality}
      </Text>
      <HStack spacing={3} fontSize="xxs" color="text.secondary">
        <Text as="span">
          <Text as="span" fontWeight="bold" color="text.primary">{workspace.caseCount}</Text> cases
        </Text>
        <Text as="span" color="border.default">·</Text>
        <Text as="span">
          <Text as="span" fontWeight="bold" color="status.success">{workspace.reviewedCount}</Text> reviewed
        </Text>
      </HStack>
    </Box>
  );
}

function EmptyWorkspaceHint(props: FlexProps) {
  return (
    <Box
      role="button"
      tabIndex={0}
      aria-label="No workspace selected. Open Datasets to choose one."
      borderRadius="lg"
      borderWidth="1px"
      borderStyle="dashed"
      borderColor="border.default"
      p={3}
      cursor="pointer"
      _hover={{ bg: 'surface.subtle', borderColor: 'border.strong' }}
      _focusVisible={{ boxShadow: 'focus', outline: 'none' }}
      {...props}
    >
      <HStack spacing={2} align="center" color="text.secondary">
        <Box
          as="span"
          display="grid"
          placeItems="center"
          w="26px"
          h="26px"
          borderRadius="md"
          bg="surface.subtle"
          flexShrink={0}
        >
          <Plus size={14} strokeWidth={2.25} aria-hidden="true" />
        </Box>
        <Text fontSize="sm" fontWeight="medium">
          No workspace selected
        </Text>
      </HStack>
      <Text fontSize="xs" color="text.secondary" mt={1}>
        Open Datasets to choose one.
      </Text>
    </Box>
  );
}

function CompactWorkspaceChip({ workspace }: { workspace: WorkspaceSummary }) {
  return (
    <Box
      role="img"
      aria-label={`Current workspace: ${workspace.label}`}
      display="grid"
      placeItems="center"
      w="36px"
      h="36px"
      borderRadius="md"
      bg="brand.50"
      color="brand.700"
      borderWidth="1px"
      borderColor="brand.100"
      title={workspace.label}
    >
      <Folder size={16} strokeWidth={2.25} aria-hidden="true" />
    </Box>
  );
}
