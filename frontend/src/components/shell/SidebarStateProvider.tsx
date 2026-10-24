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
 * The permanent sidebar has three modes: expanded, collapsed (icon-only with
 * tooltips) and hidden. Image pages (Review, Clinician Review, Annotation
 * Editor) keep their own mode, collapsed by default, so the retinal image gets
 * the width; other pages keep the tier default. Both choices are remembered on
 * this workstation as a UI-only preference.
 *
 * `mobileOpen` controls the mobile navigation drawer, distinct from the
 * permanent modes so semantics stay clean in tests.
 */

export type SidebarMode = 'expanded' | 'collapsed' | 'hidden';

const MODE_KEYS = {
  image: 'dr-support-screening.sidebar-mode.image.v1',
  other: 'dr-support-screening.sidebar-mode.other.v1',
} as const;

const IMAGE_ROUTE = /^\/(review|clinician-review|edit)(\/|$)/;

function readMode(key: string): SidebarMode | null {
  try {
    const value = window.localStorage.getItem(key);
    return value === 'expanded' || value === 'collapsed' || value === 'hidden' ? value : null;
  } catch {
    return null;
  }
}

function writeMode(key: string, mode: SidebarMode): void {
  try {
    window.localStorage.setItem(key, mode);
  } catch {
    // A restricted storage policy only loses the remembered layout.
  }
}

export type ViewportTier = 'mobile' | 'tablet' | 'laptop' | 'desktop';

interface SidebarStateValue {
  /** Current permanent-sidebar mode for this route group. */
  mode: SidebarMode;
  setMode: (next: SidebarMode) => void;
  /** True when the permanent sidebar should render in icon-only form. */
  collapsed: boolean;
  setCollapsed: (next: boolean) => void;
  toggleCollapsed: () => void;
  /** True when the permanent sidebar is hidden entirely. */
  hidden: boolean;
  /** True on image pages, where the sidebar starts collapsed. */
  imageRoute: boolean;
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

  const tierMode: SidebarMode = (initialCollapsed ?? defaultCollapsed) ? 'collapsed' : 'expanded';
  const { pathname } = useLocation();
  const imageRoute = IMAGE_ROUTE.test(pathname);
  const group = imageRoute ? 'image' : 'other';
  const [chosen, setChosen] = useState<Record<'image' | 'other', SidebarMode | null>>(() => ({
    image: readMode(MODE_KEYS.image),
    other: readMode(MODE_KEYS.other),
  }));
  const [mobileOpen, setMobileOpen] = useState(false);

  // Image pages start collapsed; other pages follow the viewport tier.
  const mode: SidebarMode = chosen[group] ?? (imageRoute ? 'collapsed' : tierMode);
  const setMode = useCallback((next: SidebarMode) => {
    setChosen((current) => ({ ...current, [group]: next }));
    writeMode(MODE_KEYS[group], next);
  }, [group]);
  const collapsed = mode === 'collapsed';
  const hidden = mode === 'hidden';
  const setCollapsed = useCallback((next: boolean) => setMode(next ? 'collapsed' : 'expanded'), [setMode]);

  // Auto-close the mobile drawer on route change so a tapped link never
  // leaves the drawer hanging on top of the destination.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const toggleCollapsed = useCallback(() => setMode(collapsed ? 'expanded' : 'collapsed'), [collapsed, setMode]);
  const openMobile = useCallback(() => setMobileOpen(true), []);
  const closeMobile = useCallback(() => setMobileOpen(false), []);

  const value = useMemo<SidebarStateValue>(
    () => ({
      mode,
      setMode,
      collapsed,
      setCollapsed,
      toggleCollapsed,
      hidden,
      imageRoute,
      mobileOpen,
      openMobile,
      closeMobile,
      showPermanent: !isMobile,
      tier,
    }),
    [mode, setMode, collapsed, setCollapsed, toggleCollapsed, hidden, imageRoute, mobileOpen, openMobile, closeMobile, isMobile, tier]
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
