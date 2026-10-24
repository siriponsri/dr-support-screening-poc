/**
 * Sidebar controls — one icon button toggles expanded and collapsed
 * (icon-only); a second hides the sidebar. When hidden, a single button
 * shows it again.
 *
 * In mobile mode the same affordance opens the navigation drawer instead
 * of toggling collapse so the chrome stays predictable across breakpoints.
 */
import { HStack, IconButton, type IconButtonProps, Tooltip } from '@chakra-ui/react';
import { Menu, PanelLeftClose, PanelLeftDashed, PanelLeftOpen } from '@/lib/icons';
import { useSidebarState } from './SidebarStateProvider';

type Variant = IconButtonProps;

export function SidebarCollapseControl(props: Partial<Variant>) {
  const { collapsed, hidden, setMode, toggleCollapsed, openMobile, showPermanent, tier } = useSidebarState();
  // Use the provider's tier (which honours `forceTier` for tests) instead
  // of evaluating `useBreakpointValue` a second time. The provider already
  // makes this decision once for the whole shell.
  const isMobile = tier === 'mobile';
  const desktopTooltip = collapsed ? 'Expand sidebar' : 'Collapse sidebar';

  if (isMobile) {
    return (
      <Tooltip label="Open navigation" placement="bottom" hasArrow openDelay={120}>
        <IconButton
          aria-label="Open navigation"
          icon={<Menu size={18} strokeWidth={2.25} />}
          variant="ghost"
          size="md"
          onClick={openMobile}
          {...props}
        />
      </Tooltip>
    );
  }

  if (hidden) {
    return (
      <Tooltip label="Show sidebar" placement="bottom" hasArrow openDelay={120}>
        <IconButton
          aria-label="Show sidebar"
          icon={<PanelLeftOpen size={18} strokeWidth={2.25} />}
          variant="ghost"
          size="md"
          onClick={() => setMode('expanded')}
          {...props}
        />
      </Tooltip>
    );
  }

  return (
    <HStack spacing={0.5}>
      <Tooltip label={desktopTooltip} placement="bottom" hasArrow openDelay={120}>
        <IconButton
          aria-label={desktopTooltip}
          icon={
            collapsed ? (
              <PanelLeftOpen size={18} strokeWidth={2.25} />
            ) : (
              <PanelLeftClose size={18} strokeWidth={2.25} />
            )
          }
          variant="ghost"
          size="md"
          onClick={toggleCollapsed}
          aria-hidden={!showPermanent ? true : undefined}
          tabIndex={!showPermanent ? -1 : 0}
          {...props}
        />
      </Tooltip>
      <Tooltip label="Hide sidebar" placement="bottom" hasArrow openDelay={120}>
        <IconButton
          aria-label="Hide sidebar"
          icon={<PanelLeftDashed size={18} strokeWidth={2.25} />}
          variant="ghost"
          size="md"
          onClick={() => setMode('hidden')}
          {...props}
        />
      </Tooltip>
    </HStack>
  );
}
