import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Alert, AlertIcon, Badge, Box, Button, HStack, Table, Tbody, Td, Text, Th, Thead, Tr } from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { useAuth } from '@/components/shell/AuthGate';
import { apiJson } from '@/lib/api';
import { useT } from '@/lib/i18n';

/** Signed screening reports where the grader chose Refer; export as FHIR or CSV, or send through the configured connector. */
interface Referral {
  image_id: string; decision: string; refer_to: string | null; urgency: string | null; patient_name: string; hn: string;
  signed_by: string | null; signed_at: string | null; deliveries: { status: string; at: string; connector: string }[];
}

const LABELS: Record<string, string> = {
  REFER: 'Refer', UNGRADABLE: 'Ungradable', OPHTHALMOLOGIST: 'Ophthalmologist', RETINA_SPECIALIST: 'Retina specialist',
  URGENT: 'Urgent', WITHIN_1_MONTH: 'Within 1 month', WITHIN_3_MONTHS: 'Within 3 months', OTHER: 'Other',
};

export function ReferralsPage() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const t = useT();
  const [items, setItems] = useState<Referral[]>([]);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const load = useCallback(async () => setItems((await apiJson<{ items: Referral[] }>('/v1/referrals')).items), []);
  useEffect(() => { void load().catch(() => setMessage({ tone: 'error', text: t('The referral list could not be loaded.') })); }, [load, t]);
  const canSend = !user || ['physician', 'expert', 'admin'].includes(user.role);

  const send = async (imageId: string) => {
    try {
      const attempt = await apiJson<{ status: string }>(`/v1/referrals/${encodeURIComponent(imageId)}/send`, { method: 'POST' });
      setMessage({ tone: attempt.status === 'FAILED' ? 'error' : 'success', text: `${t('Delivery')}: ${attempt.status}` });
      await load();
    } catch (reason) { setMessage({ tone: 'error', text: reason instanceof Error ? reason.message : t('Not sent.') }); }
  };

  return (
    <Box as="main" maxW="1300px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} />
      <Section title="Referrals" description="Only signed screening reports where the grader chose Refer. The app never decides a referral."
        action={<Button as="a" href="/v1/referrals.csv" size="sm" variant="outline">CSV</Button>}>
        {items.length === 0 ? <Text fontSize="sm" color="text.secondary">{t('No signed referrals yet.')}</Text> : (
          <Box overflowX="auto">
            <Table size="sm">
              <Thead><Tr><Th>Patient</Th><Th>HN</Th><Th>Decision</Th><Th>Refer to</Th><Th>Urgency</Th><Th>Signed by</Th><Th>Delivery</Th><Th /></Tr></Thead>
              <Tbody>
                {items.map((item) => {
                  const last = item.deliveries.at(-1);
                  return (
                    <Tr key={item.image_id}>
                      <Td>{item.patient_name || <Text as="span" color="text.secondary">{item.image_id.slice(0, 12)}</Text>}</Td>
                      <Td>{item.hn}</Td>
                      <Td>{LABELS[item.decision] ?? item.decision}</Td>
                      <Td>{item.refer_to ? LABELS[item.refer_to] : ''}</Td>
                      <Td>{item.urgency ? LABELS[item.urgency] : ''}</Td>
                      <Td>{item.signed_by}</Td>
                      <Td>{last ? <Badge colorScheme={last.status === 'FAILED' ? 'red' : 'green'}>{last.status}</Badge> : <Badge>Not sent</Badge>}</Td>
                      <Td>
                        <HStack justify="flex-end" spacing={2}>
                          <Button as="a" size="xs" variant="ghost" href={`/v1/referrals/${encodeURIComponent(item.image_id)}/fhir`} target="_blank" rel="noopener">FHIR</Button>
                          <Button as={Link} size="xs" variant="ghost" to={`/report/${encodeURIComponent(item.image_id)}`}>Report</Button>
                          <Button size="xs" variant="outline" isDisabled={!canSend} onClick={() => void send(item.image_id)}>Send</Button>
                        </HStack>
                      </Td>
                    </Tr>
                  );
                })}
              </Tbody>
            </Table>
          </Box>
        )}
      </Section>
      {message && <Alert status={message.tone} py={2} mt={4}><AlertIcon /><Text fontSize="sm">{message.text}</Text></Alert>}
    </Box>
  );
}
