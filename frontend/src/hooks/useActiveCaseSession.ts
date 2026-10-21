import { useCallback, useLayoutEffect, useRef } from 'react';

/** A retired image session must not navigate or start follow-up mutations. */
export function useActiveCaseSession() {
  const active = useRef(true);
  useLayoutEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
  return useCallback(() => active.current, []);
}
