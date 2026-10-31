import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { AiBatchPanel } from '@/components/worklist/AiBatchPanel';

const status = { ai_open: true, invocations_available: 1480, invocations_cap: 1500, model_server: 'STOPPED',
  quarantined: false, revoked: false };
const batch = { batch_id: 'batch_0123456789abcdef', total: 4, complete: 1, active: true, cancelled: false, note: null,
  counts: { grader: { SAVED: 2, PENDING: 1, NEEDS_CONFIRM_IMAGE: 1 },
    prism: { SAVED: 1, NOT_ELIGIBLE: 1, PENDING: 1, NEEDS_CONFIRM_IMAGE: 1 } } };

function respond(routes: Record<string, { status: number; body: unknown }>) {
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? 'GET'} ${input}`);
    const route = routes[`${init?.method ?? 'GET'} ${input}`] ?? { status: 404, body: { detail: 'Not Found' } };
    return { ok: route.status < 400, status: route.status, headers: new Headers(), json: async () => route.body };
  }));
  return calls;
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('AI batch panel', () => {
  it('stays hidden when the app is not on the shared queue', async () => {
    respond({});
    const { container } = render(<ChakraProvider><AiBatchPanel /></ChakraProvider>);
    await waitFor(() => expect(container.querySelector('[data-testid="ai-batch-panel"]')).toBeNull());
  });

  it('shows plain hours, the daily allowance and batch progress, and starts a batch', async () => {
    const calls = respond({
      'GET /v1/regular/status': { status: 200, body: status },
      'GET /v1/batches': { status: 200, body: { batches: [] } },
      'POST /v1/batches': { status: 200, body: batch },
    });
    render(<ChakraProvider><AiBatchPanel /></ChakraProvider>);
    expect(await screen.findByTestId('ai-batch-status')).toHaveTextContent(
      'AI server idle, starts when needed. Analyses left today: 1480 of 1500.');
    fireEvent.click(screen.getByRole('button', { name: 'Run AI on confirmed images' }));
    const progress = await screen.findByTestId('ai-batch-progress');
    expect(progress).toHaveTextContent('1 of 4 images have both AI results.');
    expect(progress).toHaveTextContent('Grade: 2 saved, 1 waiting, 1 need Confirm Image.');
    expect(progress).toHaveTextContent('PRISM: 1 saved, 1 waiting, 1 not run, 1 need Confirm Image.');
    expect(calls).toContain('POST /v1/batches');
    expect(screen.getByRole('button', { name: 'Stop waiting images' })).toBeInTheDocument();
  });

  it('says plainly when it is outside AI hours', async () => {
    respond({
      'GET /v1/regular/status': { status: 200, body: { ...status, ai_open: false } },
      'GET /v1/batches': { status: 200, body: { batches: [] } },
    });
    render(<ChakraProvider><AiBatchPanel /></ChakraProvider>);
    expect(await screen.findByTestId('ai-batch-status')).toHaveTextContent('Outside AI hours (06:00 to 22:00, Thailand time)');
  });
});
