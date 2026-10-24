/**
 * Shell behaviour tests — Round 2 deliverable.
 *
 * Covers the explicit test items requested in the brief:
 *   - sidebar renders all navigation items
 *   - active route state
 *   - collapsed state
 *   - mobile drawer open/close
 *   - route navigation
 *   - header title changes with route
 *
 * Tests run against the full <AppCore/> wrapped in MemoryRouter. To stay
 * deterministic in jsdom (no real `matchMedia`), each renderAppAt call
 * pins the responsive tier via `forceTier`. Tests that need different
 * responsive behaviour pass an explicit `forceTier`.
 *
 * Global setup (in tests/setup.ts) installs a permissive matchMedia stub
 * and a network failure mock so the shell renders without throwing.
 */
import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderAppAt } from './testUtils';
import { theme } from '@/theme';
import { RESEARCH_NOTICE } from '@/hooks/useRuntimeHealth';

describe('Sidebar navigation', () => {
  it('keeps routine clinical review apart from administration', () => {
    renderAppAt('/worklist');
    const primary = within(screen.getByRole('navigation', { name: 'Primary' }));
    expect(primary.getByRole('link', { name: /Worklist/i })).toBeInTheDocument();
    expect(primary.getByRole('link', { name: /^Review$/i })).toBeInTheDocument();
    expect(primary.queryByRole('link', { name: /Datasets/i })).not.toBeInTheDocument();
    expect(primary.queryByRole('link', { name: /Models.*Audit/i })).not.toBeInTheDocument();

    const admin = within(screen.getByRole('navigation', { name: /Administration/i }));
    expect(admin.getByRole('link', { name: /Datasets/i })).toBeInTheDocument();
    expect(admin.getByRole('link', { name: /Models.*Audit/i })).toBeInTheDocument();
    expect(admin.getByRole('link', { name: /Settings/i })).toBeInTheDocument();
  });

  it('marks only the active route with aria-current=page', () => {
    renderAppAt('/datasets');
    const admin = within(screen.getByRole('navigation', { name: /Administration/i }));
    expect(admin.getByRole('link', { name: /Datasets/i })).toHaveAttribute('aria-current', 'page');
    expect(admin.getByRole('link', { name: /Settings/i })).not.toHaveAttribute('aria-current');
    const primary = within(screen.getByRole('navigation', { name: 'Primary' }));
    expect(primary.getByRole('link', { name: /Worklist/i })).not.toHaveAttribute('aria-current');
  });

  it('shows the institutional band without naming the university or faculty', () => {
    renderAppAt('/worklist');
    expect(screen.getAllByTestId('institutional-band').length).toBeGreaterThan(0);
    expect(screen.queryByText(/Khon Kaen|Faculty of Medicine/i)).not.toBeInTheDocument();
  });

  it('exposes a brand mark and an explicit workspace recovery state', async () => {
    renderAppAt('/worklist');
    expect(screen.getAllByLabelText(/Retinal Review Workbench home/i)[0]).toBeInTheDocument();
    expect(await screen.findByText(/Workspace unavailable|No workspace open/i)).toBeInTheDocument();
  });

  it('renders the navigation as a left drawer on mobile rather than a permanent sidebar', () => {
    renderAppAt('/worklist', { forceTier: 'mobile' });
    expect(screen.getByRole('button', { name: /Open navigation/i })).toBeInTheDocument();
    // The workspace context lives inside the drawer; it should not be visible
    // until the user opens the drawer.
    expect(screen.queryByText(/Open workspace manager/i)).not.toBeInTheDocument();
  });
});

describe('Header and route mapping', () => {
  it('renders the routed title in the header', () => {
    renderAppAt('/worklist');
    expect(screen.getAllByRole('heading', { level: 1, name: /Worklist/i }).length).toBeGreaterThan(0);
  });

  it('updates the header title when the route changes', async () => {
    const user = userEvent.setup();
    renderAppAt('/worklist');
    expect(screen.getAllByRole('heading', { level: 1, name: /Worklist/i }).length).toBeGreaterThan(0);
    await user.click(screen.getByRole('link', { name: /Datasets/i }));
    expect(
      await screen.findAllByRole('heading', { level: 1, name: /Datasets/i })
    ).toBeTruthy();
  });

  it('renders the page subtitle in the header', () => {
    renderAppAt('/datasets');
    expect(
      screen.getByText(/reproducible manifest of the active Workspace/i)
    ).toBeInTheDocument();
  });

  it('redirects the index route to /worklist', () => {
    renderAppAt('/');
    expect(screen.getAllByRole('heading', { level: 1, name: /Worklist/i }).length).toBeGreaterThan(0);
  });
});

describe('Route navigation', () => {
  it('clicking a nav row navigates within the router', async () => {
    const user = userEvent.setup();
    renderAppAt('/worklist');
    const admin = screen.getByRole('navigation', { name: /Administration/i });
    const link = within(admin).getByRole('link', { name: /Models.*Audit/i });
    expect(link).toHaveAttribute('href', '/models');

    // Confirm the worklist heading is current, then click.
    expect(
      screen.getAllByRole('heading', { level: 1, name: /Worklist/i }).length
    ).toBeGreaterThan(0);

    await user.click(link);

    // The shell header and page header share the route title; target the
    // in-content heading to keep the assertion specific.
    expect(
      (await screen.findAllByRole('heading', { level: 1, name: /Models & Audit/i }, { timeout: 5000 }))[1]
    ).toBeInTheDocument();
  });
});

describe('Sidebar collapse control', () => {
  it('keeps keyboard focus visibly styled on the shell control', async () => {
    const user = userEvent.setup();
    renderAppAt('/worklist');
    const control = screen.getByRole('button', { name: /Collapse sidebar/i });
    for (let index = 0; index < 12 && document.activeElement !== control; index += 1) {
      await user.tab();
    }
    expect(control).toHaveFocus();
    // jsdom does not apply :focus-visible styles, so assert the focus token
    // used by the Chakra Button contract alongside real keyboard focus.
    expect(theme.shadows.focus).toContain('0 0 0 2px');
    expect(theme.shadows.focus).toContain('0 0 0 4px');
  });

  it('toggles the sidebar to icon-only and back on desktop', async () => {
    const user = userEvent.setup();
    renderAppAt('/worklist');
    const primary = () => screen.getByRole('navigation', { name: 'Primary' });

    // Initially the labels are rendered inside the sidebar nav.
    expect(within(primary()).getByText('Worklist')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Collapse sidebar/i }));
    // Collapsed: visible nav text is gone, but the link still resolves.
    expect(within(primary()).queryByText('Worklist')).not.toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Worklist/i }).length).toBeGreaterThan(0);

    // Expand again.
    await user.click(screen.getByRole('button', { name: /Expand sidebar/i }));
    expect(within(primary()).getByText('Worklist')).toBeInTheDocument();
  });

  it('hides the sidebar and shows it again from the top bar', async () => {
    const user = userEvent.setup();
    renderAppAt('/worklist');
    await user.click(screen.getByRole('button', { name: 'Hide sidebar' }));
    expect(screen.queryByRole('navigation', { name: 'Primary' })).not.toBeInTheDocument();
    expect(window.localStorage.getItem('dr-support-screening.sidebar-mode.other.v1')).toBe('hidden');
    await user.click(screen.getByRole('button', { name: 'Show sidebar' }));
    expect(within(screen.getByRole('navigation', { name: 'Primary' })).getByText('Worklist')).toBeInTheDocument();
  });

  it('starts collapsed on image pages and keeps a separate choice there', async () => {
    const user = userEvent.setup();
    window.localStorage.setItem('dr-support-screening.sidebar-mode.other.v1', 'expanded');
    renderAppAt('/review');
    const primary = () => screen.getByRole('navigation', { name: 'Primary' });
    expect(within(primary()).queryByText('Worklist')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Hide sidebar' }));
    expect(window.localStorage.getItem('dr-support-screening.sidebar-mode.image.v1')).toBe('hidden');
    expect(window.localStorage.getItem('dr-support-screening.sidebar-mode.other.v1')).toBe('expanded');
  });

  it('starts collapsed by default on tablet to leave space for tables', () => {
    renderAppAt('/worklist', { forceTier: 'tablet' });
    const primary = screen.getByRole('navigation', { name: 'Primary' });
    // Tablet default is collapsed: visible nav text is hidden.
    expect(within(primary).queryByText('Worklist')).not.toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Worklist/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /Expand sidebar/i })).toBeInTheDocument();
  });
});

describe('Mobile drawer', () => {
  it('opens when the hamburger is tapped and exposes the nav', async () => {
    const user = userEvent.setup();
    renderAppAt('/worklist', { forceTier: 'mobile' });

    // Confirm the open trigger is in the header.
    expect(
      screen.getByRole('button', { name: /Open navigation/i })
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Open navigation/i }));

    // After opening, the drawer exposes its own navigation and workspace context.
    expect(await screen.findByRole('button', { name: /Close/i })).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Worklist/i }).length).toBeGreaterThan(0);
  });

  it('routes the user to the chosen destination', async () => {
    const user = userEvent.setup();
    renderAppAt('/worklist', { forceTier: 'mobile' });
    await user.click(screen.getByRole('button', { name: /Open navigation/i }));
    await screen.findByRole('button', { name: /Close/i });

    // The router takes the user to /datasets; the page subtitle updates.
    await user.click(screen.getAllByRole('link', { name: /Datasets/i })[0]);
    expect(
      await screen.findByText(/reproducible manifest of the active Workspace/i, {}, { timeout: 4000 })
    ).toBeInTheDocument();
  });
});

describe('Runtime indicator honesty', () => {
  it('reports offline instead of healthy when /health cannot be reached', async () => {
    renderAppAt('/worklist');
    expect(
      await screen.findByText(/Offline/i, {}, { timeout: 4000 })
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Ready$/)).not.toBeInTheDocument();
  });

  it('shows the standing research notice as a quiet label, not a warning', async () => {
    const health = { status: 'PASS_WITH_WARNINGS', lane: 'PRIVATE_AUTHORIZED_RESEARCH_BRIDGE', warnings: [RESEARCH_NOTICE] };
    const original = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => (String(input).endsWith('/health')
      ? new Response(JSON.stringify(health), { status: 200, headers: { 'content-type': 'application/json' } })
      : original(input))) as typeof fetch;
    try {
      renderAppAt('/worklist');
      expect(await screen.findByText(/Research use/i, {}, { timeout: 4000 })).toBeInTheDocument();
      expect(screen.queryByText(/^Warnings$/i)).not.toBeInTheDocument();
    } finally {
      globalThis.fetch = original;
    }
  });
});
