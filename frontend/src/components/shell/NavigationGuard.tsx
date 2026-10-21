import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { UNSAFE_NavigationContext, UNSAFE_LocationContext } from 'react-router-dom';

type Reason = 'route' | 'case' | 'workspace';
type Guard = (reason: Reason) => Promise<boolean>;
interface GuardState {
  register: (guard: Guard) => () => void;
  hasGuard: () => boolean;
  request: (reason?: Reason) => Promise<boolean>;
  approved: (transition: () => void) => void;
}
const fallback: GuardState = {
  register: () => () => {}, hasGuard: () => false,
  request: async () => true, approved: (transition) => transition(),
};
const Context = createContext<GuardState>(fallback);

/**
 * One shared gate for SPA pushes/replaces, case controls and workspace changes.
 * This wraps the existing pinned HashRouter navigator; it never confirms labels.
 * Native POP retains the current route until the guard resolves; cancellation
 * restores the prior history entry without unmounting the clinical draft.
 */
export function NavigationGuardProvider({ children }: { children: ReactNode }) {
  const navigation = useContext(UNSAFE_NavigationContext);
  const incoming = useContext(UNSAFE_LocationContext);
  const [displayed, setDisplayed] = useState(incoming);
  const displayedRef = useRef(incoming);
  const allowLocation = useRef(false);
  const historyIndex = useCallback((): number | null => {
    const memoryIndex = (navigation.navigator as { index?: number }).index;
    const browserIndex = window.history.state?.idx;
    return typeof memoryIndex === 'number' ? memoryIndex : Number.isInteger(browserIndex) ? browserIndex : null;
  }, [navigation.navigator]);
  const displayedIndex = useRef(historyIndex());
  const guard = useRef<Guard | null>(null);
  const pending = useRef(false);
  const bypass = useRef(0);
  const register = useCallback((next: Guard) => {
    guard.current = next;
    return () => { if (guard.current === next) guard.current = null; };
  }, []);
  const hasGuard = useCallback(() => guard.current !== null, []);
  const request = useCallback(async (reason: Reason = 'route') => {
    if (pending.current) return false;
    const current = guard.current;
    if (!current) return true;
    pending.current = true;
    try { return await current(reason) && guard.current === current; }
    catch { return false; }
    finally { pending.current = false; }
  }, []);
  const approved = useCallback((transition: () => void) => {
    bypass.current += 1;
    try { transition(); } finally { bypass.current -= 1; }
  }, []);
  useLayoutEffect(() => {
    const previous = displayedRef.current;
    const left = incoming.location;
    const right = previous.location;
    const same = left.key === right.key && left.pathname === right.pathname && left.search === right.search && left.hash === right.hash;
    const accept = () => {
      displayedRef.current = incoming;
      displayedIndex.current = historyIndex();
      allowLocation.current = false;
      setDisplayed(incoming);
    };
    if (same) { allowLocation.current = false; return; }
    if (allowLocation.current || !guard.current) { accept(); return; }
    let active = true;
    void request('route').then((allowed) => {
      if (!active) return;
      if (allowed) { accept(); return; }
      const currentIndex = historyIndex();
      allowLocation.current = true;
      if (displayedIndex.current !== null && currentIndex !== null && displayedIndex.current !== currentIndex) {
        navigation.navigator.go(displayedIndex.current - currentIndex);
      } else {
        navigation.navigator.replace(previous.location, previous.location.state);
      }
    });
    return () => { active = false; };
  }, [incoming, historyIndex, navigation.navigator, request]);
  const state = useMemo(() => ({ register, hasGuard, request, approved }), [register, hasGuard, request, approved]);
  const navigator = useMemo(() => {
    const original = navigation.navigator;
    const attempt = (transition: () => void) => {
      const perform = () => { allowLocation.current = true; transition(); };
      if (bypass.current || !guard.current) { perform(); return; }
      void request().then((allowed) => { if (allowed) approved(perform); });
    };
    return {
      ...original,
      push: (...args: Parameters<typeof original.push>) => attempt(() => original.push(...args)),
      replace: (...args: Parameters<typeof original.replace>) => attempt(() => original.replace(...args)),
      go: (...args: Parameters<typeof original.go>) => attempt(() => original.go(...args)),
    };
  }, [navigation.navigator, request, approved]);
  return <Context.Provider value={state}><UNSAFE_NavigationContext.Provider value={{ ...navigation, navigator }}><UNSAFE_LocationContext.Provider value={displayed}>{children}</UNSAFE_LocationContext.Provider></UNSAFE_NavigationContext.Provider></Context.Provider>;
}

export function useNavigationGuard() { return useContext(Context); }

export function usePageNavigationGuard(handler: Guard) {
  const context = useNavigationGuard();
  const latest = useRef(handler);
  latest.current = handler;
  useLayoutEffect(() => context.register((reason) => latest.current(reason)), [context.register]);
  return context;
}
