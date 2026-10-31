import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Alert, AlertIcon, Box, Button, Flex, FormControl, FormLabel, Heading, Input, Stack, Text } from '@chakra-ui/react';
import { Eye, Lock } from '@/lib/icons';

export interface PilotUser {
  username: string;
  role: 'admin' | 'user';
  must_change: boolean;
  short_password: boolean;
}

interface AuthState {
  /** null when the backend has no sign-in (the app works as before). */
  user: PilotUser | null;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({ user: null, signOut: async () => undefined });

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

type GateState = { kind: 'checking' } | { kind: 'off' } | { kind: 'signedOut' } | { kind: 'signedIn'; user: PilotUser };

function isUser(value: unknown): value is PilotUser {
  return !!value && typeof value === 'object' && typeof (value as PilotUser).username === 'string'
    && ((value as PilotUser).role === 'admin' || (value as PilotUser).role === 'user');
}

async function post(path: string, body: unknown) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const value = await response.json().catch(() => null) as { detail?: unknown } | null;
  return { ok: response.ok, value, detail: typeof value?.detail === 'string' ? value.detail : null };
}

/**
 * Physician UX pilot sign-in. Asks the backend once who is signed in: a 401
 * shows the landing and sign-in page; any other answer without a user (the
 * sign-in feature is not configured) keeps the app exactly as before.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>({ kind: 'checking' });

  const check = useCallback(async () => {
    try {
      const response = await fetch('/v1/auth/me');
      if (response.status === 401) { setState({ kind: 'signedOut' }); return; }
      const value = await response.json().catch(() => null);
      setState(response.ok && isUser(value) ? { kind: 'signedIn', user: value } : { kind: 'off' });
    } catch {
      setState({ kind: 'off' });
    }
  }, []);

  useEffect(() => { void check(); }, [check]);

  const signOut = useCallback(async () => {
    await post('/v1/auth/logout', {}).catch(() => undefined);
    setState({ kind: 'signedOut' });
  }, []);

  // While checking, the app renders as before: without a session every API call is refused anyway.
  if (state.kind === 'signedOut') return <LandingSignIn onSignedIn={(user) => setState({ kind: 'signedIn', user })} />;
  if (state.kind === 'signedIn' && state.user.must_change) {
    return <ChangePassword user={state.user} onChanged={(user) => setState({ kind: 'signedIn', user })} onSignOut={signOut} />;
  }
  return (
    <AuthContext.Provider value={{ user: state.kind === 'signedIn' ? state.user : null, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

function Frame({ children }: { children: ReactNode }) {
  return (
    <Flex minH="100vh" bg="surface.canvas" direction={{ base: 'column', laptop: 'row' }}>
      <Flex flex={{ base: 'none', laptop: '1' }} bg="accent.institutionalDark" color="text.inverse"
        px={{ base: 6, laptop: 12 }} py={{ base: 8, laptop: 12 }} direction="column" justify="center">
        <Stack spacing={5} maxW="440px">
          <Flex align="center" gap={3}>
            <Flex w="44px" h="44px" borderRadius="full" bg="whiteAlpha.200" align="center" justify="center"><Eye size={22} /></Flex>
            <Stack spacing={0}>
              <Text fontWeight="semibold" fontSize="lg">Retinal Review Workbench</Text>
              <Text fontSize="sm" opacity={0.85}>Diabetic retinopathy review</Text>
            </Stack>
          </Flex>
          <Heading as="h1" size="lg" lineHeight="short">Review retinal images with AI assistance. The clinician decides.</Heading>
          <Stack spacing={2} fontSize="sm" opacity={0.9}>
            <Text>Import a set of images, let AI suggest a grade and lesion areas, then confirm or correct them.</Text>
            <Text>Physician UX pilot for research use. Not a diagnostic device.</Text>
          </Stack>
        </Stack>
      </Flex>
      <Flex flex="1" align="center" justify="center" px={{ base: 4, tablet: 8 }} py={10}>
        <Box w="100%" maxW="400px" bg="surface.panel" borderWidth="1px" borderColor="border.default" borderRadius="lg" p={{ base: 6, tablet: 8 }}>
          {children}
        </Box>
      </Flex>
    </Flex>
  );
}

function LandingSignIn({ onSignedIn }: { onSignedIn: (user: PilotUser) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) { setError('Enter your username and password.'); return; }
    setBusy(true);
    setError(null);
    try {
      const reply = await post('/v1/auth/login', { username: username.trim(), password });
      if (reply.ok && isUser(reply.value)) { setPassword(''); onSignedIn(reply.value); return; }
      setError(reply.detail ?? 'Sign-in did not work. Try again.');
    } catch {
      setError('The app could not be reached. Check that it is running and try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Frame>
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack spacing={5}>
          <Stack spacing={1}>
            <Heading as="h2" size="md">Sign in</Heading>
            <Text fontSize="sm" color="text.secondary">Use the account your administrator gave you.</Text>
          </Stack>
          <FormControl>
            <FormLabel>Username</FormLabel>
            <Input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" autoFocus />
          </FormControl>
          <FormControl>
            <FormLabel>Password</FormLabel>
            <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </FormControl>
          {error && <Alert status="error" py={2} role="alert"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
          <Button type="submit" leftIcon={<Lock size={15} />} isLoading={busy}>Sign in</Button>
        </Stack>
      </form>
    </Frame>
  );
}

function ChangePassword({ user, onChanged, onSignOut }: { user: PilotUser; onChanged: (user: PilotUser) => void; onSignOut: () => Promise<void> }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (next !== again) { setError('The new passwords do not match.'); return; }
    setBusy(true);
    setError(null);
    try {
      const reply = await post('/v1/auth/password', { current_password: current, new_password: next });
      if (reply.ok && isUser(reply.value)) { onChanged(reply.value); return; }
      setError(reply.detail ?? 'The password was not changed. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Frame>
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack spacing={5}>
          <Stack spacing={1}>
            <Heading as="h2" size="md">Choose a new password</Heading>
            <Text fontSize="sm" color="text.secondary">{user.username}, set your own password before you continue.</Text>
          </Stack>
          <FormControl><FormLabel>Current password</FormLabel>
            <Input type="password" value={current} onChange={(event) => setCurrent(event.target.value)} autoComplete="current-password" /></FormControl>
          <FormControl><FormLabel>New password</FormLabel>
            <Input type="password" value={next} onChange={(event) => setNext(event.target.value)} autoComplete="new-password" /></FormControl>
          <FormControl><FormLabel>New password again</FormLabel>
            <Input type="password" value={again} onChange={(event) => setAgain(event.target.value)} autoComplete="new-password" /></FormControl>
          {error && <Alert status="error" py={2} role="alert"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
          <Button type="submit" isLoading={busy}>Save password</Button>
          <Button variant="ghost" onClick={() => void onSignOut()}>Sign out</Button>
        </Stack>
      </form>
    </Frame>
  );
}
