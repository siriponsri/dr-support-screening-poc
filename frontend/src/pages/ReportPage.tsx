import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import {
  Alert, AlertIcon, Box, Button, Checkbox, FormControl, FormLabel, Grid, HStack, Input, Radio, RadioGroup,
  SimpleGrid, Stack, Text, Textarea,
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { useAuth } from '@/components/shell/AuthGate';
import { apiJson } from '@/lib/api';

/** The approved A4 screening report. The person who grades chooses Refer or Not refer; the app never picks it. */
type Eye = { quality: string | null; grade: number | null; dme: string | null; signs: string[]; previous_laser: boolean | null; other: string };
type Form = Record<string, unknown> & { right: Eye; left: Eye };
interface ReportState { revision: number; screening_report: { form: Form; status: string } | null }

const SIGNS = ['Microaneurysms', 'Haemorrhages', 'Hard exudates', 'Cotton wool spots', 'Venous beading', 'IRMA', 'New vessels', 'Vitreous haemorrhage'];
const GRADES = ['0 No apparent DR', '1 Mild NPDR', '2 Moderate NPDR', '3 Severe NPDR', '4 PDR'];
const emptyEye = (): Eye => ({ quality: null, grade: null, dme: null, signs: [], previous_laser: null, other: '' });
const emptyForm = (): Form => ({
  patient_name: '', hn: '', age_sex: '', diabetes_type: null, diabetes_years: '', exam_date: '', referring_unit: '',
  screening_site: '', previous_screening: '', camera: null, dilated: null, va_right: '', va_left: '',
  right: emptyEye(), left: emptyEye(), ai_agreement: null, decision: null, rescreen: null, refer_to: null, urgency: null, remarks: '',
});
const TEXT_FIELDS: [string, string][] = [['patient_name', 'Patient name'], ['hn', 'HN'], ['age_sex', 'Age / Sex'],
  ['diabetes_years', 'Diabetes duration (years)'], ['exam_date', 'Exam date'], ['referring_unit', 'Referring clinic / unit'],
  ['screening_site', 'Screening site'], ['previous_screening', 'Previous screening date'], ['va_right', 'Visual acuity RE 6/'],
  ['va_left', 'Visual acuity LE 6/']];

function Choice({ label, value, options, onChange }: { label: string; value: unknown; options: [string, string][]; onChange: (value: string | null) => void }) {
  return (
    <FormControl as="fieldset">
      <FormLabel as="legend" fontSize="sm">{label}</FormLabel>
      <RadioGroup value={value == null ? '' : String(value)} onChange={(next) => onChange(next || null)}>
        <HStack spacing={4} flexWrap="wrap">{options.map(([key, text]) => <Radio key={key} value={key}>{text}</Radio>)}</HStack>
      </RadioGroup>
    </FormControl>
  );
}

function EyePanel({ title, eye, onChange }: { title: string; eye: Eye; onChange: (eye: Eye) => void }) {
  const set = (patch: Partial<Eye>) => onChange({ ...eye, ...patch });
  return (
    <Stack spacing={3} borderWidth="1px" borderColor="border.subtle" borderRadius="md" p={4}>
      <Text fontWeight="semibold">{title}</Text>
      <Choice label="Image quality" value={eye.quality} options={[['GRADABLE', 'Gradable'], ['UNGRADABLE', 'Ungradable']]} onChange={(quality) => set({ quality })} />
      <FormControl as="fieldset">
        <FormLabel as="legend" fontSize="sm">DR grade (ICDR)</FormLabel>
        <RadioGroup value={eye.grade == null ? '' : String(eye.grade)} onChange={(next) => set({ grade: next === '' ? null : Number(next) })}>
          <Stack spacing={1}>{GRADES.map((text, grade) => <Radio key={grade} value={String(grade)}>{text}</Radio>)}</Stack>
        </RadioGroup>
      </FormControl>
      <Choice label="Suspected DME (confirm with OCT)" value={eye.dme} options={[['NO', 'No'], ['SUSPECTED', 'Suspected'], ['CANNOT_ASSESS', 'Cannot assess']]} onChange={(dme) => set({ dme })} />
      <FormControl as="fieldset">
        <FormLabel as="legend" fontSize="sm">Signs seen</FormLabel>
        <SimpleGrid columns={2} spacing={1}>
          {SIGNS.map((sign) => (
            <Checkbox key={sign} isChecked={eye.signs.includes(sign)}
              onChange={(event) => set({ signs: event.target.checked ? [...eye.signs, sign] : eye.signs.filter((item) => item !== sign) })}>{sign}</Checkbox>
          ))}
        </SimpleGrid>
      </FormControl>
      <Choice label="Previous laser" value={eye.previous_laser} options={[['true', 'Yes'], ['false', 'No']]} onChange={(value) => set({ previous_laser: value == null ? null : value === 'true' })} />
      <FormControl><FormLabel fontSize="sm">Other findings</FormLabel><Input value={eye.other} onChange={(event) => set({ other: event.target.value })} /></FormControl>
    </Stack>
  );
}

export function ReportPage() {
  const { pathname } = useLocation();
  const { imageId = '' } = useParams();
  const { user } = useAuth();
  const [form, setForm] = useState<Form>(emptyForm);
  const [revision, setRevision] = useState<number | null>(null);
  const [status, setStatus] = useState('Not started');
  const [reviewer, setReviewer] = useState('');
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const url = `/v1/cases/${encodeURIComponent(imageId)}/screening-report`;

  const load = useCallback(async () => {
    const state = await apiJson<ReportState>(url);
    setRevision(state.revision);
    if (state.screening_report) { setForm({ ...emptyForm(), ...state.screening_report.form }); setStatus(state.screening_report.status); }
  }, [url]);
  useEffect(() => { void load().catch((reason) => setMessage({ tone: 'error', text: reason instanceof Error ? reason.message : 'The report could not be loaded.' })); }, [load]);

  const set = (key: string, value: unknown) => setForm((current) => ({ ...current, [key]: value }));
  const save = async (sign: boolean) => {
    try {
      const reply = await apiJson<ReportState>(url, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision, report: form, sign, reviewer }),
      });
      setRevision(reply.revision); setStatus(reply.screening_report?.status ?? status);
      setMessage({ tone: 'success', text: sign ? 'Report signed.' : 'Report saved.' });
    } catch (reason) {
      setMessage({ tone: 'error', text: reason instanceof Error ? reason.message : 'The report was not saved.' });
    }
  };
  const canSign = !user || ['physician', 'expert', 'admin'].includes(user.role);

  return (
    <Box as="main" maxW="1200px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} subtitle={`Report status: ${status}`} />
      <Stack spacing={5}>
        <Section title="Patient and examination" description="Fill in what you have; only the screening result is needed to sign.">
          <SimpleGrid columns={{ base: 1, tablet: 2, laptop: 4 }} spacing={3}>
            {TEXT_FIELDS.map(([key, label]) => (
              <FormControl key={key}><FormLabel fontSize="sm">{label}</FormLabel>
                <Input value={String(form[key] ?? '')} onChange={(event) => set(key, event.target.value)} /></FormControl>
            ))}
          </SimpleGrid>
          <SimpleGrid columns={{ base: 1, laptop: 3 }} spacing={3} mt={3}>
            <Choice label="Diabetes" value={form.diabetes_type} options={[['TYPE_1', 'Type 1'], ['TYPE_2', 'Type 2'], ['PREGNANCY', 'In pregnancy']]} onChange={(value) => set('diabetes_type', value)} />
            <Choice label="Camera" value={form.camera} options={[['UWF', 'UWF'], ['CFP', 'CFP']]} onChange={(value) => set('camera', value)} />
            <Choice label="Pupils dilated" value={form.dilated} options={[['true', 'Yes'], ['false', 'No']]} onChange={(value) => set('dilated', value == null ? null : value === 'true')} />
          </SimpleGrid>
        </Section>
        <Section title="Retinal findings (ICDR, per eye)">
          <Grid templateColumns={{ base: '1fr', laptop: '1fr 1fr' }} gap={4}>
            <EyePanel title="Right eye (RE)" eye={form.right} onChange={(eye) => set('right', eye)} />
            <EyePanel title="Left eye (LE)" eye={form.left} onChange={(eye) => set('left', eye)} />
          </Grid>
          <Box mt={3}><Choice label="AI suggestion (optional): your grade compared with the AI" value={form.ai_agreement} options={[['AGREED', 'Agreed'], ['CHANGED', 'Changed the grade']]} onChange={(value) => set('ai_agreement', value)} /></Box>
        </Section>
        <Section title="Screening result (based on the worse eye)" description="You choose the result. The app does not decide the referral.">
          <Stack spacing={3}>
            <Choice label="Result" value={form.decision} options={[['NOT_REFER', 'Not refer'], ['REFER', 'Refer'], ['UNGRADABLE', 'Ungradable: re-photograph or refer']]} onChange={(value) => set('decision', value)} />
            {form.decision === 'NOT_REFER' && <Choice label="Rescreen" value={form.rescreen} options={[['ONE_YEAR', 'In 1 year'], ['SIX_TO_TWELVE_MONTHS', 'In 6 to 12 months']]} onChange={(value) => set('rescreen', value)} />}
            {form.decision === 'REFER' && (
              <>
                <Choice label="Refer to" value={form.refer_to} options={[['OPHTHALMOLOGIST', 'Ophthalmologist'], ['RETINA_SPECIALIST', 'Retina specialist']]} onChange={(value) => set('refer_to', value)} />
                <Choice label="Urgency" value={form.urgency} options={[['URGENT', 'Urgent'], ['WITHIN_1_MONTH', 'Within 1 month'], ['WITHIN_3_MONTHS', 'Within 3 months'], ['OTHER', 'Other']]} onChange={(value) => set('urgency', value)} />
              </>
            )}
            <FormControl><FormLabel fontSize="sm">Main findings and remarks</FormLabel>
              <Textarea value={String(form.remarks ?? '')} onChange={(event) => set('remarks', event.target.value)} /></FormControl>
            {!user && <FormControl maxW="360px"><FormLabel fontSize="sm">Your name</FormLabel><Input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></FormControl>}
          </Stack>
        </Section>
        {message && <Alert status={message.tone} py={2}><AlertIcon /><Text fontSize="sm">{message.text}</Text></Alert>}
        <HStack spacing={3} flexWrap="wrap">
          <Button variant="outline" onClick={() => void save(false)} isDisabled={revision == null}>Save draft</Button>
          <Button onClick={() => void save(true)} isDisabled={revision == null || !canSign || !form.decision}>Sign report</Button>
          <Button as="a" href={`${url}/print`} target="_blank" rel="noopener" variant="ghost">Print / Save as PDF</Button>
          <Button as={Link} to={`/review/${encodeURIComponent(imageId)}`} variant="ghost">Back to review</Button>
        </HStack>
        {!canSign && <Text fontSize="sm" color="text.secondary">A nurse prepares the report. A physician signs it.</Text>}
      </Stack>
    </Box>
  );
}
