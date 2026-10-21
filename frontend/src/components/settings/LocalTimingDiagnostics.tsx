import { useState } from 'react';
import { Button, Checkbox, HStack, Select, Stack, Text } from '@chakra-ui/react';
import { Section } from '@/components/common/Section';
import { localTiming, type TimingConfig } from '@/lib/localTiming';

export function LocalTimingDiagnostics() {
  const [enabled, setEnabled] = useState(localTiming.enabled);
  const [config, setConfig] = useState<TimingConfig>(localTiming.configuration());
  const [notice, setNotice] = useState('');
  const update = (next: TimingConfig) => { setConfig(next); localTiming.configure(enabled, next); };
  const download = () => {
    const data = new Blob([JSON.stringify(localTiming.export(), null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(data);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = 'local-ux-timing.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
    setNotice('Downloaded local diagnostics. No data was sent to an analytics service.');
  };
  return <Section title="Local workflow timing" description="Optional diagnostics for IT and supervised usability studies. Off by default; memory only until this tab closes or you clear it.">
    <Stack spacing={3}>
      <Checkbox isChecked={enabled} onChange={(event) => { setEnabled(event.target.checked); localTiming.configure(event.target.checked, config); }}>Record local workflow timings</Checkbox>
      <HStack flexWrap="wrap">
        <Select aria-label="Timing observation cohort" value={config.cohort} onChange={(event) => update({ ...config, cohort: event.target.value as TimingConfig['cohort'] })}>
          <option value="UNSPECIFIED">Observation not classified</option><option value="SYNTHETIC_AUTOMATION">Synthetic automation</option><option value="OBSERVED_USER">Supervised user observation</option>
        </Select>
        <Select aria-label="Timing environment" value={config.environment} onChange={(event) => update({ ...config, environment: event.target.value as TimingConfig['environment'] })}>
          <option value="UNKNOWN">Environment unknown</option><option value="LOCAL_APP_QA_MODEL">Local app / QA models</option><option value="HOSPITAL_LOCAL">Hospital local</option><option value="LIGHTNING">Lightning</option>
        </Select>
        <Select aria-label="Timing load phase" value={config.phase} onChange={(event) => update({ ...config, phase: event.target.value as TimingConfig['phase'] })}>
          <option value="UNKNOWN">Load phase not verified</option><option value="COLD">Cold (operator classified)</option><option value="WARM">Warm (operator classified)</option>
        </Select>
      </HStack>
      <Text fontSize="sm">No patient names, source identifiers, filenames, images, remarks or request content are recorded. Activity means a visible focused tab within 30 seconds of an input event; it does not measure clinical thought or prove review. Missing backend/network components stay unknown. Labels above describe the observation; they do not verify hardware or model warmup.</Text>
      <HStack flexWrap="wrap"><Button variant="outline" onClick={download}>Download local timing JSON</Button><Button variant="outline" onClick={() => { localTiming.clear(); setNotice('Local timing observations cleared.'); }}>Clear local timings</Button></HStack>
      {notice && <Text role="status" fontSize="sm">{notice}</Text>}
    </Stack>
  </Section>;
}
