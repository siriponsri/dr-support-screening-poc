import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter, useNavigate } from 'react-router-dom';
import { webcrypto } from 'node:crypto';
import { LocalTiming, localTiming, serverDurations } from '@/lib/localTiming';
import { apiJson } from '@/lib/api';
import { LocalTimingDiagnostics } from '@/components/settings/LocalTimingDiagnostics';
import { LocalTimingObserver } from '@/components/shell/LocalTimingObserver';
import { GradingFolderSnapshot } from '@/components/dataset/GradingFolderSnapshot';
import { PrismInputPreview } from '@/components/review/PrismInputPreview';
import { makePlan, model, pngBytes, previewCase } from './fixtures/prismPreview';

vi.mock('@/components/shell/workspace', () => ({ useWorkspace: () => ({ activeWorkspace: { id: 'private-workspace-runtime-key' } }) }));

const config = { cohort: 'SYNTHETIC_AUTOMATION', environment: 'UNKNOWN', phase: 'UNKNOWN' } as const;
function rig() {
  let clock = 0;
  let nextId = 0;
  const timing = new LocalTiming(() => clock, () => `opaque-${++nextId}`);
  return { timing, at: (value: number) => { clock = value; } };
}
afterEach(() => { localTiming.configure(false); localTiming.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('local-only timing contracts (synthetic clocks, not physician timings)', () => {
  it('defaults off and never serializes runtime case keys', () => {
    const { timing, at } = rig();
    timing.enter('PRIVATE_NAME_AND_FILENAME.jpg'); timing.event('review_edit');
    expect(timing.export().flows).toEqual([]);
    timing.configure(true, config); timing.enter('PRIVATE_NAME_AND_FILENAME.jpg');
    at(5); timing.event('case_ready');
    expect(JSON.stringify(timing.export())).not.toContain('PRIVATE_NAME_AND_FILENAME');
  });
  it('records ordered system waits and a verified-save endpoint independently of human thinking', () => {
    const { timing, at } = rig();
    timing.configure(true, config); timing.enter('case'); timing.modality('case', 'CFP');
    const load = timing.start('case_load', 'case');
    at(10); load.end('COMPLETED'); timing.event('case_ready', 'case');
    at(20); timing.event('image_ready', 'case'); timing.interact();
    at(50); timing.event('review_edit', 'case');
    const save = timing.start('review_save', 'case');
    at(70); save.end('COMPLETED'); timing.event('confirmed_save', 'case');
    const result = timing.export();
    expect(result.flows[0]).toMatchObject({ outcome: 'COMPLETED', human_review_ms: null, modality: 'CFP', ended_ms: 70 });
    expect(result.step_summary.find((row: { step: string }) => row.step === 'review_save')).toMatchObject({ completed_n: 1, mean_ms: 20, p95_ms: null });
    expect(result.flow_summary[0]).toMatchObject({ completed_n: 1, mean_ms: 70 });
    expect(result.entries.filter((entry: { name: string }) => entry.name === 'image_load')[0].duration_ms).toBe(20);
  });
  it('censors case switches, retires pending spans and preserves late-response correlation', () => {
    const { timing, at } = rig(); timing.configure(true, config); timing.enter('first');
    const delayed = timing.start('prism_submit', 'first');
    at(10); timing.enter('second');
    at(50); delayed.end('COMPLETED'); delayed.end('COMPLETED');
    timing.event('confirmed_save', 'first');
    const result = timing.export();
    expect(result.flows[0].outcome).toBe('INCOMPLETE');
    expect(result.flows[1].outcome).toBeNull();
    expect(result.entries.filter((entry: { name: string }) => entry.name === 'late_response_ignored')).toHaveLength(1);
    expect(result.step_summary.find((row: { step: string }) => row.step === 'prism_submit')).toMatchObject({ completed_n: 0, aborted_n: 1, mean_ms: null });
  });
  it('keeps retries separate and excludes failed/aborted samples from completed means', () => {
    const { timing, at } = rig(); timing.configure(true, config); timing.enter('case');
    const first = timing.start('preview_prepare'); at(5); first.end('FAILED');
    const second = timing.start('preview_prepare'); at(15); second.end('ABORTED');
    const third = timing.start('preview_prepare'); at(35); third.end('COMPLETED'); third.end('COMPLETED');
    expect(timing.export().step_summary.find((row: { step: string }) => row.step === 'preview_prepare')).toMatchObject({ n: 3, completed_n: 1, failed_n: 1, aborted_n: 1, mean_ms: 20, median_ms: 20 });
  });
  it('separates visible activity-window time, foreground idle and background time', () => {
    const { timing, at } = rig(); timing.configure(true, config); timing.enter('case'); timing.interact();
    at(40_000); timing.visibility(false);
    at(50_000); timing.visibility(true);
    at(60_000); timing.leave();
    expect(timing.export().flows[0]).toMatchObject({ active_observation_ms: 30_000, foreground_idle_ms: 20_000, background_ms: 10_000, human_review_ms: null });
  });
  it('does not invent absent backend timing or parse arbitrary header text', () => {
    expect(serverDurations()).toEqual({ queue_ms: null, preprocessing_ms: null, inference_ms: null });
    expect(serverDurations('queue;dur=3,preprocessing;dur=5.5,inference;dur=7')).toEqual({ queue_ms: 3, preprocessing_ms: 5.5, inference_ms: 7 });
    expect(serverDurations('patient-name;dur=2, inference;dur=-1, queue;dur=NaN')).toEqual(serverDurations());
  });
  it('stratifies modality, observation cohort and operator load phase', () => {
    const { timing, at } = rig(); timing.configure(true, config); timing.enter('one'); timing.modality('one', 'UWF');
    const one = timing.start('global_submit'); at(10); one.end('COMPLETED');
    timing.configure(true, { ...config, phase: 'WARM' }); timing.enter('two'); timing.modality('two', 'CFP');
    const two = timing.start('global_submit'); at(30); two.end('COMPLETED');
    expect(timing.export().step_summary.filter((row: { step: string }) => row.step === 'global_submit')).toHaveLength(2);
  });
  it('separates annotation confirmation from the preceding confirmed-grade flow', () => {
    const { timing, at } = rig(); timing.configure(true, config); timing.enter('case');
    at(10); timing.event('confirmed_save', 'case'); timing.enter('case', true);
    at(20); timing.event('review_edit', 'case'); timing.event('annotation_confirmed_save', 'case');
    const result = timing.export();
    expect(result.flows.map((flow: { name: string }) => flow.name)).toEqual(['case_to_confirmed_save', 'annotation_to_confirmed_save']);
    expect(result.flows.every((flow: { outcome: string }) => flow.outcome === 'COMPLETED')).toBe(true);
  });
  it('includes only allowlisted model identities and hash revisions, separately by model', () => {
    const { timing, at } = rig(); timing.configure(true, config); timing.enter('case');
    const one = timing.start('global_submit', 'case', { model_id: 'retfound-aptos5', model_version: 'a'.repeat(40) });
    at(10); one.end('COMPLETED');
    const two = timing.start('global_submit', 'case', { model_id: 'PATIENT_PRIVATE', model_version: 'NAME_PRIVATE' });
    at(20); two.end('COMPLETED');
    const result = timing.export();
    expect(JSON.stringify(result)).not.toContain('PRIVATE');
    expect(result.step_summary.filter((row: { step: string }) => row.step === 'global_submit')).toHaveLength(2);
  });
  it('exports pending observations as unfinished rather than zero-duration successes', () => {
    const { timing } = rig(); timing.configure(true, config); timing.enter('case'); timing.start('preview_prepare');
    const result = timing.export();
    expect(result.pending).toHaveLength(2); expect(result.step_summary).toEqual([]);
    expect(result.flows[0].ended_ms).toBeNull();
  });
  it('stops collection and clears retained samples without external storage', () => {
    const { timing, at } = rig(); timing.configure(true, config); timing.enter('case');
    const request = timing.start('case_load'); at(5); timing.configure(false);
    const entries = timing.export().entries.length; at(30); request.end('COMPLETED');
    expect(timing.export().entries).toHaveLength(entries);
    timing.clear(); expect(timing.export().flows).toEqual([]); expect(timing.export().entries).toEqual([]);
  });
  it('cannot repopulate cleared diagnostics from an older pending request', () => {
    const { timing } = rig(); timing.configure(true, config);
    const old = timing.folder('folder_snapshot'); timing.clear(); old.end('COMPLETED');
    expect(timing.export().flows).toEqual([]); expect(timing.export().entries).toEqual([]);
  });
  it('separates folder previews, completed copies and failed copies', () => {
    const { timing, at } = rig(); timing.configure(true, config);
    const preview = timing.folder('folder_preview'); at(10); preview.end('COMPLETED');
    const failed = timing.folder('folder_snapshot'); at(20); failed.end('FAILED');
    const copied = timing.folder('folder_snapshot'); at(40); copied.end('COMPLETED');
    expect(timing.export().flow_summary.find((row: { step: string }) => row.step === 'grading_folder_snapshot')).toMatchObject({ n: 2, completed_n: 1, failed_n: 1, mean_ms: 20 });
  });
  it('bounds memory and reports truncated observations explicitly', () => {
    const { timing } = rig(); timing.configure(true, config); timing.enter('case');
    for (let i = 0; i < 4100; i++) timing.event('review_edit');
    expect(timing.export().entries).toHaveLength(4000); expect(timing.export().dropped).toBeGreaterThan(0);
  });
  it('preserves API errors and cancellation without logging payloads or response details', async () => {
    localTiming.configure(true, config); localTiming.enter('PRIVATE-ID');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ detail: 'PRIVATE_REMARK' }) })
      .mockRejectedValueOnce(new DOMException('PRIVATE_CANCEL', 'AbortError')));
    await expect(apiJson('/v1/cases/PRIVATE-ID/review', { method: 'POST', body: 'SECRET_PAYLOAD' })).rejects.toThrow('PRIVATE_REMARK');
    await expect(apiJson('/v1/cases/PRIVATE-ID')).rejects.toMatchObject({ name: 'AbortError' });
    const data = JSON.stringify(localTiming.export());
    for (const value of ['PRIVATE-ID', 'PRIVATE_REMARK', 'SECRET_PAYLOAD', 'PRIVATE_CANCEL']) expect(data).not.toContain(value);
    expect(localTiming.export().step_summary.find((row: { step: string }) => row.step === 'case_load')).toMatchObject({ aborted_n: 1 });
  });
  it('exposes opt-in controls without making requests or medical actions', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    render(<ChakraProvider><LocalTimingDiagnostics /></ChakraProvider>);
    const checkbox = screen.getByLabelText('Record local workflow timings'); expect(checkbox).not.toBeChecked();
    fireEvent.click(checkbox); expect(localTiming.enabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Timing observation cohort'), { target: { value: 'SYNTHETIC_AUTOMATION' } });
    expect(localTiming.configuration().cohort).toBe('SYNTHETIC_AUTOMATION');
    fireEvent.click(screen.getByRole('button', { name: 'Clear local timings' }));
    expect(fetch).not.toHaveBeenCalled();
  });
  it('preserves same-case page navigation and censors a different-case route', () => {
    localTiming.configure(true, config);
    const Buttons = () => {
      const navigate = useNavigate();
      return <><button onClick={() => navigate('/clinician-review/private-case')}>Same case</button><button onClick={() => navigate('/review/other-case')}>Next case</button></>;
    };
    render(<MemoryRouter initialEntries={['/review/private-case']}><LocalTimingObserver /><Buttons /></MemoryRouter>);
    const delayed = localTiming.start('case_load', 'private-case');
    fireEvent.click(screen.getByText('Same case'));
    expect(localTiming.export().flows).toHaveLength(1);
    fireEvent.click(screen.getByText('Next case'));
    delayed.end('COMPLETED');
    const data = localTiming.export();
    expect(data.flows).toHaveLength(2); expect(data.flows[0].outcome).toBe('INCOMPLETE');
    expect(JSON.stringify(data)).not.toContain('private-case');
    expect(JSON.stringify(data)).not.toContain('private-workspace');
  });
  it('records an aborted folder preview when its Workspace changes, even if fetch resolves late', async () => {
    localTiming.configure(true, config);
    let resolve!: (value: Response) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((done) => { resolve = done; })));
    const node = (id: string) => <ChakraProvider><GradingFolderSnapshot workspaceId={id} exportAllowed /></ChakraProvider>;
    const view = render(node('private-old'));
    fireEvent.click(screen.getByRole('button', { name: 'Preview grading folders' }));
    view.rerender(node('private-new'));
    await act(async () => { resolve(new Response(JSON.stringify({ workspace_id: 'private-old', can_export: true }))); });
    expect(localTiming.export().flow_summary[0]).toMatchObject({ aborted_n: 1, completed_n: 0 });
    expect(JSON.stringify(localTiming.export())).not.toContain('private-old');
  });
  it('marks preview ready only after both verified images load, with no model submission', async () => {
    vi.stubGlobal('crypto', webcrypto);
    URL.createObjectURL = vi.fn(() => 'blob:synthetic-timing'); URL.revokeObjectURL = vi.fn();
    const fetch = vi.fn(async () => ({ ok: true, arrayBuffer: async () => pngBytes.buffer.slice(0) }));
    vi.stubGlobal('fetch', fetch);
    localTiming.configure(true, config); localTiming.enter(previewCase.image_id);
    render(<ChakraProvider><PrismInputPreview item={{ ...previewCase, prism_input_preview: makePlan() }} model={model} /></ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    const input = await screen.findByAltText('Verified planned input preview');
    expect(localTiming.export().entries.some((entry: { name: string }) => entry.name === 'preview_ready')).toBe(false);
    fireEvent.load(input); fireEvent.load(screen.getByAltText('Verified original preview'));
    await waitFor(() => expect(localTiming.export().entries.filter((entry: { name: string }) => entry.name === 'preview_ready')).toHaveLength(1));
    expect(fetch.mock.calls.every((call) => (call as unknown[]).length < 2 || (call[1] as RequestInit)?.method !== 'POST')).toBe(true);
  });
});
