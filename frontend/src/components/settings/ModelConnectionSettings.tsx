import { useEffect, useState } from 'react';
import { Alert, AlertIcon, Box, Button, FormControl, FormLabel, HStack, Input, SimpleGrid, Spinner, Stack, Text } from '@chakra-ui/react';
import { CheckCircle2, Save, TestTube2 } from '@/lib/icons';
import { modelConnectionApi, type ModelConnectionModel, type ModelConnectionResponse } from '@/lib/api';
import { Section } from '@/components/common/Section';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';

function statusView(connection: ModelConnectionResponse | null): { label: string; tone: StatusTone } {
  if (!connection || connection.status === 'NOT_CONFIGURED') return { label: 'Manual mode', tone: 'neutral' };
  if (connection.status === 'CONNECTED' && connection.capabilities_ready) return { label: 'Connected', tone: 'success' };
  if (connection.status === 'CONNECTED') return { label: 'Connected; manual mode', tone: 'warning' };
  if (connection.status === 'UNAVAILABLE') return { label: 'Unavailable; manual mode', tone: 'warning' };
  return { label: 'Not verified; manual mode', tone: 'warning' };
}

function taskLabel(task?: string | null): string {
  return task === 'global' ? 'DR grading' : task === 'lesion-roi' ? 'Lesion assistance' : 'Other capability';
}

function modalityLabel(modality: string): string {
  return modality === 'CFP' ? 'CFP' : modality === 'UWF' ? 'UWF' : modality;
}

function ModelCapabilityRow({ model }: { model: ModelConnectionModel }) {
  const modalities = (model.modalities ?? []).map(modalityLabel).join(', ') || 'No image type advertised';
  return (
    <Box borderWidth="1px" borderColor="border.subtle" p={3}>
      <HStack justify="space-between" align="flex-start" spacing={3}>
        <Stack spacing={1} minW={0}>
          <Text fontFamily="mono" fontSize="sm" wordBreak="break-word">{model.model_id}</Text>
          <Text fontSize="xs" color="text.secondary">{taskLabel(model.task)} · {modalities}</Text>
        </Stack>
        <StatusBadge tone={model.ready ? 'success' : 'warning'}>{model.ready ? 'Ready' : 'Unavailable'}</StatusBadge>
      </HStack>
    </Box>
  );
}

export function ModelConnectionSettings() {
  const [connection, setConnection] = useState<ModelConnectionResponse | null>(null);
  const [name, setName] = useState('Model API');
  const [url, setUrl] = useState('');
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<'test' | 'save' | null>(null);
  const [feedback, setFeedback] = useState<{ status: 'info' | 'success' | 'warning' | 'error'; message: string } | null>(null);

  useEffect(() => {
    void modelConnectionApi.get().then((loaded) => {
      setConnection(loaded);
      if (loaded.name) setName(loaded.name);
      if (loaded.url) setUrl(loaded.url);
    }).catch(() => setFeedback({ status: 'warning', message: 'Model connection settings are unavailable.' })).finally(() => setLoading(false));
  }, []);

  const request = () => ({ name: name.trim(), url: url.trim(), ...(token ? { token } : {}) });

  const test = async () => {
    setWorking('test'); setFeedback(null);
    try {
      const result = await modelConnectionApi.test(request());
      setConnection(result);
      setFeedback({ status: result.status === 'CONNECTED' ? 'success' : 'warning', message: result.message });
    } catch { setFeedback({ status: 'warning', message: 'Connection could not be verified.' }); }
    finally { setWorking(null); }
  };

  const save = async () => {
    setWorking('save'); setFeedback(null);
    try {
      const result = await modelConnectionApi.save(request());
      setConnection(result);
      setToken('');
      setFeedback({ status: 'success', message: 'Model connection saved.' });
    } catch { setFeedback({ status: 'warning', message: 'Connection could not be verified. The previous connection is unchanged.' }); }
    finally { setWorking(null); }
  };

  const status = statusView(connection);
  return (
    <Section title="AI Model Connection" description="Optional provider-neutral connection for a hospital LAN GPU server or local GPU API." action={<StatusBadge tone={status.tone}><CheckCircle2 size={11} aria-hidden="true" /> {status.label}</StatusBadge>}>
      {loading ? <HStack color="text.secondary"><Spinner size="sm" /><Text fontSize="sm">Loading connection settings</Text></HStack> : (
        <Stack spacing={4}>
          {feedback && <Alert status={feedback.status}><AlertIcon /><Text fontSize="sm">{feedback.message}</Text></Alert>}
          <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={4}>
            <FormControl isRequired><FormLabel htmlFor="model-connection-name">Connection name</FormLabel><Input id="model-connection-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Model API" /></FormControl>
            <FormControl isRequired><FormLabel htmlFor="model-connection-url">Model API URL</FormLabel><Input id="model-connection-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://model-api.example" inputMode="url" /></FormControl>
          </SimpleGrid>
          <FormControl><FormLabel htmlFor="model-connection-token">Access token (optional)</FormLabel><Input id="model-connection-token" type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder={connection?.token_configured ? 'Token configured; leave blank to keep it' : 'Enter only when required'} autoComplete="new-password" /><Text mt={1} fontSize="xs" color="text.secondary">Stored only by the running backend connection. It is never returned to this page or written to Workspace storage.</Text></FormControl>
          {connection && <Stack spacing={3}>
            <Text fontSize="sm" color="text.secondary">{connection.message}</Text>
            <Alert status={connection.capabilities_ready ? 'success' : 'info'} alignItems="flex-start">
              <AlertIcon />
              <Text fontSize="sm">{connection.capabilities_ready ? 'Compatible model capabilities are available for routing.' : 'Manual review remains available. Model assistance is optional and may be unavailable for the selected image type.'}</Text>
            </Alert>
            {connection.models.length > 0 && <Stack spacing={2}><Text fontSize="sm" fontWeight="semibold">Discovered capabilities</Text>{connection.models.map((model) => <ModelCapabilityRow key={model.model_id} model={model} />)}</Stack>}
          </Stack>}
          <HStack justify="flex-end" spacing={2}>
            <Button variant="outline" leftIcon={<TestTube2 size={15} />} onClick={() => void test()} isLoading={working === 'test'} isDisabled={working !== null || !name.trim() || !url.trim()}>Test connection</Button>
            <Button variant="solid" leftIcon={<Save size={15} />} onClick={() => void save()} isLoading={working === 'save'} isDisabled={working !== null || !name.trim() || !url.trim()}>Save</Button>
          </HStack>
        </Stack>
      )}
    </Section>
  );
}
