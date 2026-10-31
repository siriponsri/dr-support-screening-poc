import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { AuthGate, useAuth } from '@/components/shell/AuthGate';

function Inside() {
  const { user } = useAuth();
  return <p>App content for {user ? user.username : 'no sign-in'}</p>;
}

function routes(table: Record<string, () => { status: number; body: unknown }>) {
  const calls: Array<{ path: string; body?: string }> = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    calls.push({ path: input, body: init?.body as string | undefined });
    const route = table[input] ?? (() => ({ status: 404, body: { detail: 'Not Found' } }));
    const { status, body } = route();
    return { ok: status < 400, status, json: async () => body };
  }));
  return calls;
}

function mount() {
  return render(<ChakraProvider><AuthGate><Inside /></AuthGate></ChakraProvider>);
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('pilot sign-in gate', () => {
  it('keeps the app unchanged when the backend has no sign-in', async () => {
    routes({});
    mount();
    expect(await screen.findByText('App content for no sign-in')).toBeInTheDocument();
  });

  it('shows the landing sign-in page, signs in, and never keeps the password on screen', async () => {
    let signedIn = false;
    const calls = routes({
      '/v1/auth/me': () => signedIn ? { status: 200, body: { username: 'admin', role: 'admin', must_change: false, short_password: true } }
        : { status: 401, body: { detail: 'Please sign in.' } },
      '/v1/auth/login': () => { signedIn = true; return { status: 200, body: { username: 'admin', role: 'admin', must_change: false, short_password: true } }; },
    });
    mount();
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByText('Physician UX pilot for research use. Not a diagnostic device.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pilot-pass' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('App content for admin')).toBeInTheDocument();
    expect(calls.find((call) => call.path === '/v1/auth/login')?.body).toBe(JSON.stringify({ username: 'admin', password: 'pilot-pass' }));
    expect(window.localStorage.getItem('dr_session')).toBeNull();
  });

  it('shows the server wording for a wrong password', async () => {
    routes({
      '/v1/auth/me': () => ({ status: 401, body: { detail: 'Please sign in.' } }),
      '/v1/auth/login': () => ({ status: 401, body: { detail: 'The username or password is not correct.' } }),
    });
    mount();
    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The username or password is not correct.');
  });

  it('asks a new user to choose a password before the app opens', async () => {
    routes({
      '/v1/auth/me': () => ({ status: 200, body: { username: 'doctor1', role: 'user', must_change: true, short_password: false } }),
      '/v1/auth/password': () => ({ status: 200, body: { username: 'doctor1', role: 'user', must_change: false, short_password: false } }),
    });
    mount();
    expect(await screen.findByRole('heading', { name: 'Choose a new password' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'first-pass' } });
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'my-own-pass' } });
    fireEvent.change(screen.getByLabelText('New password again'), { target: { value: 'my-own-pass' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save password' }));
    expect(await screen.findByText('App content for doctor1')).toBeInTheDocument();
  });
});
