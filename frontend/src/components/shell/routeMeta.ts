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
    // The data scope is stated once, in the sidebar footer, from /health.
    subtitle: 'Retinal images for clinician review',
  },
  '/datasets': {
    title: 'Datasets',
    subtitle: 'Manage retinal imaging workspaces',
  },
  '/review': {
    title: 'Review',
    subtitle: 'Check the image and the AI result, then confirm',
  },
  '/edit': {
    title: 'Annotation Editor',
    subtitle: 'Create explicit human annotations in original image space',
  },
  '/gold': {
    title: 'Gold-100',
    subtitle: 'Research labels by the ophthalmologist',
  },
  '/report': {
    title: 'Screening Report',
    subtitle: 'The grader chooses Refer or Not refer; a physician signs',
  },
  '/clinician-review': {
    title: 'Clinician Review',
    subtitle: 'Human sign-off and review record',
  },
  '/models': {
    title: 'Models & Audit',
    subtitle: 'Provider readiness, provenance, limitations',
  },
  '/settings': {
    title: 'Settings',
    subtitle: 'Workspace, runtime, and clinician preferences',
  },
  '/today': {
    title: 'Today',
    subtitle: 'Your review work at a glance',
  },
  '/admin': {
    title: 'Admin',
    subtitle: 'Accounts and stored data',
  },
};

export const DEFAULT_META: RouteMeta = {
  title: 'Retinal Review Workbench',
  subtitle: 'Clinician review workspace',
};

export function getRouteMeta(pathname: string): RouteMeta {
  if (pathname.startsWith('/review/')) return ROUTE_META['/review'];
  if (pathname.startsWith('/edit/')) return ROUTE_META['/edit'];
  if (pathname.startsWith('/clinician-review/')) return ROUTE_META['/clinician-review'];
  if (pathname.startsWith('/report/')) return ROUTE_META['/report'];
  if (pathname.startsWith('/gold/')) return ROUTE_META['/gold'];
  return ROUTE_META[pathname] ?? DEFAULT_META;
}
