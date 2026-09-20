/**
 * Sidebar — the permanent left navigation surface.
 *
 * Three vertical sections:
 *  1. Brand mark + product name.
 *  2. Primary navigation + secondary (Settings) with a workspace card.
 *  3. Environment footer.
 *
 * Collapsed mode hides labels and the workspace card text; only a compact
 * workspace chip remains. Sidebar widths adapt to viewport tier.
 */
import {
  Box,
  Divider,
  Flex,
  HStack,
  Stack,
  Text,
  VStack,
  type BoxProps,
} from '@chakra-ui/react';
import { ShieldCheck, Stethoscope } from '@/lib/icons';
import { BrandMark } from '@/components/common/BrandMark';
import { SidebarNavList } from './SidebarNavList';
import { WorkspaceCard } from './WorkspaceCard';
import { PRIMARY_NAV, SECONDARY_NAV, type NavItem } from './navItems';
import { useSidebarState } from './SidebarStateProvider';

interface SidebarProps extends BoxProps {
  /**
   * When true the sidebar renders in icon-only mode regardless of viewport.
   * Normal usage is to control this through `useSidebarState`.
   */
  collapsed?: boolean;
  onItemNavigate?: () => void;
  /**
   * Optional explicit nav override. Defaults to PRIMARY_NAV/SECONDARY_NAV.
   * Kept exported for tests.
   */
  primaryNav?: NavItem[];
  secondaryNav?: NavItem[];
}

export function Sidebar({
  collapsed: collapsedProp,
  onItemNavigate,
  primaryNav = PRIMARY_NAV.items,
  secondaryNav = SECONDARY_NAV.items,
  ...rest
}: SidebarProps) {
  const { collapsed: collapsedState } = useSidebarState();
  const collapsed = collapsedProp ?? collapsedState;

  return (
    <Flex
      direction="column"
      h="100%"
      bg="surface.panel"
      borderRightWidth="1px"
      borderColor="border.subtle"
      {...rest}
    >
      <Box px={collapsed ? 2 : 5} py={collapsed ? 2 : 5}>
        {collapsed ? (
          <CollapsedBrandMark />
        ) : (
          <BrandMark />
        )}
      </Box>
      <Divider borderColor="border.subtle" />
      <Box flex={1} overflowY="auto" overflowX="hidden" px={collapsed ? 1 : 4} py={4}>
        <Stack spacing={5}>
          <Box>
            <SidebarNavList
              items={primaryNav}
              collapsed={collapsed}
              heading={!collapsed ? PRIMARY_NAV.heading : undefined}
              onNavigate={onItemNavigate}
            />
          </Box>
          <WorkspaceCard variant={collapsed ? 'compact' : 'full'} />
          {collapsed && (
            <Box pt={1}>
              <SidebarNavList
                items={secondaryNav}
                collapsed={collapsed}
                ariaLabel="Configuration"
                onNavigate={onItemNavigate}
              />
            </Box>
          )}
        </Stack>
      </Box>
      {!collapsed && (
        <>
          <Divider borderColor="border.subtle" />
          <Box px={4} pb={3}>
            <SidebarNavList
              items={secondaryNav}
              collapsed={collapsed}
              heading={SECONDARY_NAV.heading}
              ariaLabel="Configuration"
              onNavigate={onItemNavigate}
            />
          </Box>
          <Divider borderColor="border.subtle" />
          <HStack
            spacing={2}
            px={4}
            py={3}
            bg="surface.subtle"
            align="flex-start"
            fontSize="xs"
            color="text.secondary"
          >
            <ShieldCheck
              size={14}
              strokeWidth={2.25}
              aria-hidden="true"
              style={{ marginTop: 2 }}
            />
            <VStack align="flex-start" spacing={0} lineHeight="1.5">
              <Text fontWeight="bold" color="text.primary">
                Public &amp; synthetic only
              </Text>
              <Text>Research use · v0.4.0</Text>
            </VStack>
          </HStack>
        </>
      )}
      {collapsed && (
        <>
          <Divider borderColor="border.subtle" />
          <Box py={3} display="flex" justifyContent="center">
            <EnvironmentGlyph />
          </Box>
        </>
      )}
    </Flex>
  );
}

function CollapsedBrandMark() {
  return (
    <Box
      as="a"
      href="#/"
      aria-label="DR Support Screening home"
      display="grid"
      placeItems="center"
      w="36px"
      h="36px"
      bg="action.primary"
      color="text.inverse"
      borderRadius="md"
      mx="auto"
    >
      <Stethoscope size={18} strokeWidth={2.25} aria-hidden="true" />
    </Box>
  );
}

function EnvironmentGlyph() {
  return (
    <Box
      as="span"
      display="grid"
      placeItems="center"
      w="28px"
      h="28px"
      borderRadius="md"
      bg="surface.subtle"
      color="status.success"
      title="Public & synthetic only"
    >
      <ShieldCheck size={14} strokeWidth={2.25} aria-hidden="true" />
    </Box>
  );
}
