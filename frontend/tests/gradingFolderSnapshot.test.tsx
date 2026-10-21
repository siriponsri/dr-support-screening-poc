import { ChakraProvider } from '@chakra-ui/react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GradingFolderSnapshot } from '@/components/dataset/GradingFolderSnapshot';

const preview = {
  workspace_id: 'synthetic-workspace', can_export: true, source_state_digest: { digest: 'a'.repeat(64) },
  grading_folders: { schema_version: 'grading-folders.v1', status: 'READY', plan_sha256: 'b'.repeat(64),
    group_counts: { Grade2: 1, UNREVIEWED: 1 }, file_count: 2, record_count: 3,
    copy_bytes: 100, skipped_count: 1, duplicate_record_count: 1, skipped_reasons: { SOURCE_UNAVAILABLE: 1 } },
};
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const node = (workspaceId: string | null = 'synthetic-workspace', exportAllowed = true) => <ChakraProvider><GradingFolderSnapshot workspaceId={workspaceId} exportAllowed={exportAllowed} /></ChakraProvider>;

describe('immutable grading-folder snapshot UI', () => {
  it('shows a read-only preview before creating an explicitly bound copy snapshot', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => options?.method === 'POST'
      ? response({ workspace_id: 'synthetic-workspace', snapshot_id: 'synthetic-snapshot', directory_name: 'dataset-snapshot-fixture', manifest: { grading_folders: preview.grading_folders } })
      : response(preview));
    render(node());
    const create = screen.getByRole('button', { name: 'Create grading-folder snapshot' });
    expect(create).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Preview grading folders' }));
    expect(await screen.findByText('Grade2: 1')).toBeInTheDocument();
    expect(screen.getByText('UNREVIEWED: 1')).toBeInTheDocument();
    expect(screen.getByText('SOURCE UNAVAILABLE: 1')).toBeInTheDocument();
    expect(fetch.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true);
    fireEvent.click(create);
    fireEvent.click(create);
    expect(await screen.findByText(/2 original files copied/)).toBeInTheDocument();
    const posts = fetch.mock.calls.filter(([, options]) => options?.method === 'POST');
    expect(posts).toHaveLength(1);
    expect(JSON.parse(String(posts[0][1]?.body))).toEqual({ include_grade_folders: true,
      expected_workspace_id: 'synthetic-workspace', expected_source_state_digest: 'a'.repeat(64),
      expected_grading_plan_sha256: 'b'.repeat(64) });
    expect(create).toBeDisabled();
  });

  it('keeps hospital restriction and no-workspace states disabled without any request', () => {
    const fetch = vi.spyOn(globalThis, 'fetch');
    const view = render(node('hospital-workspace', false));
    expect(screen.getByText(/hospital export remains disabled/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Preview grading folders' }));
    expect(fetch).not.toHaveBeenCalled();
    view.rerender(node(null, false));
    expect(screen.getByText(/Open an authorized Workspace/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create grading-folder snapshot' })).toBeDisabled();
  });

  it('does not silently use an older backend that ignores the opt-in request', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ ...preview, grading_folders: undefined }));
    render(node());
    fireEvent.click(screen.getByRole('button', { name: 'Preview grading folders' }));
    expect(await screen.findByText(/unavailable on this backend/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create grading-folder snapshot' })).toBeDisabled();
    expect(fetch.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false);
  });

  it('discards a late preview across workspace changes', async () => {
    let resolve!: (value: Response) => void;
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise((done) => { resolve = done; }));
    const view = render(node());
    fireEvent.click(screen.getByRole('button', { name: 'Preview grading folders' }));
    view.rerender(node('other-workspace'));
    await act(async () => { resolve(response(preview)); });
    expect(screen.queryByText('Grade2: 1')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create grading-folder snapshot' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Preview grading folders' })).toBeEnabled();
  });

  it('invalidates a rejected creation and hides private server details', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => options?.method === 'POST'
      ? response({ detail: 'C:\\private\\synthetic-source' }, 409) : response(preview));
    render(node());
    fireEvent.click(screen.getByRole('button', { name: 'Preview grading folders' }));
    await screen.findByText('Grade2: 1');
    fireEvent.click(screen.getByRole('button', { name: 'Create grading-folder snapshot' }));
    expect(await screen.findByText(/Snapshot creation could not be verified/)).toBeInTheDocument();
    expect(screen.queryByText(/private\\synthetic/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create grading-folder snapshot' })).toBeDisabled();
    expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1);
  });

  it('explains unsupported/missing source copies without offering an empty snapshot', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({ ...preview, grading_folders: { ...preview.grading_folders,
      status: 'NO_COPYABLE_SOURCES', file_count: 0 } }));
    render(node());
    fireEvent.click(screen.getByRole('button', { name: 'Preview grading folders' }));
    await waitFor(() => expect(screen.getByText(/No supported, source-verified images can be copied/)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Create grading-folder snapshot' })).toBeDisabled();
  });
});
