import { useEffect, useRef, useState } from 'react';

/**
 * Runtime health is reserved for backend-derived state. The hook never
 * assumes success — it starts in `idle`, transitions through `checking`,
 * and only reports `online` (with `warnings` or not) after `/health` returns
 * a successful response.
 *
 * If the fetch fails, CORS-blocked, or the body is unparseable, the hook
 * reports `offline` so the chrome never claims a remote provider is healthy
 * without evidence.
 */

export type RuntimeTone = 'idle' | 'checking' | 'online' | 'warnings' | 'offline';

export interface RuntimeHealth {
  tone: RuntimeTone;
  /** Short label shown in the header pill (≤ 16 chars). */
  label: string;
  /** Optional tooltip detail; omitted when nothing meaningful to add. */
  detail?: string;
  /** Raw `/health` payload if the round-trip succeeded. */
  raw?: unknown;
}

const idle: RuntimeHealth = { tone: 'idle', label: 'Connecting' };
const checking: RuntimeHealth = { tone: 'checking', label: 'Checking' };

const POLL_INTERVAL_MS = 30_000;

export function useRuntimeHealth(enabled = true): RuntimeHealth {
  const [state, setState] = useState<RuntimeHealth>(enabled ? checking : idle);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    if (!enabled) {
      setState(idle);
      return;
    }

    let timer: ReturnType<typeof setTimeout> | null = null;

    const probe = async () => {
      try {
        const ctrl = new AbortController();
        const timeoutId = setTimeout(() => ctrl.abort(), 6_000);
        const res = await fetch('/health', { signal: ctrl.signal });
        clearTimeout(timeoutId);
        if (!res.ok) {
          if (mounted.current) {
            setState({
              tone: 'offline',
              label: 'Disconnected',
              detail: `Health endpoint returned HTTP ${res.status}`,
            });
          }
          return;
        }
        const body = (await res.json()) as {
          status?: string;
          lane?: string;
          warnings?: string[];
        };
        const hasWarnings = Array.isArray(body.warnings) && body.warnings.length > 0;
        if (mounted.current) {
          setState({
            tone: hasWarnings ? 'warnings' : 'online',
            label: hasWarnings ? 'Warnings' : 'Ready',
            detail: body.status ?? body.lane,
            raw: body,
          });
        }
      } catch (err) {
        if (mounted.current) {
          setState({
            tone: 'offline',
            label: 'Offline',
            detail: err instanceof Error ? err.message : 'Health probe failed',
          });
        }
      }
    };

    // First call after a short grace period so the initial paint is calm.
    timer = setTimeout(() => {
      if (!mounted.current) return;
      void probe();
    }, 250);

    const interval = setInterval(() => {
      if (mounted.current) void probe();
    }, POLL_INTERVAL_MS);

    return () => {
      mounted.current = false;
      if (timer) clearTimeout(timer);
      clearInterval(interval);
    };
  }, [enabled]);

  return state;
}
