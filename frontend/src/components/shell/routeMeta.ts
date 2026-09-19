/**
 * Route metadata — maps each pathname to the chrome the AppHeader should
 * show. Pages render their own in-content header (title + subtitle). The
 * shell header surfaces only the page title; this map is the single source
 * of truth used by the shell. Pages can override it via PageHeader.
 */
export interface RouteMeta {
  title: string;
  subtitle?: string;
  /** Optional small uppercase kicker shown above the in-content title. */
  kicker?: string;
}

export const ROUTE_META: Record<string, RouteMeta> = {
  '/worklist': {
    title: 'Worklist',
    subtitle: 'Public & synthetic cases for clinician review',
  },
  '/datasets': {
    title: 'Datasets',
    subtitle: 'Manage retinal imaging workspaces',
  },
  '/review': {
    title: 'Review',
    subtitle: 'Clinician review of admission sessions',
  },
  '/models': {
    title: 'Models & Audit',
    subtitle: 'Provider readiness, provenance, limitations',
  },
  '/settings': {
    title: 'Settings',
    subtitle: 'Workspace, runtime, and clinician preferences',
  },
  '/_foundation': {
    title: 'Design foundation',
    subtitle: 'Theme tokens, components, and responsive primitives',
  },
};

export const DEFAULT_META: RouteMeta = {
  title: 'DR Support Screening',
  subtitle: 'Clinician review workspace',
};

export function getRouteMeta(pathname: string): RouteMeta {
  if (pathname.startsWith('/review/')) return ROUTE_META['/review'];
  return ROUTE_META[pathname] ?? DEFAULT_META;
}
