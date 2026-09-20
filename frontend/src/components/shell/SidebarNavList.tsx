/**
 * Sidebar nav list — renders one row per NavItem with a clear active state
 * and (importantly) works in both expanded and collapsed modes.
 *
 * In expanded mode the row shows an icon, label, and optional right-aligned
 * meta. The row gets a 3px Medicine Green left bar and a soft green
 * background when active. In collapsed mode only the icon is visible inside
 * a uniform tile; tooltips surface the label.
 */
import { Box, HStack, StackProps, Text, Tooltip, VStack } from '@chakra-ui/react';
import { NavLink, useLocation } from 'react-router-dom';
import type { NavItem } from './navItems';

interface SidebarNavListProps extends Omit<StackProps, 'children'> {
  items: NavItem[];
  collapsed: boolean;
  /**
   * Show the section heading (only when expanded). The heading is also
   * used as the section's accessible landmark so screen readers can
   * distinguish primary from secondary navigation.
   */
  heading?: string;
  /**
   * Landmark label exposed via `aria-label`. Defaults to "Primary".
   * Use a section-specific label ("Configuration", "Mobile") for
   * additional landmarks inside the sidebar.
   */
  ariaLabel?: string;
  onNavigate?: () => void;
}

export function SidebarNavList({
  items,
  collapsed,
  heading,
  ariaLabel = 'Primary',
  onNavigate,
  ...rest
}: SidebarNavListProps) {
  return (
    <VStack as="nav" aria-label={ariaLabel} align="stretch" spacing={collapsed ? 1.5 : 0.5} {...rest}>
      {!collapsed && heading && (
        <Text
          as="div"
          fontSize="xxs"
          fontWeight="bold"
          letterSpacing="0.08em"
          textTransform="uppercase"
          color="text.secondary"
          mb={2}
          px={3}
        >
          {heading}
        </Text>
      )}
      {items.map((item) => (
        <SidebarNavRow key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
      ))}
    </VStack>
  );
}

function SidebarNavRow({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const { icon: Icon, label, to } = item;
  const location = useLocation();
  const pathOnly = location.pathname;
  const active = pathOnly === to || (to === '/' && pathOnly === '/');

  const row = (
    <HStack
      spacing={collapsed ? 0 : 3}
      justify={collapsed ? 'center' : 'flex-start'}
      align="center"
      h={collapsed ? '36px' : undefined}
      w={collapsed ? '36px' : 'auto'}
      mx={collapsed ? 'auto' : 0}
      px={collapsed ? 0 : 3}
      py={collapsed ? 0 : '8px'}
      borderRadius="md"
      borderLeftWidth={collapsed ? '0' : '3px'}
      borderLeftColor={active ? 'action.primary' : 'transparent'}
      bg={active ? 'action.primarySoft' : 'transparent'}
      color={active ? 'action.primaryHover' : 'text.secondary'}
      fontSize="md"
      fontWeight={active ? 'bold' : 'medium'}
      textDecoration="none"
      transition="background 120ms ease, color 120ms ease, transform 120ms ease"
      _hover={{
        bg: active ? 'action.primarySoft' : 'surface.subtle',
        transform: collapsed ? undefined : 'translateX(1px)',
      }}
      _focusVisible={{ outline: 'none', boxShadow: 'focus' }}
    >
      <Icon
        size={16}
        strokeWidth={active ? 2.25 : 2}
        aria-hidden="true"
      />
      {!collapsed && (
        <Text as="span" flex={1} lineHeight="1.2" noOfLines={1}>
          {label}
        </Text>
      )}
    </HStack>
  );

  // Tooltip-wrapped rows render the tooltip on the icon (collapsed mode);
  // in expanded mode the row itself is the link target, so we wrap the
  // whole HStack in a NavLink for proper semantics and click handling.
  const link = (
    <NavLink
      to={to}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      aria-label={collapsed ? label : undefined}
      style={{ display: 'block', textDecoration: 'none' }}
    >
      {row}
    </NavLink>
  );

  if (collapsed) {
    return (
      <Tooltip label={label} placement="right" hasArrow openDelay={120} gutter={6}>
        <Box as="div" display="flex" justifyContent="center">
          {link}
        </Box>
      </Tooltip>
    );
  }

  return link;
}
