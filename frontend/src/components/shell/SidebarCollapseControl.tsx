/**
 * Sidebar collapse control — single icon button that toggles the sidebar
 * between expanded and collapsed (icon-only) states.
 *
 * In mobile mode the same affordance opens the navigation drawer instead
 * of toggling collapse so the chrome stays predictable across breakpoints.
 */
import { IconButton, type IconButtonProps, Tooltip } from '@chakra-ui/react';
import { Menu, PanelLeftClose, PanelLeftOpen } from '@/lib/icons';
import { useSidebarState } from './SidebarStateProvider';

type Variant = IconButtonProps;

export function SidebarCollapseControl(props: Partial<Variant>) {
  const { collapsed, toggleCollapsed, openMobile, showPermanent, tier } = useSidebarState();
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

  return (
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
  );
}
