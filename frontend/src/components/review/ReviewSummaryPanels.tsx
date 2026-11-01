/** Read-only summary panels shown on the Review page. */
import { Alert, AlertIcon, Badge, Box, Heading, HStack, Stack, Text } from '@chakra-ui/react';
import { StatusBadge } from '@/components/common/StatusBadge';
import { LESION_COLORS } from '@/components/review/RetinalCanvas';
import { drGradeLabel, type CaseRecord } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { clinicianResultState, LESION_DISPLAY_LABELS, modelDisplayName } from './reviewCaseLabels';

export function ResultWarnings({ item }: { item: CaseRecord }) {
  const t = useT();
  const warnings = [...(item.global?.warnings ?? []), ...(item.lesion?.warnings ?? [])];
  if (warnings.length === 0) return null;
  return (
    <Alert status="warning" mt={4}>
      <AlertIcon />
      <Stack spacing={1}>
        <Text fontWeight="semibold">{t('Model notes available')}</Text>
        <Text fontSize="sm">{t('Technical model notes are available in Models & Audit. Review remains available; confirm the image and human decision.')}</Text>
      </Stack>
    </Alert>
  );
}

export function Assessment({ item }: { item: CaseRecord }) {
  const t = useT();
  if (!item.global) return <Text color="text.secondary">{t('Not analyzed')}</Text>;
  return (
    <Stack spacing={3}>
      <HStack justify="space-between" align="flex-start">
        <Stack spacing={1}>
          <Text fontSize="sm" color="text.secondary">{t('System-predicted DR grade')}</Text>
          <Heading size="lg">{item.global.grade === null ? t(clinicianResultState(item.global.state)) : (drGradeLabel(item.global.grade) ?? t('Grade available'))}</Heading>
        </Stack>
      <StatusBadge tone={item.global.state === 'AI_SUGGESTION' ? 'info' : 'warning'}>{clinicianResultState(item.global.state)}</StatusBadge>
      </HStack>
      {item.global.confidence !== null && (
        <HStack justify="space-between">
          <Text color="text.secondary">{t('Top model score')}</Text>
          <Text fontWeight="semibold">{(item.global.confidence * 100).toFixed(1)}%</Text>
        </HStack>
      )}
      <Text fontSize="xs" color="text.muted">AI: {modelDisplayName(item.global.model_id)}</Text>
    </Stack>
  );
}

export function LesionSuggestions({ item }: { item: CaseRecord }) {
  const t = useT();
  if (!item.lesion) return <Text color="text.secondary">{t('Not analyzed')}</Text>;
  if (item.lesion.state === 'UNSUPPORTED') return <Text color="status.warning">{t('Lesion assistance is unavailable for this image. Continue with manual review.')}</Text>;
  const lesions = item.lesion.lesions;
  const counts = lesions.reduce<Record<string, number>>((result, lesion) => {
    result[lesion.canonical_label] = (result[lesion.canonical_label] ?? 0) + 1;
    return result;
  }, {});
  return (
    <Stack spacing={3}>
      <HStack justify="space-between">
        <Text color="text.secondary">{t('AI lesion suggestions')}</Text>
        <Text fontWeight="semibold">{lesions.length}</Text>
      </HStack>
      <Stack spacing={2}>
        <Text fontSize="sm" color="text.secondary">{t('Suggested classes')}</Text>
        {Object.keys(counts).length ? Object.entries(counts).map(([label, count]) => (
          <HStack key={label} justify="space-between"><Text>{LESION_DISPLAY_LABELS[label] ?? label.replace(/_/g, ' ')}</Text><Badge variant="info">{count}</Badge></HStack>
        )) : <Text color="text.secondary">{t('No AI regions returned. This does not establish absence of lesions.')}</Text>}
      </Stack>
      <Text fontSize="xs" color="text.muted">{t('Raw AI suggestions by class. Optional visual assistance; no per-detection action is required.')}</Text>
      <Text fontSize="xs" color="text.muted">AI: {modelDisplayName(item.lesion.model_id)}</Text>
    </Stack>
  );
}

export function LesionLegend() {
  return (
    <HStack spacing={3} flexWrap="wrap" fontSize="xs" color="text.secondary">
      {Object.entries(LESION_COLORS).map(([label, color]) => (
        <HStack key={label} spacing={1}>
          <Box w="9px" h="9px" borderRadius="sm" bg={color} />
          <Text>{LESION_DISPLAY_LABELS[label] ?? label.replace(/_/g, ' ')}</Text>
        </HStack>
      ))}
    </HStack>
  );
}

export function MaskLegend() {
  const t = useT();
  return (
    <Stack spacing={1} aria-label="Mask preview key">
      <Text fontSize="xs" fontWeight="semibold" color="text.primary">{t('Mask preview key')}</Text>
      <HStack spacing={3} flexWrap="wrap" fontSize="xs" color="text.secondary">
        <HStack spacing={1}>
          <Box w="9px" h="9px" borderRadius="sm" bg="#127E6A" />
          <Text>{t('Retained retinal area')}</Text>
        </HStack>
        <HStack spacing={1}>
          <Box w="9px" h="9px" borderRadius="sm" bg="#344054" />
          <Text>{t('Excluded border / artifact area')}</Text>
        </HStack>
        <HStack spacing={1}>
          <Box w="9px" h="9px" borderWidth="2px" borderColor="#14585C" borderRadius="sm" />
          <Text>{t('Mask boundary (retained / excluded edge)')}</Text>
        </HStack>
      </HStack>
    </Stack>
  );
}

export function ReviewContextStatus({ item }: { item: CaseRecord }) {
  const t = useT();
  const messages = [
    item.resolver_ui?.action_required ? 'Patient and eye context needs confirmation.' : null,
    item.admission_ui?.action_required ? 'Image context needs confirmation.' : null,
  ].filter((message): message is string => Boolean(message));
  if (messages.length === 0) return null;
  return (
    <Alert status="warning" variant="subtle" py={2} px={3} alignItems="flex-start">
      <AlertIcon />
      <Text fontSize="sm">{messages.map((message) => t(message)).join(' ')}</Text>
    </Alert>
  );
}
