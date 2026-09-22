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
import { describe, it, expect } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderAppAt } from './testUtils';
import { theme } from '@/theme';

describe('Sidebar navigation', () => {
  it('renders all five primary nav destinations on desktop', () => {
    renderAppAt('/worklist');
    const primary = screen.getByRole('navigation', { name: 'Primary' });
    const primaryScope = within(primary);
    expect(primaryScope.getByRole('link', { name: /Worklist/i })).toBeInTheDocument();
    expect(primaryScope.getByRole('link', { name: /Datasets/i })).toBeInTheDocument();
    expect(primaryScope.getByRole('link', { name: /^Review$/i })).toBeInTheDocument();
    expect(primaryScope.getByRole('link', { name: /Models.*Audit/i })).toBeInTheDocument();

    // Settings lives in a separate "Configuration" landmark.
    const config = screen.getByRole('navigation', { name: /Configuration/i });
    expect(within(config).getByRole('link', { name: /Settings/i })).toBeInTheDocument();
  });

  it('marks only the active route with aria-current=page', () => {
    renderAppAt('/datasets');
    const primary = screen.getByRole('navigation', { name: 'Primary' });
    const primaryScope = within(primary);
    expect(primaryScope.getByRole('link', { name: /Datasets/i })).toHaveAttribute('aria-current', 'page');
    expect(primaryScope.getByRole('link', { name: /Worklist/i })).not.toHaveAttribute('aria-current');

    const config = screen.getByRole('navigation', { name: /Configuration/i });
    expect(within(config).getByRole('link', { name: /Settings/i })).not.toHaveAttribute('aria-current');
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
    const primary = screen.getByRole('navigation', { name: 'Primary' });
    const link = within(primary).getByRole('link', { name: /Models.*Audit/i });
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
});
