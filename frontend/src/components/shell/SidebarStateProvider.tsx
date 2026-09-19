import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useBreakpointValue } from '@chakra-ui/react';
import { useLocation } from 'react-router-dom';

/**
 * Sidebar state lives in a context so the header (which owns the collapse
 * control) and the sidebar body itself read the same source of truth.
 *
 * Two states are tracked:
 *
 * - `collapsed` — desktop/laptop mode only. Visible sidebar shrinks to
 *   icon-only with tooltips.
 * - `mobileOpen` — controls the mobile navigation drawer. Distinct from
 *   collapse so semantics stay clean in tests.
 */

export type ViewportTier = 'mobile' | 'tablet' | 'laptop' | 'desktop';

interface SidebarStateValue {
  /** True when the permanent sidebar should render in icon-only form. */
  collapsed: boolean;
  setCollapsed: (next: boolean) => void;
  toggleCollapsed: () => void;
  /** True when the mobile drawer should be open. */
  mobileOpen: boolean;
  openMobile: () => void;
  closeMobile: () => void;
  /**
   * True when the permanent sidebar should be mounted at all. False
   * on screens where the mobile drawer is the only chrome.
   */
  showPermanent: boolean;
  /**
   * The active viewport tier — exposed so tests can assert against the
   * current responsive decision.
   */
  tier: ViewportTier;
}

const SidebarStateContext = createContext<SidebarStateValue | null>(null);

interface ProviderProps {
  children: ReactNode;
  /**
   * `collapsed` initial state. When omitted, the hook picks a sensible
   * default per breakpoint (collapsed on tablet, expanded elsewhere).
   */
  initialCollapsed?: boolean;
  /**
   * Override the responsive decision tree entirely. Used by tests so they
   * can drive either the permanent sidebar (desktop) or the mobile drawer
   * without depending on a real `matchMedia` implementation in jsdom.
   * Production code should never pass this — the default `undefined`
   * delegates to Chakra's `useBreakpointValue`.
   */
  forceTier?: ViewportTier;
}

function tierFromBreakpoint(
  bp: 'mobile' | 'tablet' | 'laptop' | 'desktop' | undefined
): ViewportTier {
  return bp ?? 'mobile';
}

export function SidebarStateProvider({
  children,
  initialCollapsed,
  forceTier,
}: ProviderProps) {
  // Detect each tier independently so the test-mode `forceTier` prop can
  // replicate Chakra's behaviour exactly.
  const bpMobile = useBreakpointValue({ base: true, tablet: false, laptop: false, desktop: false });
  const bpTablet = useBreakpointValue({ base: false, tablet: true, laptop: false, desktop: false });
  const bpLaptop = useBreakpointValue({ base: false, tablet: false, laptop: true, desktop: false });
  const bpDesktop = useBreakpointValue({ base: false, tablet: false, laptop: false, desktop: true });

  const detectedTier: ViewportTier = bpMobile
    ? 'mobile'
    : bpTablet
    ? 'tablet'
    : bpLaptop
    ? 'laptop'
    : bpDesktop
    ? 'desktop'
    : 'mobile';

  const tier: ViewportTier = forceTier ?? detectedTier;

  const isMobile = tier === 'mobile';

  // Defaults when no `initialCollapsed` is provided: collapsed on tablet
  // (where space is at a premium), expanded elsewhere.
  const defaultCollapsed = tier === 'tablet';

  const [collapsed, setCollapsed] = useState<boolean>(
    initialCollapsed ?? defaultCollapsed
  );
  const [mobileOpen, setMobileOpen] = useState(false);

  // When `initialCollapsed` is omitted, follow the viewport tier.
  useEffect(() => {
    if (initialCollapsed !== undefined) return;
    setCollapsed(defaultCollapsed);
  }, [defaultCollapsed, initialCollapsed]);

  // Auto-close the mobile drawer on route change so a tapped link never
  // leaves the drawer hanging on top of the destination.
  const { pathname } = useLocation();
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), []);
  const openMobile = useCallback(() => setMobileOpen(true), []);
  const closeMobile = useCallback(() => setMobileOpen(false), []);

  const value = useMemo<SidebarStateValue>(
    () => ({
      collapsed,
      setCollapsed,
      toggleCollapsed,
      mobileOpen,
      openMobile,
      closeMobile,
      showPermanent: !isMobile,
      tier,
    }),
    [collapsed, toggleCollapsed, mobileOpen, openMobile, closeMobile, isMobile, tier]
  );

  return (
    <SidebarStateContext.Provider value={value}>{children}</SidebarStateContext.Provider>
  );
}

/** Internal helper for tests — exposed via context only. */
export const __test_helpers = { tierFromBreakpoint };

export function useSidebarState(): SidebarStateValue {
  const ctx = useContext(SidebarStateContext);
  if (!ctx) {
    throw new Error('useSidebarState must be used inside <SidebarStateProvider>');
  }
  return ctx;
}
