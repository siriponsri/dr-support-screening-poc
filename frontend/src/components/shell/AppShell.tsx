/**
 * AppShell — the responsive application frame for the React chrome.
 *
 * The shell consists of three regions:
 *  - Sidebar (permanent on tablet+, hidden on mobile in favour of a Drawer).
 *  - Top bar (AppHeader) — page-aware title, runtime pill, collapse control.
 *  - Main outlet content (rendered by the router).
 *  - Footer (small disclaimer).
 *
 * Collapsed mode swaps the wide Sidebar for an icon-only Sidebar. The
 * SidebarStateProvider supplies the state used by both the collapse
 * affordance in the header and the Sidebar itself.
 */
import { Box, Grid, GridItem, useBreakpointValue } from '@chakra-ui/react';
import { Outlet } from 'react-router-dom';
import { SidebarStateProvider, useSidebarState, type ViewportTier } from './SidebarStateProvider';
import { Sidebar } from './Sidebar';
import { SidebarDrawer } from './SidebarDrawer';
import { AppHeader } from './AppHeader';

const SHELL_MIN_H = '100vh';

interface AppShellProps {
  /**
   * Test-only override that pins the responsive tier so tests don't depend
   * on `matchMedia` in jsdom. Production code omits this.
   */
  forceTier?: ViewportTier;
}

export function AppShell({ forceTier }: AppShellProps = {}) {
  // Sidebar state needs to be a single provider so the header's collapse
  // toggle and the sidebar body remain in sync.
  return (
    <SidebarStateProvider forceTier={forceTier}>
      <ShellLayout />
    </SidebarStateProvider>
  );
}

function ShellLayout() {
  const { showPermanent, collapsed } = useSidebarState();

  // Sidebar widths by tier — keep these narrow enough to leave room for
  // clinical tables on the main viewport.
  const widthMobileDrawer = '74vw';
  const widthTablet = collapsed ? '64px' : '210px';
  const widthLaptop = collapsed ? '64px' : '236px';
  const widthDesktop = collapsed ? '68px' : '256px';

  const sidebarWidth = useBreakpointValue({
    base: widthMobileDrawer,
    tablet: widthTablet,
    laptop: widthLaptop,
    desktop: widthDesktop,
  });

  return (
    <Box minH={SHELL_MIN_H} bg="surface.canvas">
      <Grid
        templateColumns={{
          base: '1fr',
          tablet: `${sidebarWidth ?? '232px'} minmax(0, 1fr)`,
        }}
        templateRows="auto 1fr auto"
        templateAreas={
          showPermanent
            ? {
                tablet: '"sidebar topbar" "sidebar main" "sidebar footer"',
              }
            : { base: '"topbar" "main" "footer"' }
        }
        minH={SHELL_MIN_H}
      >
        {showPermanent ? (
          <GridItem
            area="sidebar"
            borderRightWidth="1px"
            borderColor="border.subtle"
            position="sticky"
            top={0}
            h="100vh"
            minH={SHELL_MIN_H}
            overflow="hidden"
          >
            <Sidebar collapsed={collapsed} />
          </GridItem>
        ) : (
          <SidebarDrawer />
        )}
        <GridItem area="topbar" position="sticky" top={0} zIndex={2}>
          <AppHeader />
        </GridItem>
        <GridItem area="main" minW={0}>
          <Outlet />
        </GridItem>
        <GridItem
          area="footer"
          borderTopWidth="1px"
          borderColor="border.subtle"
          bg="surface.panel"
          py={3}
          px={{ base: 4, tablet: 5, laptop: 7 }}
        >
          <Box
            as="footer"
            fontSize="xs"
            color="text.secondary"
            textAlign="center"
          >
            Suggestions support review. They do not establish a diagnosis or
            autonomous referral.
          </Box>
        </GridItem>
      </Grid>
    </Box>
  );
}
