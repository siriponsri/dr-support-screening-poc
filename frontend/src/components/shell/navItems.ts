/**
 * Canonical sidebar navigation for the Retinal Review Workbench shell.
 *
 * Clinical review (Worklist, Review) first; Datasets, Models & Audit and
 * Settings grouped under Administration. Each entry maps a `to` path to an
 * icon and label.
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
  Users,
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

/** Routine clinician work: the doctor view. */
export const PRIMARY_NAV: NavSection = {
  heading: 'Clinical review',
  items: [
    { to: '/worklist', label: 'Worklist', icon: ListChecks },
    { to: '/review',   label: 'Review',   icon: Eye },
  ],
};

/** Administration is kept apart from routine review (not an access control). */
export const SECONDARY_NAV: NavSection = {
  heading: 'Administration',
  items: [
    { to: '/datasets', label: 'Datasets',       icon: Database },
    { to: '/models',   label: 'Models & Audit', icon: Activity },
    { to: '/settings', label: 'Settings',       icon: Settings2 },
  ],
};

/** Shown under Administration only to a signed-in administrator. */
export const ADMIN_NAV_ITEM: NavItem = { to: '/admin', label: 'Admin', icon: Users };

/** Flat list of every navigation entry the shell exposes. */
export const ALL_NAV_ITEMS: NavItem[] = [
  ...PRIMARY_NAV.items,
  ...SECONDARY_NAV.items,
];
