import { act, renderHook, waitFor, screen } from '@testing-library/react';
import { describe, it, vi, expect } from 'vitest';
import { useRuntimeHealth } from '@/hooks/useRuntimeHealth';
import { renderAppAt } from './testUtils';

for (const payload of [null, {}, { status: 'FAIL' }, { status: 'UNKNOWN' }]) {
  it(`does not claim readiness for ${JSON.stringify(payload)}`, async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
    const { result } = renderHook(() => useRuntimeHealth());
    await waitFor(() => expect(result.current.tone).toBe('offline'));
    expect(result.current.raw).toBeUndefined();
  });
}
for (const [lane, label] of [['PRIVATE_AUTHORIZED_RESEARCH_BRIDGE', 'Authorized private evaluation'], ['PUBLIC_SYNTHETIC_BRIDGE', 'Public & synthetic only'], ['unknown', 'Data scope unavailable']]) {
  it(`shows the backend-configured data scope: ${lane}`, async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => new Response(JSON.stringify(String(input) === '/health' ? { status: 'PASS_WITH_WARNINGS', lane, warnings: [] } : String(input) === '/v1/workspaces/active' ? { workspace: null, database: { status: 'postgres' }, warnings: [] } : String(input) === '/v1/workspaces' ? { workspaces: [], active_workspace: null, warnings: [] } : []), { status: 200 }));
    renderAppAt('/worklist');
    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.getByText('Use only approved research data')).toBeInTheDocument();
  });
}
it('ignores a delayed health response from a disabled probe', async () => {
  let release!: (value: Response) => void;
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise((resolve) => { release = resolve; }));
  const { result, rerender } = renderHook(({ enabled }) => useRuntimeHealth(enabled), { initialProps: { enabled: true } });
  await waitFor(() => expect(release).toBeDefined());
  rerender({ enabled: false });
  await act(async () => release(new Response(JSON.stringify({ status: 'PASS' }), { status: 200 })));
  expect(result.current.tone).toBe('idle');
});
