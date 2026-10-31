import { useT } from '@/lib/i18n';
import { useEffect, useMemo, useState } from 'react';
import { Alert, AlertIcon, Box, Button, HStack, Progress, SimpleGrid, Stack, Text } from '@chakra-ui/react';
import { useLocation, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { useAuth } from '@/components/shell/AuthGate';
import { apiJson, regularApi, type CaseRecord, type RegularBatch, type RegularStatus } from '@/lib/api';
import { caseComplete, imageContextConfirmed } from '@/lib/caseProgress';
import { ArrowRight, ScanLine } from '@/lib/icons';

export interface TodayCounts {
  total: number;
  toReview: number;
  waitingForAi: number;
  reviewed: number;
  needsAttention: number;
  nextToReview: string | null;
}

/** Plain work counts from the saved cases; nothing here changes a case. */
export function todayCounts(cases: CaseRecord[]): TodayCounts {
  let toReview = 0, waitingForAi = 0, reviewed = 0, needsAttention = 0;
  let nextToReview: string | null = null;
  for (const item of cases) {
    if (!imageContextConfirmed(item)) { needsAttention += 1; continue; }
    if (caseComplete(item)) { reviewed += 1; continue; }
    if (item.global || item.lesion) {
      toReview += 1;
      nextToReview = nextToReview ?? item.image_id;
    } else {
      waitingForAi += 1;
    }
  }
  return { total: cases.length, toReview, waitingForAi, reviewed, needsAttention, nextToReview };
}

function Tile({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <Box bg="surface.panel" borderWidth="1px" borderColor="border.default" borderRadius="md" px={4} py={3}>
      <Text fontSize="sm" color="text.secondary">{label}</Text>
      <Text fontSize="2xl" fontWeight="semibold" lineHeight="1.3">{value}</Text>
      <Text fontSize="xs" color="text.muted">{hint}</Text>
    </Box>
  );
}

/**
 * The physician's start page: what is waiting, what AI is doing, and one
 * button to continue. Counts come from saved cases; AI wording stays
 * "awaiting review" until a clinician confirms.
 */
export function TodayPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const t = useT();
  const { user } = useAuth();
  const [cases, setCases] = useState<CaseRecord[] | null>(null);
  const [status, setStatus] = useState<RegularStatus | null>(null);
  const [batch, setBatch] = useState<RegularBatch | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const loaded = await apiJson<CaseRecord[]>('/v1/cases');
        if (alive) { setCases(loaded); setError(null); }
      } catch (reason) {
        if (alive) setError(reason instanceof Error ? reason.message : 'Cases could not be loaded.');
      }
      try {
        const [nextStatus, batches] = await Promise.all([regularApi.status(), regularApi.batches()]);
        if (alive) { setStatus(nextStatus); setBatch(batches.batches.at(-1) ?? null); }
      } catch {
        if (alive) { setStatus(null); setBatch(null); }   // Not on the shared queue: AI status lives in the header.
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);

  const counts = useMemo(() => todayCounts(cases ?? []), [cases]);
  const settled = batch ? batch.total * 2 - (['grader', 'prism'] as const)
    .reduce((sum, stage) => sum + (batch.counts[stage].PENDING ?? 0) + (batch.counts[stage].RUNNING ?? 0), 0) : 0;

  return (
    <Box as="main" maxW="1200px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader pathname={pathname} subtitle={user ? `Signed in as ${user.username}` : t('Your review work at a glance')} />
      {error && <Alert status="error" mb={4}><AlertIcon /><Text>{error}</Text></Alert>}
      <Stack spacing={5}>
        <SimpleGrid columns={{ base: 2, laptop: 4 }} spacing={3} data-testid="today-tiles">
          <Tile label="To review" value={counts.toReview} hint={t('AI result, awaiting review')} />
          <Tile label="Waiting for AI" value={counts.waitingForAi} hint={t('Confirmed, no AI result yet')} />
          <Tile label="Reviewed" value={counts.reviewed} hint={t('Grade and lesions confirmed')} />
          <Tile label="Needs attention" value={counts.needsAttention} hint={t('Confirm the image first')} />
        </SimpleGrid>
        <HStack spacing={3} flexWrap="wrap">
          <Button leftIcon={<ArrowRight size={16} />} isDisabled={!counts.nextToReview}
            onClick={() => counts.nextToReview && navigate(`/review/${encodeURIComponent(counts.nextToReview)}`)}>
            {t('Continue reviewing')}
          </Button>
          <Button variant="outline" leftIcon={<ScanLine size={16} />} onClick={() => navigate('/worklist')}>{t('Import or confirm images')}</Button>
        </HStack>
        <Section title="AI analysis" description={status
          ? (status.ai_open ? t('The AI server runs from 06:00 to 22:00, Thailand time.') : t('Outside AI hours (06:00 to 22:00, Thailand time). Review and export still work.'))
          : t('AI status is shown at the top right.')}>
          {batch ? (
            <Stack spacing={2} data-testid="today-batch">
              <Progress value={batch.total ? (settled / (batch.total * 2)) * 100 : 0} size="sm" aria-label="AI batch progress" borderRadius="full" />
              <Text fontSize="sm">{batch.complete} of {batch.total} images have both AI results.</Text>
              {status && <Text fontSize="xs" color="text.secondary">Analyses left today: {status.invocations_available ?? 0} of {status.invocations_cap ?? 0}.</Text>}
            </Stack>
          ) : (
            <Text fontSize="sm" color="text.secondary">{t('No AI batch yet. Start one from the Worklist after confirming images.')}</Text>
          )}
        </Section>
      </Stack>
    </Box>
  );
}
