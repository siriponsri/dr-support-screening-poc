import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { WorkspaceProfile } from '@/lib/api';
import { renderAppAt } from './testUtils';

const workspaceA: WorkspaceProfile = {
  id: 'ws_april',
  name: 'April DR Screening',
  input_folder: 'C:\\Data\\April-DR\\input',
  output_folder: 'C:\\Data\\April-DR\\output',
  database_path: 'C:\\Data\\April-DR\\review.sqlite',
  created_at: '2026-09-20T05:00:00+00:00',
  updated_at: '2026-09-20T05:00:00+00:00',
  last_opened: '2026-09-20T05:00:00+00:00',
};

const workspaceB: WorkspaceProfile = {
  ...workspaceA,
  id: 'ws_may',
  name: 'May DR Screening',
  input_folder: 'C:\\Data\\May-DR\\input',
  output_folder: 'C:\\Data\\May-DR\\output',
  database_path: 'C:\\Data\\May-DR\\review.sqlite',
};

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }));
}

interface MockOptions {
  workspaces?: WorkspaceProfile[];
  active?: WorkspaceProfile | null;
  openFailure?: string;
  folderPickers?: Array<{ status: 'selected' | 'cancelled' | 'unavailable'; path?: string; message?: string }>;
  databasePickers?: Array<{ status: 'selected' | 'cancelled' | 'unavailable'; path?: string; message?: string }>;
}

function mockWorkspaceApi(options: MockOptions = {}) {
  const calls: Array<{ url: string; method: string; body: unknown }> = [];
  const workspaces = options.workspaces ?? [];
  let active = options.active ?? null;
  const folderPickers = [...(options.folderPickers ?? [])];
  const databasePickers = [...(options.databasePickers ?? [])];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = input instanceof Request ? input.url : String(input);
    const method = init?.method ?? (input instanceof Request ? input.method : 'GET');
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : null;
    calls.push({ url, method, body });

    if (url.endsWith('/health')) throw new TypeError('offline');
    if (url.endsWith('/v1/workspaces/active')) {
      return jsonResponse({
        workspace: active,
        database: active ? { path: active.database_path, status: 'ready' } : { path: 'local-state/bridge/reviews.sqlite', status: 'fallback' },
        warnings: [],
      });
    }
    if (url.endsWith('/v1/workspaces/pickers/folder')) {
      const result = folderPickers.shift() ?? { status: 'cancelled' as const };
      return jsonResponse({ status: result.status, path: result.path ?? null, code: null, message: result.message ?? null });
    }
    if (url.endsWith('/v1/workspaces/pickers/database')) {
      const result = databasePickers.shift() ?? { status: 'cancelled' as const };
      return jsonResponse({ status: result.status, path: result.path ?? null, code: null, message: result.message ?? null });
    }
    if (url.endsWith('/v1/workspaces') && method === 'GET') {
      return jsonResponse({ workspaces, active_workspace_id: active?.id ?? null, active_workspace: active, warnings: [] });
    }
    if (url.endsWith('/v1/workspaces') && method === 'POST') {
      active = { ...workspaceB, ...body, id: 'ws_created' } as WorkspaceProfile;
      return jsonResponse({ workspace: active, active: true, warnings: [] });
    }
    if (url.includes('/v1/workspaces/') && url.endsWith('/open')) {
      if (options.openFailure) return jsonResponse({ detail: options.openFailure }, 409);
      active = url.includes(workspaceB.id) ? workspaceB : workspaceA;
      return jsonResponse({ workspace: active, active: true, warnings: [] });
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  });
  return calls;
}

describe('Workspace manager', () => {
  it('loads the active workspace into Settings and the shell context', async () => {
    mockWorkspaceApi({ workspaces: [workspaceA], active: workspaceA });
    renderAppAt('/settings');

    expect(await screen.findAllByText('April DR Screening')).not.toHaveLength(0);
    expect(screen.getAllByText(workspaceA.database_path)).not.toHaveLength(0);
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText(/does not move or copy images/i)).toBeInTheDocument();
    const activeRow = screen.getByRole('group', { name: 'April DR Screening workspace' });
    expect(within(activeRow).getByText('Active')).toBeInTheDocument();
    expect(within(activeRow).queryByRole('button', { name: 'Switch' })).not.toBeInTheDocument();
    expect(within(activeRow).queryByRole('button', { name: /Open/i })).not.toBeInTheDocument();
    expect(within(activeRow).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('switches an inactive workspace and moves the active context', async () => {
    const calls = mockWorkspaceApi({ workspaces: [workspaceA, workspaceB], active: workspaceA });
    const user = userEvent.setup();
    renderAppAt('/settings');
    await screen.findByText('May DR Screening');

    expect(calls.some((call) => call.url.endsWith('/ws_may/open'))).toBe(false);
    const mayRow = screen.getByRole('group', { name: 'May DR Screening workspace' });
    await user.click(within(mayRow).getByRole('button', { name: 'Switch' }));
    expect(await screen.findByText('May DR Screening is now the active workspace.')).toBeInTheDocument();
    expect(calls).toContainEqual(expect.objectContaining({
      url: expect.stringContaining('/v1/workspaces/ws_may/open'),
      method: 'POST',
    }));
    expect(within(screen.getByRole('group', { name: 'May DR Screening workspace' })).getByText('Active')).toBeInTheDocument();
    expect(within(screen.getByRole('group', { name: 'April DR Screening workspace' })).queryByText('Active')).not.toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Current workspace: May DR Screening' })).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Current workspace: April DR Screening' })).not.toBeInTheDocument();
  });

  it('preserves the previous active workspace when switching fails', async () => {
    mockWorkspaceApi({ workspaces: [workspaceA, workspaceB], active: workspaceA, openFailure: 'Database could not be opened.' });
    const user = userEvent.setup();
    renderAppAt('/settings');
    await screen.findByText('May DR Screening');

    await user.click(within(screen.getByRole('group', { name: 'May DR Screening workspace' })).getByRole('button', { name: 'Switch' }));

    expect(await screen.findByText('Database could not be opened.')).toBeInTheDocument();
    expect(within(screen.getByRole('group', { name: 'April DR Screening workspace' })).getByText('Active')).toBeInTheDocument();
    expect(within(screen.getByRole('group', { name: 'May DR Screening workspace' })).queryByText('Active')).not.toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Current workspace: April DR Screening' })).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Current workspace: May DR Screening' })).not.toBeInTheDocument();
  });

  it('treats picker cancellation as normal and explains unavailable native dialogs', async () => {
    mockWorkspaceApi({
      folderPickers: [
        { status: 'cancelled' },
        { status: 'unavailable', message: 'Native dialogs are not available in this environment.' },
      ],
    });
    const user = userEvent.setup();
    renderAppAt('/settings');
    await user.click(await screen.findByRole('button', { name: 'New workspace' }));
    const input = screen.getByLabelText('Input folder');
    await user.type(input, 'C:\\Existing\\input');
    await user.click(screen.getByRole('button', { name: 'Browse input folder' }));
    expect(await screen.findByText(/selection cancelled/i)).toBeInTheDocument();
    expect(input).toHaveValue('C:\\Existing\\input');

    await user.click(screen.getByRole('button', { name: 'Browse output folder' }));
    expect(await screen.findByText(/Native dialogs are not available/i)).toBeInTheDocument();
  });

  it('creates and activates a workspace from the editor form', async () => {
    const calls = mockWorkspaceApi();
    const user = userEvent.setup();
    renderAppAt('/settings');
    await user.click(await screen.findByRole('button', { name: 'New workspace' }));
    await user.type(screen.getByLabelText('Workspace name'), 'New local review');
    await user.type(screen.getByLabelText('Input folder'), 'C:\\Data\\input');
    await user.type(screen.getByLabelText('Output folder'), 'C:\\Data\\output');
    await user.type(screen.getByLabelText('SQLite database'), 'C:\\Data\\review.sqlite');
    await user.click(screen.getByRole('button', { name: 'Create workspace', exact: true }));

    await waitFor(() => expect(screen.getByText('Workspace created and opened.')).toBeInTheDocument());
    expect(calls.find((call) => call.url.endsWith('/v1/workspaces') && call.method === 'POST')?.body).toMatchObject({
      name: 'New local review',
      input_folder: 'C:\\Data\\input',
      output_folder: 'C:\\Data\\output',
      database_path: 'C:\\Data\\review.sqlite',
    });
    expect(screen.getAllByText('New local review')).not.toHaveLength(0);
  });
});
