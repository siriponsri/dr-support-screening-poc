import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Alert, AlertIcon, Box, Button, Flex, FormControl, FormLabel, Grid, Heading, HStack, IconButton, Input, InputGroup, InputRightElement, Stack, Text } from '@chakra-ui/react';
import { motion, useReducedMotion } from 'framer-motion';
import { BrandMark } from '@/components/common/BrandMark';
import { Eye, EyeOff, Lock, ShieldCheck } from '@/lib/icons';
import { sidebarScope } from '@/theme';
import { kkuColors } from '@/theme/colors';

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
      {state.kind === 'signedIn' ? <FadeIn motionKey={`app-${state.user.username}`}>{children}</FadeIn> : children}
    </AuthContext.Provider>
  );
}

/** Short fade between the sign-in page and the app; off when the user prefers reduced motion. */
export function FadeIn({ children, motionKey }: { children: ReactNode; motionKey: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div key={motionKey} initial={reduce ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: 'easeOut' }} style={{ height: '100%' }}>
      {children}
    </motion.div>
  );
}

const SLIDES = [
  { title: 'Import a whole set at once', body: 'Bring in a folder of CFP or UWF images, confirm the shared details once, and see which images need a closer look.' },
  { title: 'AI suggests, you decide', body: 'Each image gets a grade suggestion and possible lesion areas. Nothing becomes a label until a clinician confirms it.' },
  { title: 'Pick up where you left off', body: 'Grades and annotations are saved as you go. Export copies the images into grade folders without touching the originals.' },
];

const GRADES = ['0', '1', '2', '3', '4', 'U'];
/** The solid green call to action, matching the app's dark navigation green. */
const PRIMARY = { bg: kkuColors.sidebarBackground, color: 'white', borderColor: kkuColors.sidebarBackground,
  _hover: { bg: kkuColors.sidebarRaised }, _active: { bg: kkuColors.sidebarBackground } };
const INK = { color: 'gray.800' };

/** Illustrative preview of the review panel; not data. */
function PreviewCard() {
  return (
    <Box position="relative" w="100%" maxW="360px" mx="auto">
      <Box bg="white" color="gray.800" borderRadius="lg" p={5} boxShadow="lg">
        <Text fontSize="xs" fontWeight="bold" letterSpacing="0.06em" textTransform="uppercase" color="gray.500">Clinician decision</Text>
        <Text fontSize="lg" fontWeight="bold" mt={1} lineHeight="short" {...INK}>Confirm or correct the AI grade</Text>
        <Grid templateColumns="repeat(3, 1fr)" gap={2} mt={4}>
          {GRADES.map((grade) => (
            <Box key={grade} textAlign="center" py={2} borderRadius="md" borderWidth="1px" fontWeight="semibold" fontSize="sm"
              bg={grade === '2' ? kkuColors.sidebarBackground : 'white'} color={grade === '2' ? 'white' : 'gray.700'}
              borderColor={grade === '2' ? kkuColors.sidebarBackground : 'gray.200'} borderStyle={grade === 'U' ? 'dashed' : 'solid'}>
              {grade}
            </Box>
          ))}
        </Grid>
      </Box>
      <HStack position="absolute" right={{ base: 2, tablet: -6 }} bottom={-7} bg="white" color="gray.800" borderRadius="lg"
        px={4} py={3} boxShadow="lg" spacing={3}>
        <Box w="8px" h="8px" borderRadius="full" bg="status.warning" />
        <Text fontSize="sm" fontWeight="semibold" {...INK}>AI result awaiting review</Text>
      </HStack>
    </Box>
  );
}

function FeatureSlides() {
  const [index, setIndex] = useState(0);
  const reduce = useReducedMotion();
  useEffect(() => {
    if (reduce) return undefined;
    const timer = window.setInterval(() => setIndex((value) => (value + 1) % SLIDES.length), 6000);
    return () => window.clearInterval(timer);
  }, [reduce]);
  const slide = SLIDES[index];
  return (
    <Stack spacing={5} align="center" textAlign="center" maxW="440px" mx="auto">
      <Box minH="128px">
        <motion.div key={index} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}>
          <Heading as="h2" fontSize="3xl" fontWeight="bold" lineHeight="short" letterSpacing="-0.01em">{slide.title}</Heading>
          <Text mt={3} fontSize="md" opacity={0.85}>{slide.body}</Text>
        </motion.div>
      </Box>
      <HStack spacing={2} role="tablist" aria-label="Features">
        {SLIDES.map((item, position) => (
          <Box key={item.title} as="button" type="button" role="tab" aria-selected={position === index}
            aria-label={item.title} onClick={() => setIndex(position)} h="8px" borderRadius="full"
            w={position === index ? '24px' : '8px'} bg={position === index ? 'action.primary' : 'whiteAlpha.500'}
            transition="all 0.25s ease" />
        ))}
      </HStack>
    </Stack>
  );
}

/**
 * Clean two-panel sign-in in the app's colours: the form on a light panel, and
 * the app's dark green on the right with a preview card and short feature notes.
 */
function Frame({ title, children }: { title: string; children: ReactNode }) {
  return (
    <FadeIn motionKey={title}>
      <Flex minH="100vh" bg="surface.canvas" align="center" justify="center" p={{ base: 0, tablet: 6, laptop: 10 }}>
        <Grid w="100%" maxW="1180px" minH={{ base: '100vh', tablet: '640px' }} templateColumns={{ base: '1fr', laptop: '1fr 1.1fr' }}
          bg="surface.panel" borderRadius={{ base: 0, tablet: 'xl' }} overflow="hidden" boxShadow={{ base: 'none', tablet: 'xl' }}>
          <Flex direction="column" px={{ base: 6, tablet: 12, laptop: 16 }} py={{ base: 8, tablet: 10 }}>
            <BrandMark />
            <Flex flex={1} align="center" py={10}>
              <Box w="100%" maxW="400px">{children}</Box>
            </Flex>
            <Text fontSize="xs" color="text.secondary">Physician UX pilot for research use. Not a diagnostic device.</Text>
          </Flex>
          <Flex display={{ base: 'none', laptop: 'flex' }} direction="column" position="relative" overflow="hidden"
            sx={sidebarScope} bg="surface.panel" color="text.primary" px={12} py={10}>
            <Box position="absolute" top="-180px" right="-180px" w="520px" h="520px" borderRadius="full" bg="whiteAlpha.100" />
            <HStack justify="flex-end" position="relative" fontSize="sm" color="text.secondary" spacing={2}>
              <ShieldCheck size={16} aria-hidden="true" />
              <Text>Research use</Text>
            </HStack>
            <Flex flex={1} direction="column" justify="center" position="relative" gap={16}>
              <PreviewCard />
              <FeatureSlides />
            </Flex>
          </Flex>
        </Grid>
      </Flex>
    </FadeIn>
  );
}

function LandingSignIn({ onSignedIn }: { onSignedIn: (user: PilotUser) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

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
    <Frame title="Sign in">
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack spacing={5}>
          <Stack spacing={1}>
            <Heading as="h1" fontSize={{ base: "3xl", tablet: "4xl" }} fontWeight="bold" letterSpacing="-0.02em">Sign in</Heading>
            <Text fontSize="md" color="text.secondary">Use the account your administrator gave you.</Text>
          </Stack>
          <FormControl>
            <FormLabel>Username</FormLabel>
            <Input size="lg" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" autoFocus />
          </FormControl>
          <FormControl>
            <FormLabel>Password</FormLabel>
            <InputGroup size="lg">
              <Input type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
              <InputRightElement>
                <IconButton size="sm" variant="ghost" aria-label={showPassword ? 'Hide password' : 'Show password'}
                  icon={showPassword ? <EyeOff size={16} /> : <Eye size={16} />} onClick={() => setShowPassword((value) => !value)} />
              </InputRightElement>
            </InputGroup>
          </FormControl>
          {error && <Alert status="error" py={2} role="alert"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
          <Button type="submit" size="lg" w="100%" leftIcon={<Lock size={16} />} isLoading={busy} {...PRIMARY}>Sign in</Button>
        </Stack>
      </form>
    </Frame>
  );
}

/** The current rules from the server, in plain words. */
function PasswordRules() {
  const [rules, setRules] = useState<{ min_length: number; letters_and_numbers: boolean } | null>(null);
  useEffect(() => {
    void fetch('/v1/auth/policy').then((response) => (response.ok ? response.json() : null))
      .then((value) => setRules(value)).catch(() => setRules(null));
  }, []);
  if (!rules) return null;
  return (
    <Text fontSize="sm" color="text.secondary">
      Use at least {rules.min_length} characters{rules.letters_and_numbers ? ', with letters and numbers' : ''}.
    </Text>
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
    <Frame title="Choose a new password">
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack spacing={5}>
          <Stack spacing={1}>
            <Heading as="h1" fontSize={{ base: "2xl", tablet: "3xl" }} fontWeight="bold" letterSpacing="-0.02em">Choose a new password</Heading>
            <Text fontSize="sm" color="text.secondary">{user.username}, set your own password before you continue.</Text>
            <PasswordRules />
          </Stack>
          <FormControl><FormLabel>Current password</FormLabel>
            <Input type="password" value={current} onChange={(event) => setCurrent(event.target.value)} autoComplete="current-password" /></FormControl>
          <FormControl><FormLabel>New password</FormLabel>
            <Input type="password" value={next} onChange={(event) => setNext(event.target.value)} autoComplete="new-password" /></FormControl>
          <FormControl><FormLabel>New password again</FormLabel>
            <Input type="password" value={again} onChange={(event) => setAgain(event.target.value)} autoComplete="new-password" /></FormControl>
          {error && <Alert status="error" py={2} role="alert"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
          <Button type="submit" size="lg" w="100%" isLoading={busy} {...PRIMARY}>Save password</Button>
          <Button variant="ghost" onClick={() => void onSignOut()}>Sign out</Button>
        </Stack>
      </form>
    </Frame>
  );
}
