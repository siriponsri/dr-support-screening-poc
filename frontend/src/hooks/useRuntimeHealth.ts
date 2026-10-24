import { useEffect, useState } from 'react';

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

export type RuntimeTone = 'idle' | 'checking' | 'online' | 'research' | 'warnings' | 'offline';

/**
 * The standing research-use notice `/health` always returns. It is context, not
 * a fault, so it is shown as a quiet label rather than a warning.
 */
export const RESEARCH_NOTICE = 'Research-only; model readiness is reported separately';

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

  useEffect(() => {
    let active = true;
    const controllers = new Set<AbortController>();
    if (!enabled) {
      setState(idle);
      return;
    }

    let timer: ReturnType<typeof setTimeout> | null = null;

    const probe = async () => {
      const ctrl = new AbortController();
      controllers.add(ctrl);
      const timeoutId = setTimeout(() => ctrl.abort(), 6_000);
      try {
        const res = await fetch('/health', { signal: ctrl.signal });
        if (!res.ok) {
          if (active) {
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
        if (!body || !['PASS', 'PASS_WITH_WARNINGS'].includes(body.status ?? '')) {
          throw new Error('Review service readiness could not be verified.');
        }
        const warnings = Array.isArray(body.warnings) ? body.warnings : [];
        const realWarnings = warnings.filter((warning) => warning !== RESEARCH_NOTICE);
        const researchOnly = body.status === 'PASS_WITH_WARNINGS' && warnings.length > 0 && realWarnings.length === 0;
        const hasWarnings = !researchOnly && (body.status === 'PASS_WITH_WARNINGS' || realWarnings.length > 0);
        if (active) {
          setState({
            tone: researchOnly ? 'research' : hasWarnings ? 'warnings' : 'online',
            label: researchOnly ? 'Research use' : hasWarnings ? 'Warnings' : 'Ready',
            detail: researchOnly ? RESEARCH_NOTICE : realWarnings[0] ?? body.status ?? body.lane,
            raw: body,
          });
        }
      } catch (err) {
        if (active) {
          setState({
            tone: 'offline',
            label: 'Offline',
            detail: err instanceof Error ? err.message : 'Health probe failed',
          });
        }
      } finally {
        clearTimeout(timeoutId);
        controllers.delete(ctrl);
      }
    };

    // First call after a short grace period so the initial paint is calm.
    timer = setTimeout(() => {
      if (!active) return;
      void probe();
    }, 250);

    const interval = setInterval(() => {
      if (active) void probe();
    }, POLL_INTERVAL_MS);

    return () => {
      active = false;
      controllers.forEach((controller) => controller.abort());
      if (timer) clearTimeout(timer);
      clearInterval(interval);
    };
  }, [enabled]);

  return state;
}
