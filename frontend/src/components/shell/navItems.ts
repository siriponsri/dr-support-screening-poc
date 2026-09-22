/**
 * Canonical sidebar navigation for the Retinal Review Workbench shell.
 *
 * Five primary destinations plus Settings. Each entry maps a `to` path to an
 * icon, label, and optional one-liner used in the route header.
 *
 * Update both this file and `routeMeta.ts` when adding a route — the two are
 * intentionally separate so the sidebar and the page header can evolve
 * independently. Keep them in sync by path string only.
 */
import {
  Activity,
  Database,
  Eye,
  ListChecks,
  Settings2,
  type LucideIcon,
} from '@/lib/icons';

export interface NavItem {
  /** Route pathname (without hash — HashRouter uses `#/path`). */
  to: string;
  label: string;
  icon: LucideIcon;
}

export interface NavSection {
  /** Section title in the sidebar (not shown when collapsed). */
  heading: string;
  items: NavItem[];
}

export const PRIMARY_NAV: NavSection = {
  heading: 'Workspace',
  items: [
    { to: '/worklist', label: 'Worklist',       icon: ListChecks },
    { to: '/datasets', label: 'Datasets',       icon: Database },
    { to: '/review',   label: 'Review',         icon: Eye },
    { to: '/models',   label: 'Models & Audit', icon: Activity },
  ],
};

export const SECONDARY_NAV: NavSection = {
  heading: 'Configuration',
  items: [
    { to: '/settings', label: 'Settings', icon: Settings2 },
  ],
};

/** Flat list of every navigation entry the shell exposes. */
export const ALL_NAV_ITEMS: NavItem[] = [
  ...PRIMARY_NAV.items,
  ...SECONDARY_NAV.items,
];
