import { useT } from '@/lib/i18n';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  Alert, AlertIcon, Badge, Box, Button, Checkbox, Code, FormControl, FormLabel, Grid, HStack, Input, Radio, RadioGroup, Select, SimpleGrid, Stack,
  Switch, Tab, TabList, TabPanel, TabPanels, Table, Tabs, Tbody, Td, Text, Th, Thead, Tr,
} from '@chakra-ui/react';
import { useLocation } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { PILOT_ROLES, roleLabel, useAuth, type PilotRole } from '@/components/shell/AuthGate';
import { apiJson } from '@/lib/api';

interface UserRow { username: string; role: PilotRole; disabled: boolean; must_change: boolean; updated_utc?: string }
interface DbSummary {
  storage: string; workspace: { id: string; name: string } | null; cases: number; with_ai_grade: number;
  with_prism: number; grade_confirmed: number; grade_corrected: number; annotations: number; batches: number;
}
interface CaseRow {
  image_id: string; revision: number; modality?: string; source_origin?: string; ai_grade?: number | null;
  ai_model?: string | null; prism_saved: boolean; clinician_grade?: number | null; grade_status?: string | null;
  grade_source?: string | null; lesion_review?: string | null; annotations: number; ai_runs: number;
}

const PAGE = 25;
const post = (path: string, body: unknown) => apiJson<{ users: UserRow[] }>(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

/** Administrator tools for the pilot: accounts, and a read-only view of what the app has stored. */
export function AdminPage() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const t = useT();
  if (!user || user.role !== 'admin') {
    return (
      <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
        <PageHeader pathname={pathname} subtitle={t('Accounts and stored data')} />
        <Alert status="info"><AlertIcon /><Text>{t('Only an administrator can open this page.')}</Text></Alert>
      </Box>
    );
  }
  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} subtitle={t('Accounts and stored data')} />
      <Tabs variant="enclosed" isLazy>
        <TabList><Tab>Users and sign-in</Tab><Tab>Database</Tab><Tab>AI server</Tab><Tab>Referral connector</Tab></TabList>
        <TabPanels>
          <TabPanel px={0}><UsersPanel me={user.username} /></TabPanel>
          <TabPanel px={0}><DatabasePanel /></TabPanel>
          <TabPanel px={0}><ServerModePanel /></TabPanel>
          <TabPanel px={0}><ReferralConnectorPanel /></TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}

function UsersPanel({ me }: { me: string }) {
  const t = useT();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<PilotRole>('physician');

  const load = useCallback(async () => {
    try { setUsers((await apiJson<{ users: UserRow[] }>('/v1/admin/users')).users); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Users could not be loaded.'); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    try {
      setUsers((await post('/v1/admin/users', { username: username.trim().toLowerCase(), password, role })).users);
      setNotice(`${t('Saved')} ${username.trim().toLowerCase()}. ${t('They choose their own password at first sign-in.')}`);
      setUsername(''); setPassword(''); setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The account was not saved.'); }
  };

  const toggle = async (row: UserRow) => {
    try { setUsers((await post('/v1/admin/users', { username: row.username, disabled: !row.disabled })).users); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'The account was not changed.'); }
  };

  return (
    <Grid templateColumns={{ base: '1fr', desktop: 'minmax(0, 1.4fr) minmax(0, 1fr)' }} gap={5} alignItems="start">
    <Stack spacing={5}>
      <Section title="Add a user or reset a password" description={t('Give the person a temporary password; the app asks them to choose their own at first sign-in.')}>
        <form onSubmit={(event) => void save(event)}>
          <SimpleGrid columns={{ base: 1, tablet: 4 }} spacing={3} alignItems="end">
            <FormControl><FormLabel>{t('Username')}</FormLabel><Input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="off" /></FormControl>
            <FormControl><FormLabel>{t('Temporary password')}</FormLabel><Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" /></FormControl>
            <FormControl><FormLabel>{t('Role')}</FormLabel>
              <Select value={role} onChange={(event) => setRole(event.target.value as PilotRole)}>
                {PILOT_ROLES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </Select></FormControl>
            <Button type="submit" isDisabled={!username.trim() || !password}>{t('Save account')}</Button>
          </SimpleGrid>
        </form>
      </Section>
      {notice && <Alert status="success" py={2}><AlertIcon /><Text fontSize="sm">{notice}</Text></Alert>}
      {error && <Alert status="error" py={2}><AlertIcon /><Text fontSize="sm">{t(error)}</Text></Alert>}
      <Section title="Accounts" description={t('Disabling an account signs that person out at once.')}>
        <Box overflowX="auto">
          <Table size="sm">
            <Thead><Tr><Th>Username</Th><Th>Role</Th><Th>Status</Th><Th>Updated</Th><Th /></Tr></Thead>
            <Tbody>
              {users.map((row) => (
                <Tr key={row.username}>
                  <Td fontWeight="semibold">{row.username}</Td>
                  <Td>{roleLabel(row.role)}</Td>
                  <Td>
                    {row.disabled ? <Badge colorScheme="gray">Disabled</Badge>
                      : row.must_change ? <Badge colorScheme="orange">Must set password</Badge> : <Badge colorScheme="green">Active</Badge>}
                  </Td>
                  <Td fontSize="xs" color="text.secondary">{row.updated_utc ? new Date(row.updated_utc).toLocaleString() : ''}</Td>
                  <Td textAlign="right">
                    {row.username !== me && (
                      <Button size="xs" variant="outline" onClick={() => void toggle(row)}>{row.disabled ? t('Enable') : t('Disable')}</Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      </Section>
    </Stack>
    <PolicyPanel />
    </Grid>
  );
}

interface Policy {
  min_length: number; letters_and_numbers: boolean; first_sign_in_change: boolean;
  max_failures: number; lockout_minutes: number; idle_minutes: number;
}
type Bounds = Record<'min_length' | 'max_failures' | 'lockout_minutes' | 'idle_minutes', [number, number]>;

const NUMBER_FIELDS: Array<{ key: keyof Bounds; label: string; unit: string }> = [
  { key: 'min_length', label: 'Minimum password length', unit: 'characters' },
  { key: 'max_failures', label: 'Lock the account after', unit: 'wrong tries' },
  { key: 'lockout_minutes', label: 'Keep it locked for', unit: 'minutes' },
  { key: 'idle_minutes', label: 'Sign out when idle for', unit: 'minutes' },
];

/** Sign-in rules in plain words; every number stays within safe limits set by the server. */
function PolicyPanel() {
  const t = useT();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [bounds, setBounds] = useState<Bounds | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void apiJson<{ policy: Policy; bounds: Bounds }>('/v1/admin/policy')
      .then((value) => { setPolicy(value.policy); setBounds(value.bounds); })
      .catch((reason) => setError(reason instanceof Error ? reason.message : 'The policy could not be loaded.'));
  }, []);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!policy) return;
    try {
      const value = await apiJson<{ policy: Policy }>('/v1/admin/policy', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(policy),
      });
      setPolicy(value.policy); setSaved(true); setError(null);
    } catch (reason) { setSaved(false); setError(reason instanceof Error ? reason.message : 'The policy was not saved.'); }
  };

  return (
    <Section title="Sign-in policy" description="Applies to new and changed passwords and to every sign-in.">
      {!policy || !bounds ? (error ? <Text fontSize="sm" color="status.danger">{t(error)}</Text> : <Text fontSize="sm" color="text.secondary">{t('Loading...')}</Text>) : (
        <form onSubmit={(event) => void save(event)}>
          <Stack spacing={0} divider={<Box borderTopWidth="1px" borderColor="border.subtle" />}>
            {NUMBER_FIELDS.map(({ key, label, unit }) => (
              <HStack key={key} justify="space-between" py={2.5} spacing={3}>
                <Text fontSize="sm">{t(label)}</Text>
                <HStack spacing={2}>
                  <Input type="number" size="sm" w="76px" min={bounds[key][0]} max={bounds[key][1]} value={policy[key]}
                    aria-label={t(label)} onChange={(event) => { setSaved(false); setPolicy({ ...policy, [key]: Number(event.target.value) }); }} />
                  <Text fontSize="xs" color="text.secondary" w="72px">{t(unit)}</Text>
                </HStack>
              </HStack>
            ))}
            <HStack justify="space-between" py={2.5}>
              <Text fontSize="sm">{t('Passwords need letters and numbers')}</Text>
              <Switch isChecked={policy.letters_and_numbers} aria-label={t('Passwords need letters and numbers')}
                onChange={(event) => { setSaved(false); setPolicy({ ...policy, letters_and_numbers: event.target.checked }); }} />
            </HStack>
            <HStack justify="space-between" py={2.5}>
              <Text fontSize="sm">{t('New users choose their own password')}</Text>
              <Switch isChecked={policy.first_sign_in_change} aria-label={t('New users choose their own password')}
                onChange={(event) => { setSaved(false); setPolicy({ ...policy, first_sign_in_change: event.target.checked }); }} />
            </HStack>
            <HStack justify="space-between" py={2.5}>
              <Text fontSize="sm">{t('Usernames')}</Text>
              <Text fontSize="sm" color="text.secondary">{t('3 to 40 of a to z, 0 to 9, dot, dash, underscore')}</Text>
            </HStack>
          </Stack>
          {error && <Text mt={2} fontSize="sm" color="status.danger">{t(error)}</Text>}
          <HStack mt={3} spacing={3}>
            <Button type="submit" size="sm">{t('Save policy')}</Button>
            {saved && <Text fontSize="sm" color="status.success">{t('Saved')}</Text>}
          </HStack>
        </form>
      )}
    </Section>
  );
}

function gradeText(value: number | null | undefined) {
  return value === null || value === undefined ? '' : String(value);
}

function DatabasePanel() {
  const t = useT();
  const [summary, setSummary] = useState<DbSummary | null>(null);
  const [rows, setRows] = useState<CaseRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [record, setRecord] = useState<{ image_id: string; record: unknown } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextOffset: number, term: string) => {
    try {
      const [nextSummary, page] = await Promise.all([
        apiJson<DbSummary>('/v1/admin/db/summary'),
        apiJson<{ total: number; rows: CaseRow[] }>(`/v1/admin/db/cases?offset=${nextOffset}&limit=${PAGE}&search=${encodeURIComponent(term)}`),
      ]);
      setSummary(nextSummary); setRows(page.rows); setTotal(page.total); setOffset(nextOffset); setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The database could not be read.'); }
  }, []);
  useEffect(() => { void load(0, ''); }, [load]);

  const open = async (imageId: string) => {
    try { setRecord(await apiJson(`/v1/admin/db/cases/${encodeURIComponent(imageId)}`)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'The record could not be read.'); }
  };

  const tiles: Array<[string, string | number]> = summary ? [
    ['Storage', summary.storage], ['Workspace', summary.workspace?.name ?? 'None open'], ['Cases', summary.cases],
    ['AI grade saved', summary.with_ai_grade], ['PRISM saved', summary.with_prism], ['Grade confirmed', summary.grade_confirmed],
    ['Grade corrected', summary.grade_corrected], ['Annotations', summary.annotations], ['AI batches', summary.batches],
  ] : [];

  return (
    <Stack spacing={5}>
      <Alert status="warning" py={2}><AlertIcon /><Text fontSize="sm">{t('Read-only view. It can contain patient data: do not share screenshots of it.')}</Text></Alert>
      {error && <Alert status="error" py={2}><AlertIcon /><Text fontSize="sm">{t(error)}</Text></Alert>}
      <SimpleGrid columns={{ base: 2, tablet: 3, laptop: 5 }} spacing={3}>
        {tiles.map(([label, value]) => (
          <Box key={label} borderWidth="1px" borderColor="border.default" bg="surface.panel" borderRadius="md" p={3}>
            <Text fontSize="xs" color="text.secondary">{label}</Text>
            <Text fontSize="lg" fontWeight="semibold" noOfLines={1}>{value}</Text>
          </Box>
        ))}
      </SimpleGrid>
      <Section title="Stored cases" description="AI results and clinician decisions are kept separately; open a case to see its full stored record."
        action={(
          <HStack as="form" onSubmit={(event) => { event.preventDefault(); void load(0, search); }}>
            <Input size="sm" placeholder={t('Search image ID')} value={search} onChange={(event) => setSearch(event.target.value)} />
            <Button size="sm" type="submit" variant="outline">{t('Search')}</Button>
          </HStack>
        )}>
        <Box overflowX="auto">
          <Table size="sm">
            <Thead><Tr><Th>Image ID</Th><Th>Type</Th><Th>Source</Th><Th>AI grade</Th><Th>PRISM</Th><Th>Clinician grade</Th><Th>Grade review</Th><Th>Lesion review</Th><Th isNumeric>Annotations</Th><Th isNumeric>Rev.</Th></Tr></Thead>
            <Tbody>
              {rows.map((row) => (
                <Tr key={row.image_id} _hover={{ bg: 'surface.subtle', cursor: 'pointer' }} onClick={() => void open(row.image_id)}>
                  <Td><Code fontSize="xs">{row.image_id.length > 16 ? `${row.image_id.slice(0, 12)}...` : row.image_id}</Code></Td>
                  <Td>{row.modality ?? ''}</Td>
                  <Td>{row.source_origin ?? ''}</Td>
                  <Td>{gradeText(row.ai_grade)}</Td>
                  <Td>{row.prism_saved ? 'Saved' : ''}</Td>
                  <Td>{gradeText(row.clinician_grade)}</Td>
                  <Td>{row.grade_source === 'AI_CORRECTED' ? 'Corrected' : row.grade_source === 'AI_ACCEPTED' ? 'Accepted' : row.grade_status === 'CONFIRMED' ? 'Confirmed' : 'Not reviewed'}</Td>
                  <Td>{row.lesion_review ? 'Reviewed' : 'Not reviewed'}</Td>
                  <Td isNumeric>{row.annotations}</Td>
                  <Td isNumeric>{row.revision}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
        <HStack justify="space-between" mt={3} fontSize="sm">
          <Text color="text.secondary">{total ? `${offset + 1} ${t('to')} ${Math.min(offset + PAGE, total)} ${t('of')} ${total}` : t('No cases')}</Text>
          <HStack>
            <Button size="sm" variant="outline" isDisabled={offset === 0} onClick={() => void load(Math.max(0, offset - PAGE), search)}>{t('Previous')}</Button>
            <Button size="sm" variant="outline" isDisabled={offset + PAGE >= total} onClick={() => void load(offset + PAGE, search)}>{t('Next')}</Button>
          </HStack>
        </HStack>
      </Section>
      {record && (
        <Section title="Stored record" description={`${t('Image')} ${record.image_id}. ${t('Read-only.')}`}
          action={<Button size="sm" variant="ghost" onClick={() => setRecord(null)}>{t('Close')}</Button>}>
          <Box as="pre" fontSize="xs" bg="surface.subtle" p={3} borderRadius="md" maxH="480px" overflow="auto" whiteSpace="pre-wrap">
            {JSON.stringify(record.record, null, 2)}
          </Box>
        </Section>
      )}
    </Stack>
  );
}


interface ServerMode {
  mode: 'hospital_local' | 'team_server'; modes: Record<string, string>; consented_workspaces: string[];
  current_workspace: string | null; current_model_host: string; applies: string;
}

/** Which AI server the app uses. The team server takes only workspaces marked as public or consented images. */
function ServerModePanel() {
  const t = useT();
  const [state, setState] = useState<ServerMode | null>(null);
  const [mode, setMode] = useState<ServerMode['mode']>('hospital_local');
  const [consented, setConsented] = useState<string[]>([]);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  useEffect(() => {
    void apiJson<ServerMode>('/v1/admin/server-mode').then((value) => {
      setState(value); setMode(value.mode); setConsented(value.consented_workspaces);
    }).catch((reason) => setMessage({ tone: 'error', text: reason instanceof Error ? reason.message : 'Could not load the setting.' }));
  }, []);
  const workspace = state?.current_workspace ?? null;
  const test = async () => {
    try {
      const result = await apiJson<{ reachable: boolean; message: string }>('/v1/admin/server-mode/test');
      setMessage({ tone: result.reachable ? 'success' : 'error', text: result.message });
    } catch (reason) { setMessage({ tone: 'error', text: reason instanceof Error ? reason.message : 'The test could not run.' }); }
  };
  const save = async () => {
    try {
      const value = await apiJson<ServerMode>('/v1/admin/server-mode', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, consented_workspaces: consented }),
      });
      setState(value); setMessage({ tone: 'success', text: `Saved. It applies ${value.applies}.` });
    } catch (reason) { setMessage({ tone: 'error', text: reason instanceof Error ? reason.message : 'Not saved.' }); }
  };
  return (
    <Stack spacing={5} maxW="760px">
      <Section title="AI server" description="Choose where AI analysis runs. Images may leave the hospital only when they are public or consented.">
        <Stack spacing={4}>
          <RadioGroup value={mode} onChange={(value) => setMode(value as ServerMode['mode'])}>
            <Stack spacing={2}>
              <Radio value="hospital_local">{t('Hospital model server (all admitted images)')}</Radio>
              <Radio value="team_server">{t('Team server, dr-train (public or consented images only)')}</Radio>
            </Stack>
          </RadioGroup>
          {workspace && (
            <Checkbox isChecked={consented.includes(workspace)}
              onChange={(event) => setConsented((current) => event.target.checked
                ? [...new Set([...current, workspace])] : current.filter((item) => item !== workspace))}>
              {t('This workspace')} ({workspace}) {t('holds only public or consented images')}
            </Checkbox>
          )}
          <Text fontSize="sm" color="text.secondary">
            {t('Model server in use now:')} {state?.current_model_host || t('not set')}. {t('A change applies at the next start.')}
          </Text>
          <HStack spacing={3} flexWrap="wrap">
            <Button onClick={() => void save()} isDisabled={!state}>{t('Save AI server')}</Button>
            <Button variant="outline" onClick={() => void test()}>{t('Test connection')}</Button>
          </HStack>
        </Stack>
      </Section>
      {message && <Alert status={message.tone} py={2}><AlertIcon /><Text fontSize="sm">{t(message.text)}</Text></Alert>}
    </Stack>
  );
}


interface Connector { kind: 'none' | 'file_drop' | 'webhook'; folder: string; url: string; token_env: string }

/** Where signed referrals go. Off by default; sending patient data outside needs the hospital's approval first. */
function ReferralConnectorPanel() {
  const t = useT();
  const [form, setForm] = useState<Connector>({ kind: 'none', folder: '', url: '', token_env: '' });
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  useEffect(() => {
    void apiJson<Connector>('/v1/admin/referral-connector').then((value) => setForm({
      kind: value.kind, folder: value.folder, url: value.url, token_env: value.token_env,
    })).catch(() => setMessage({ tone: 'error', text: 'Could not load the setting.' }));
  }, []);
  const save = async () => {
    try {
      await apiJson<Connector>('/v1/admin/referral-connector', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form),
      });
      setMessage({ tone: 'success', text: 'Saved.' });
    } catch (reason) { setMessage({ tone: 'error', text: reason instanceof Error ? reason.message : 'Not saved.' }); }
  };
  return (
    <Stack spacing={5} maxW="760px">
      <Section title="Referral connector" description="Where signed referrals go when someone presses Send. Patient data may leave the app only after the hospital approves the destination.">
        <Stack spacing={4}>
          <RadioGroup value={form.kind} onChange={(kind) => setForm({ ...form, kind: kind as Connector['kind'] })}>
            <Stack spacing={2}>
              <Radio value="none">{t('Off (nothing leaves the app)')}</Radio>
              <Radio value="file_drop">{t('File drop folder (FHIR JSON for a hospital integration engine)')}</Radio>
              <Radio value="webhook">{t('HTTPS webhook (FHIR JSON)')}</Radio>
            </Stack>
          </RadioGroup>
          {form.kind === 'file_drop' && (
            <FormControl><FormLabel>{t('Folder (full path)')}</FormLabel>
              <Input value={form.folder} onChange={(event) => setForm({ ...form, folder: event.target.value })} /></FormControl>
          )}
          {form.kind === 'webhook' && (
            <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={3}>
              <FormControl><FormLabel>{t('Address (https://)')}</FormLabel>
                <Input value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} /></FormControl>
              <FormControl><FormLabel>{t('Token variable name (optional)')}</FormLabel>
                <Input value={form.token_env} placeholder="REFERRAL_TOKEN" onChange={(event) => setForm({ ...form, token_env: event.target.value })} /></FormControl>
            </SimpleGrid>
          )}
          <Text fontSize="sm" color="text.secondary">{t('The server operator first lists the allowed webhook addresses and the drop folder area. Other destinations are refused.')}</Text>
          <Button alignSelf="flex-start" onClick={() => void save()}>{t('Save connector')}</Button>
        </Stack>
      </Section>
      {message && <Alert status={message.tone} py={2}><AlertIcon /><Text fontSize="sm">{t(message.text)}</Text></Alert>}
    </Stack>
  );
}
