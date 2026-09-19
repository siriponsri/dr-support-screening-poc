/**
 * Helpers used by shell.test.tsx and any future frontend integration test.
 *
 *  - renderAppAt()  mounts ChakraProvider + MemoryRouter + the router-
 *                   agnostic <AppCore/> at the given pathname so tests can
 *                   inspect what a user would see on that route.
 *  - withProviders() wraps an explicit node with ChakraProvider +
 *                   MemoryRouter at a specific initial path.
 *
 * Tests default to a desktop viewport via `forceTier` so they don't rely
 * on jsdom's missing `matchMedia`. Individual tests can override to
 * 'mobile' / 'tablet' to verify responsive decisions.
 */
import { ChakraProvider } from '@chakra-ui/react';
import { render, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { theme } from '@/theme';
import { AppCore } from '@/App';
import type { ViewportTier } from '@/components/shell/SidebarStateProvider';
import type { ReactNode } from 'react';

export interface RenderOptions {
  /** Initial route. Defaults to `/worklist`. */
  pathname?: string;
  /**
   * Override the responsive tier the shell should treat itself as in.
   * Defaults to `'desktop'` so the permanent sidebar is mounted.
   */
  forceTier?: ViewportTier;
  initialEntries?: string[];
}

export function renderAppAt(
  pathname: string = '/worklist',
  options: RenderOptions = {}
): RenderResult {
  const { forceTier = 'desktop', initialEntries } = options;
  return render(
    <ChakraProvider theme={theme}>
      <MemoryRouter initialEntries={initialEntries ?? [pathname]}>
        <AppCore forceTier={forceTier} />
      </MemoryRouter>
    </ChakraProvider>
  );
}

export function withProviders(node: ReactNode, pathname: string, forceTier: ViewportTier = 'desktop') {
  return render(
    <ChakraProvider theme={theme}>
      <MemoryRouter initialEntries={[pathname]}>
        {node}
      </MemoryRouter>
    </ChakraProvider>
  );
}

// Expose AppCore under its proper type for users of the helper.
export { AppCore };
