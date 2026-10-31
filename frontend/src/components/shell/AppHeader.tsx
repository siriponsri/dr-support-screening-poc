/**
 * AppHeader — the contextual top bar above the main content.
 *
 * Composition:
 *   Left  : collapse/menu toggle, page title (routed), subtitle.
 *   Right : runtime status pill, settings shortcut (where applicable).
 *
 * The header is page-aware — it reads the current pathname from the router
 * and resolves to a title/subtitle via `routeMeta.ts`. Pages may override
 * the page-level title via their own PageHeader component (this header
 * still owns the chrome controls).
 */
import {
  Box,
  Button,
  HStack,
  Spacer,
  Text,
  Tooltip,
  useBreakpointValue,
} from '@chakra-ui/react';
import { useLocation, NavLink } from 'react-router-dom';
import { LogOut, Settings2 as SettingsIcon } from '@/lib/icons';
import { useAuth } from './AuthGate';
import { SidebarCollapseControl } from './SidebarCollapseControl';
import { useRuntimeHealth } from '@/hooks/useRuntimeHealth';
import { useSidebarState } from './SidebarStateProvider';
import { useWorkspace } from './workspace';
import { getRouteMeta } from './routeMeta';

export function AppHeader() {
  const { showPermanent, collapsed, hidden } = useSidebarState();
  const location = useLocation();
  const meta = getRouteMeta(location.pathname);
  const isCompact = useBreakpointValue({ base: true, tablet: false, laptop: false });
  const runtime = useRuntimeHealth();

  return (
    <HStack
      as="header"
      h={{ base: '60px', tablet: '64px' }}
      px={{ base: 3, tablet: 4, laptop: 5 }}
      spacing={3}
      borderBottomWidth="1px"
      borderColor="border.subtle"
      bg="surface.panel"
      align="center"
    >
      <SidebarCollapseControl />
      <Box minW={0} flex={1}>
        <HStack spacing={2} align="baseline">
          <Text
            as="h1"
            fontSize={{ base: 'md', tablet: 'lg' }}
            fontWeight="semibold"
            color="text.primary"
            lineHeight="1.2"
            letterSpacing="-0.01em"
            noOfLines={1}
          >
            {meta.title}
          </Text>
        </HStack>
        {!isCompact && meta.subtitle && (
          <Text
            as="p"
            fontSize={{ base: 'xs', tablet: 'sm' }}
            color="text.secondary"
            lineHeight="1.4"
            noOfLines={1}
          >
            {meta.subtitle}
          </Text>
        )}
      </Box>
      <Spacer />
      <HStack spacing={2}>
        {showPermanent && hidden && <HiddenWorkspaceContext />}
        <RuntimePill runtime={runtime} />
        <SettingsShortcut hidden={!showPermanent || (showPermanent && collapsed)} />
        <SignedInUser compact={!!isCompact} />
      </HStack>
    </HStack>
  );
}

/** Pilot sign-in: who is signed in, a reminder about a short password, and sign out. */
function SignedInUser({ compact }: { compact: boolean }) {
  const { user, signOut } = useAuth();
  if (!user) return null;
  return (
    <HStack spacing={2} data-testid="signed-in-user">
      {user.short_password && !compact && (
        <Tooltip label="This password is short. Change it in Settings before other people use the app.">
          <Text fontSize="xs" color="status.warning" fontWeight="semibold">Change password</Text>
        </Tooltip>
      )}
      {!compact && <Text fontSize="sm" color="text.secondary">{user.username}{user.role === 'admin' ? ' (admin)' : ''}</Text>}
      <Button size="sm" variant="ghost" leftIcon={<LogOut size={15} />} onClick={() => void signOut()}>Sign out</Button>
    </HStack>
  );
}

/** Keeps workspace context visible while the sidebar (and its card) is hidden. */
function HiddenWorkspaceContext() {
  const { activeWorkspace, status } = useWorkspace();
  const degraded = status === 'error' || status === 'degraded';
  const label = activeWorkspace ? activeWorkspace.name : degraded ? 'Workspace unavailable' : 'No workspace open';
  return (
    <Box
      as={NavLink}
      to="/settings"
      maxW="220px"
      px={2}
      fontSize="xs"
      fontWeight="medium"
      color={activeWorkspace ? 'text.secondary' : 'status.warning'}
      title={activeWorkspace ? `Workspace: ${activeWorkspace.name}` : label}
      aria-label={activeWorkspace ? `Current workspace: ${activeWorkspace.name}` : label}
      _hover={{ color: 'text.primary' }}
    >
      <Text as="span" color="inherit" noOfLines={1}>{activeWorkspace ? `Workspace: ${label}` : label}</Text>
    </Box>
  );
}

function RuntimePill({ runtime }: { runtime: ReturnType<typeof useRuntimeHealth> }) {
  const visual = RUNTIME_VISUAL[runtime.tone];
  const tooltip = runtime.detail
    ? `${runtime.label} / ${runtime.detail}`
    : runtime.label;

  return (
    <Tooltip label={tooltip} placement="bottom" hasArrow openDelay={120}>
      <HStack
        spacing={2}
        px={2.5}
        h="28px"
        borderRadius="full"
        bg={visual.bg}
        borderWidth="1px"
        borderColor={visual.border}
        color={visual.fg}
        fontSize="xxs"
        fontWeight="bold"
        letterSpacing="0.04em"
        textTransform="uppercase"
        as="span"
      >
        <Box w="6px" h="6px" borderRadius="full" bg={visual.dot} />
        <Text as="span">{runtime.label}</Text>
      </HStack>
    </Tooltip>
  );
}

interface RuntimeVisual {
  bg: string;
  border: string;
  fg: string;
  dot: string;
}

const RUNTIME_VISUAL: Record<ReturnType<typeof useRuntimeHealth>['tone'], RuntimeVisual> = {
  idle:      { bg: 'surface.subtle', border: 'border.subtle',    fg: 'text.secondary', dot: 'text.muted' },
  checking:  { bg: 'surface.subtle', border: 'border.subtle',    fg: 'text.secondary', dot: 'text.muted' },
  online:    { bg: 'status.successSoft', border: 'status.successBorder', fg: 'status.success', dot: 'status.success' },
  research:  { bg: 'surface.subtle', border: 'border.subtle',    fg: 'text.secondary', dot: 'text.muted' },
  warnings:  { bg: 'status.warningSoft', border: 'status.warningBorder', fg: 'status.warning', dot: 'status.warning' },
  offline:   { bg: 'status.dangerSoft',  border: 'status.dangerBorder',  fg: 'status.danger',  dot: 'status.danger' },
};

function SettingsShortcut({ hidden }: { hidden: boolean }) {
  if (hidden) return null;
  return (
    <Tooltip label="Settings" placement="bottom" hasArrow openDelay={120}>
      <Box
        as={NavLink}
        to="/settings"
        aria-label="Settings"
        display="inline-flex"
        alignItems="center"
        justifyContent="center"
        w="36px"
        h="36px"
        borderRadius="md"
        color="text.secondary"
        _hover={{ bg: 'surface.subtle', color: 'text.primary' }}
        _focusVisible={{ outline: 'none', boxShadow: 'focus' }}
        data-testid="header-settings-shortcut"
      >
        <SettingsIcon size={16} strokeWidth={2.25} aria-hidden="true" />
      </Box>
    </Tooltip>
  );
}
