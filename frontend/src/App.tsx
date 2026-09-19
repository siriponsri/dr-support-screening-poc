import { ChakraProvider, ColorModeScript } from '@chakra-ui/react';
import { HashRouter } from 'react-router-dom';
import { theme } from '@/theme';
import { AppRoutes } from '@/routes';
import type { ViewportTier } from '@/components/shell/SidebarStateProvider';

/**
 * Production app shell — wraps the router-agnostic AppCore in a HashRouter
 * and ChakraProvider so static-served bundles work without a server-side
 * rewrite rule (a single index.html is served for unknown routes).
 */
export function App() {
  return (
    <>
      <ColorModeScript initialColorMode={theme.config.initialColorMode} />
      <ChakraProvider theme={theme}>
        <HashRouter>
          <AppRoutes />
        </HashRouter>
      </ChakraProvider>
    </>
  );
}

interface AppCoreProps {
  /** Test-only viewport override forwarded to AppShell. */
  forceTier?: ViewportTier;
}

/**
 * Router-agnostic component tree. Used directly by tests so they can wrap
 * the tree in MemoryRouter without double-rendering react-router.
 */
export function AppCore({ forceTier }: AppCoreProps = {}) {
  return <AppRoutes forceTier={forceTier} />;
}
