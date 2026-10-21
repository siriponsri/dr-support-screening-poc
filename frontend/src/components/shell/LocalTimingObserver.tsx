import { useEffect, useLayoutEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { localTiming } from '@/lib/localTiming';
import { useWorkspace } from './workspace';

export function LocalTimingObserver() {
  const { pathname } = useLocation();
  const { activeWorkspace } = useWorkspace();
  const scope = useRef(activeWorkspace?.id);
  useLayoutEffect(() => {
    if (scope.current !== activeWorkspace?.id) localTiming.leave();
    scope.current = activeWorkspace?.id;
    const match = /^\/(review|clinician-review|edit)\/([^/]+)$/.exec(pathname);
    let key: string | null = null;
    try { key = match ? decodeURIComponent(match[2]) : null; } catch { /* Invalid routes record no identifiers. */ }
    localTiming.enter(key, match?.[1] === 'edit');
  }, [pathname, activeWorkspace?.id]);
  useEffect(() => {
    const activity = () => localTiming.interact();
    const visibility = () => localTiming.visibility(document.visibilityState === 'visible' && document.hasFocus());
    for (const name of ['pointerdown', 'keydown', 'wheel']) window.addEventListener(name, activity, { passive: true });
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('focus', visibility); window.addEventListener('blur', visibility);
    visibility();
    return () => {
      for (const name of ['pointerdown', 'keydown', 'wheel']) window.removeEventListener(name, activity);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('focus', visibility); window.removeEventListener('blur', visibility);
      localTiming.leave();
    };
  }, []);
  return null;
}
