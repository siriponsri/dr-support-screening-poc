import { describe, it, vi, expect } from 'vitest';
import { loadCaseList } from '@/lib/caseNavigation';
describe('Worklist failure is distinct from an empty queue', () => {
  it('rejects an HTTP failure', async () => { vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('offline', { status: 503 })); await expect(loadCaseList()).rejects.toThrow(); });
  it('rejects a malformed successful response', async () => { vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 })); await expect(loadCaseList()).rejects.toThrow(); });
  it('keeps a genuinely empty queue valid', async () => { vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 })); await expect(loadCaseList()).resolves.toEqual([]); });
});
