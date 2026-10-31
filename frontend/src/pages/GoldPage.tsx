import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import {
  Alert, AlertIcon, Badge, Box, Button, Checkbox, FormControl, FormLabel, Grid, HStack, Image, Input, Radio,
  RadioGroup, SimpleGrid, Stack, Table, Tbody, Td, Text, Th, Thead, Tr,
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { useAuth } from '@/components/shell/AuthGate';
import { apiJson, type CaseRecord } from '@/lib/api';

/** Gold-100 research labelling: the expert's grade is the reference; the AI suggestion appears only afterwards. */
interface GoldRecord {
  blind?: { grade: number | null; gradable: boolean };
  ai_revealed_at?: string;
  after_ai?: { grade: number | null; changed: boolean };
}
interface GoldState { revision: number; gold_label: GoldRecord | null; ai_grade?: { grade: number | null; model_id?: string | null } }

const GRADES = ['0 No apparent DR', '1 Mild NPDR', '2 Moderate NPDR', '3 Severe NPDR', '4 PDR'];
const QUADRANTS = ['superior', 'inferior', 'nasal', 'temporal'] as const;
const SIGNS: [string, string][] = [['HAEMORRHAGES', 'Haemorrhages'], ['VENOUS_BEADING', 'Venous beading'], ['IRMA', 'IRMA'],
  ['NEW_VESSELS', 'New vessels'], ['HARD_EXUDATES_NEAR_FOVEA', 'Hard exudates near the fovea']];
const put = (url: string, body: unknown, method = 'PUT') => apiJson<GoldState>(url, {
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

function status(record: GoldRecord | null | undefined): string {
  if (!record?.blind) return 'Not started';
  if (record.after_ai) return 'Done';
  return record.ai_revealed_at ? 'AI viewed' : 'Your grade saved';
}

export function GoldPage() {
  const { imageId } = useParams();
  return imageId ? <GoldLabel imageId={imageId} /> : <GoldList />;
}

function GoldList() {
  const { pathname } = useLocation();
  const [cases, setCases] = useState<CaseRecord[] | null>(null);
  const [states, setStates] = useState<Record<string, string>>({});
  useEffect(() => {
    void apiJson<CaseRecord[]>('/v1/cases').then(async (loaded) => {
      setCases(loaded);
      const entries = await Promise.all(loaded.map(async (item) => {
        const state = await apiJson<GoldState>(`/v1/cases/${encodeURIComponent(item.image_id)}/gold-label`).catch(() => null);
        return [item.image_id, status(state?.gold_label)] as const;
      }));
      setStates(Object.fromEntries(entries));
    }).catch(() => setCases([]));
  }, []);
  const done = Object.values(states).filter((value) => value === 'Done').length;
  return (
    <Box as="main" maxW="1200px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} subtitle={`${done} of ${cases?.length ?? 0} images labelled`} />
      <Section title="Images" description="Open an image to grade it. Your grade is the reference; the AI suggestion stays hidden until you save it.">
        <Box overflowX="auto">
          <Table size="sm">
            <Thead><Tr><Th>Image</Th><Th>Type</Th><Th>Status</Th><Th /></Tr></Thead>
            <Tbody>
              {(cases ?? []).map((item) => (
                <Tr key={item.image_id}>
                  <Td fontFamily="mono">{item.image_id.slice(0, 12)}</Td>
                  <Td>{item.modality}</Td>
                  <Td><Badge colorScheme={states[item.image_id] === 'Done' ? 'green' : 'gray'}>{states[item.image_id] ?? '...'}</Badge></Td>
                  <Td textAlign="right"><Button as={Link} size="sm" variant="outline" to={`/gold/${encodeURIComponent(item.image_id)}`}>Open</Button></Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      </Section>
    </Box>
  );
}

function GoldLabel({ imageId }: { imageId: string }) {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const url = `/v1/cases/${encodeURIComponent(imageId)}/gold-label`;
  const started = useRef(Date.now());
  const [state, setState] = useState<GoldState | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [gradable, setGradable] = useState<boolean | null>(null);
  const [grade, setGrade] = useState<number | null>(null);
  const [confidence, setConfidence] = useState<string | null>(null);
  const [signs, setSigns] = useState<Record<string, string[]>>({});
  const [reason, setReason] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState('');
  const [finalGrade, setFinalGrade] = useState<number | null>(null);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const seconds = () => Math.round((Date.now() - started.current) / 1000);

  const load = useCallback(async () => {
    const [next, item] = await Promise.all([apiJson<GoldState>(url), apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(imageId)}`)]);
    setImageUrl(item.image_url);
    setState(next);
    if (next.gold_label?.blind) { setGrade(next.gold_label.blind.grade); setGradable(next.gold_label.blind.gradable); }
    if (next.gold_label?.after_ai) setFinalGrade(next.gold_label.after_ai.grade);
  }, [url, imageId]);
  useEffect(() => { void load().catch(() => setMessage({ tone: 'error', text: 'This image could not be loaded.' })); }, [load]);

  const run = async (action: () => Promise<GoldState>, done: string) => {
    try { const next = await action(); setState((current) => ({ ...current, ...next })); setMessage({ tone: 'success', text: done }); }
    catch (reason) { setMessage({ tone: 'error', text: reason instanceof Error ? reason.message : 'Not saved.' }); }
  };
  const record = state?.gold_label;
  const locked = Boolean(record?.ai_revealed_at);
  const quadrantSigns = useMemo(() => Object.fromEntries(Object.entries(signs).filter(([, list]) => list.length)), [signs]);
  const canWrite = !user || ['expert', 'admin'].includes(user.role);

  return (
    <Box as="main" maxW="1400px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} subtitle={`Status: ${status(record)}`} />
      {!canWrite && <Alert status="info" mb={4}><AlertIcon /><Text fontSize="sm">Gold labels are entered by the ophthalmologist (expert) account.</Text></Alert>}
      <Grid templateColumns={{ base: '1fr', desktop: 'minmax(0, 1.3fr) minmax(0, 1fr)' }} gap={5} alignItems="start">
        {imageUrl ? <Image src={imageUrl} alt="Retinal image for grading" borderRadius="md" bg="black" w="100%" />
          : <Box bg="surface.subtle" borderRadius="md" minH="320px" />}
        <Stack spacing={4}>
          <Section title="Your grade" description="Your grade is the reference. Only the grade and gradability are needed.">
            <Stack spacing={3}>
              <RadioGroup value={gradable == null ? '' : String(gradable)} onChange={(value) => setGradable(value === 'true')} isDisabled={locked || !canWrite}>
                <HStack spacing={4}><Radio value="true">Gradable</Radio><Radio value="false">Ungradable</Radio></HStack>
              </RadioGroup>
              <RadioGroup value={grade == null ? '' : String(grade)} onChange={(value) => setGrade(Number(value))} isDisabled={locked || !canWrite || gradable === false}>
                <Stack spacing={1}>{GRADES.map((text, index) => <Radio key={index} value={String(index)}>{text}</Radio>)}</Stack>
              </RadioGroup>
              <RadioGroup value={confidence ?? ''} onChange={setConfidence} isDisabled={locked || !canWrite}>
                <HStack spacing={4}><Text fontSize="sm">Confidence (optional):</Text><Radio value="SURE">Sure</Radio><Radio value="UNSURE">Unsure</Radio></HStack>
              </RadioGroup>
              <Text fontSize="sm" fontWeight="semibold">Signs by quadrant (optional)</Text>
              <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={2}>
                {QUADRANTS.map((quadrant) => (
                  <Stack key={quadrant} spacing={1} borderWidth="1px" borderColor="border.subtle" borderRadius="md" p={2}>
                    <Text fontSize="sm" textTransform="capitalize">{quadrant}</Text>
                    {SIGNS.map(([key, label]) => (
                      <Checkbox key={key} size="sm" isDisabled={locked || !canWrite} isChecked={(signs[quadrant] ?? []).includes(key)}
                        onChange={(event) => setSigns((current) => ({ ...current, [quadrant]: event.target.checked
                          ? [...(current[quadrant] ?? []), key] : (current[quadrant] ?? []).filter((item) => item !== key) }))}>{label}</Checkbox>
                    ))}
                  </Stack>
                ))}
              </SimpleGrid>
              <RadioGroup value={reason ?? ''} onChange={setReason} isDisabled={locked || !canWrite}>
                <HStack spacing={3} flexWrap="wrap"><Text fontSize="sm">Why chosen (optional):</Text>
                  {[['TYPICAL', 'Typical'], ['HARD', 'Hard'], ['SEVERE', 'Severe'], ['RARE', 'Rare']].map(([key, label]) => <Radio key={key} value={key}>{label}</Radio>)}</HStack>
              </RadioGroup>
              {!user && <FormControl maxW="320px"><FormLabel fontSize="sm">Your name</FormLabel><Input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></FormControl>}
              <Button alignSelf="flex-start" isDisabled={locked || !canWrite || gradable == null || (gradable && grade == null)}
                onClick={() => void run(() => put(`${url}/blind`, {
                  revision: state?.revision, reviewer, seconds_spent: seconds(),
                  label: { gradable, grade: gradable ? grade : null, confidence, quadrant_signs: quadrantSigns, selection_reason: reason },
                }), 'Your grade is saved.')}>Save my grade</Button>
            </Stack>
          </Section>
          <Section title="AI suggestion (optional)" description="Shown only after your own grade is saved. Your saved grade stays as it is.">
            {state?.ai_grade ? (
              <Stack spacing={3}>
                <Text fontSize="sm">AI suggestion: {state.ai_grade.grade == null ? 'no AI result' : GRADES[state.ai_grade.grade]}</Text>
                <RadioGroup value={finalGrade == null ? '' : String(finalGrade)} onChange={(value) => setFinalGrade(Number(value))} isDisabled={!canWrite}>
                  <Stack spacing={1}><Text fontSize="sm">Your final grade (the same or changed):</Text>
                    {GRADES.map((text, index) => <Radio key={index} value={String(index)}>{text}</Radio>)}</Stack>
                </RadioGroup>
                <Button alignSelf="flex-start" variant="outline" isDisabled={!canWrite || finalGrade == null}
                  onClick={() => void run(() => put(`${url}/final`, { revision: state?.revision, grade: finalGrade, reviewer, seconds_spent: seconds() }), 'Final grade saved. Thank you.')}>Save final grade</Button>
              </Stack>
            ) : (
              <Button alignSelf="flex-start" variant="ghost" isDisabled={!record?.blind || !canWrite}
                onClick={() => void run(() => put(`${url}/reveal-ai`, { revision: state?.revision, reviewer }, 'POST'), 'AI suggestion shown.')}>Show AI suggestion</Button>
            )}
          </Section>
          {message && <Alert status={message.tone} py={2}><AlertIcon /><Text fontSize="sm">{message.text}</Text></Alert>}
          <Button as={Link} to="/gold" variant="ghost" alignSelf="flex-start">Back to the list</Button>
        </Stack>
      </Grid>
    </Box>
  );
}
