import { useState } from 'react';
import {
  Box,
  Button,
  Code,
  FormControl,
  FormLabel,
  HStack,
  Input,
  Select,
  SimpleGrid,
  Stack,
  Text,
} from '@chakra-ui/react';
import { Section } from '@/components/common/Section';
import { StatusBadge, type StatusTone } from '@/components/common/StatusBadge';
import {
  lesionReviewApi,
  type CaseRecord,
  type LesionLabel,
  type ReviewEvidenceItem,
} from '@/lib/api';

const LABELS: Array<{ value: LesionLabel; label: string }> = [
  { value: 'MICROANEURYSM', label: 'Microaneurysm' },
  { value: 'HEMORRHAGE', label: 'Hemorrhage' },
  { value: 'HARD_EXUDATE', label: 'Hard exudate' },
  { value: 'SOFT_EXUDATE', label: 'Soft exudate' },
];

function displayLabel(label: string | null) {
  return LABELS.find((option) => option.value === label)?.label ?? label ?? 'Annotation';
}

function shortLabel(label: string | null) {
  return label === 'MICROANEURYSM' ? 'MA'
    : label === 'HEMORRHAGE' ? 'HE'
      : label === 'HARD_EXUDATE' ? 'EX'
        : label === 'SOFT_EXUDATE' ? 'SE' : 'ROI';
}

function statusText(status: ReviewEvidenceItem['status']) {
  return {
    AI_SUGGESTED: 'AI suggested',
    CLINICIAN_CONFIRMED: 'Clinician confirmed',
    CLINICIAN_REMOVED: 'Clinician removed',
    CLINICIAN_ADDED: 'Clinician added',
    LABEL_CHANGED: 'Label changed',
    GEOMETRY_CHANGED: 'Geometry changed',
    CORRECTED: 'Corrected',
  }[status];
}

function statusTone(status: ReviewEvidenceItem['status']): StatusTone {
  if (status === 'CLINICIAN_CONFIRMED' || status === 'CLINICIAN_ADDED') return 'success';
  if (status === 'CLINICIAN_REMOVED') return 'danger';
  if (status === 'LABEL_CHANGED' || status === 'GEOMETRY_CHANGED' || status === 'CORRECTED') return 'warning';
  return 'info';
}

function scoreText(score: number | null) {
  return score === null ? null : score.toFixed(2);
}

interface ReviewEvidencePanelProps {
  item: CaseRecord;
  selectedLesionId?: string | null;
  onSelectLesion?: (detectionId: string) => void;
  onSaved: (item: CaseRecord) => void;
}

export function ReviewEvidencePanel({ item, selectedLesionId, onSelectLesion, onSaved }: ReviewEvidencePanelProps) {
  const evidence = item.review_evidence;
  const aiItems = (evidence?.items ?? []).filter((entry) => entry.source === 'AI');
  const [reviewer, setReviewer] = useState(evidence?.reviewer ?? '');
  const [focusedId, setFocusedId] = useState<string | null>(selectedLesionId ?? null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [correctionLabel, setCorrectionLabel] = useState<LesionLabel>('MICROANEURYSM');
  const [correctionRectangle, setCorrectionRectangle] = useState<[string, string, string, string]>(['', '', '', '']);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const focusedLesionId = selectedLesionId ?? focusedId;
  const focusedEntry = aiItems.find((entry) => entry.annotation_id === focusedLesionId) ?? null;

  const selectLesion = (detectionId: string) => {
    setFocusedId(detectionId);
    onSelectLesion?.(detectionId);
    setActiveId(null);
    setError(null);
    setSaved(null);
  };

  const beginCorrection = (entry: ReviewEvidenceItem) => {
    const rectangle = entry.corrected_rectangle ?? entry.original_rectangle;
    setActiveId(entry.annotation_id);
    setCorrectionLabel((entry.corrected_label ?? entry.label ?? 'MICROANEURYSM') as LesionLabel);
    setCorrectionRectangle(rectangle ? rectangle.map((value) => String(value)) as [string, string, string, string] : ['', '', '', '']);
    setError(null);
    setSaved(null);
  };

  const submit = async (entry: ReviewEvidenceItem, action: 'CONFIRM' | 'REJECT' | 'CORRECT') => {
    if (!entry.annotation_id || saving) return;
    if (!reviewer.trim()) {
      setError('Reviewer name is required before recording review evidence.');
      return;
    }
    const values = correctionRectangle.map(Number);
    if (action === 'CORRECT' && values.some((value) => !Number.isFinite(value))) {
      setError('Enter four finite coordinates before saving a correction.');
      return;
    }
    setSaving(true);
    setError(null);
    setSaved(null);
    try {
      const savedCase = await lesionReviewApi.review(item.image_id, {
        revision: item.revision,
        reviewer: reviewer.trim(),
        detection_id: entry.annotation_id,
        action,
        label: action === 'CORRECT' ? correctionLabel : undefined,
        rectangle: action === 'CORRECT' ? values as [number, number, number, number] : undefined,
      });
      onSaved(savedCase);
      setActiveId(null);
      setSaved(action === 'CONFIRM' ? 'AI suggestion confirmed.' : action === 'REJECT' ? 'AI suggestion marked removed.' : 'AI suggestion correction saved.');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The review evidence could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Section title="PRISM evidence" description="Optional visual evidence for clinician inspection. Review completion is recorded separately from individual detections.">
      {!evidence ? <Text color="text.secondary">No review evidence is available yet.</Text> : (
        <Stack spacing={4} minW={0}>
          <SimpleGrid columns={{ base: 2, tablet: 4 }} spacing={2}>
            {[
              ['Confirmed', evidence.summary.confirmed],
              ['Added', evidence.summary.added],
              ['Removed', evidence.summary.removed],
              ['Corrected', evidence.summary.corrected],
            ].map(([label, value]) => (
              <Box key={label} borderWidth="1px" borderColor="border.subtle" borderRadius="md" px={3} py={2}>
                <Text fontSize="xs" color="text.secondary">{label}</Text>
                <Text fontSize="lg" fontWeight="semibold" sx={{ fontVariantNumeric: 'tabular-nums' }}>{value}</Text>
              </Box>
            ))}
          </SimpleGrid>
          <HStack justify="space-between" align="flex-start" flexWrap="wrap" gap={2} minW={0}>
            <Text fontSize="sm"><strong>Evidence status:</strong> {evidence.status}</Text>
            <Text fontSize="sm" color="text.secondary">{aiItems.length} AI detection{aiItems.length === 1 ? '' : 's'} available for inspection</Text>
          </HStack>
          {error && <Text role="alert" color="status.danger" fontSize="sm">{error}</Text>}
          {saved && <Text role="status" color="status.success" fontSize="sm">{saved}</Text>}
          {aiItems.length === 0 ? <Text color="text.secondary">No AI lesion suggestions are available.</Text> : (
            <Stack spacing={2}>
              {aiItems.map((entry) => {
                const selected = focusedLesionId === entry.annotation_id;
                return (
                  <Box key={entry.annotation_id} borderWidth="1px" borderColor={selected ? 'border.focus' : 'border.subtle'} borderRadius="md" p={2} minW={0}>
                    <HStack justify="space-between" align="flex-start" gap={3} minW={0}>
                      <Button
                        variant="ghost"
                        size="sm"
                        flex={1}
                        minW={0}
                        justifyContent="flex-start"
                        whiteSpace="normal"
                        textAlign="left"
                        onClick={() => entry.annotation_id && selectLesion(entry.annotation_id)}
                        aria-pressed={selected}
                        title={`Inspect ${displayLabel(entry.label)} AI detection`}
                      >
                        <Stack spacing={0} align="flex-start" minW={0}>
                          <Text fontWeight="semibold">{shortLabel(entry.label)}{entry.score !== null ? ` · ${scoreText(entry.score)}` : ''}</Text>
                          <Text fontSize="xs" color="text.secondary" noOfLines={1}>{displayLabel(entry.label)} · AI visual evidence</Text>
                        </Stack>
                      </Button>
                      <StatusBadge tone={statusTone(entry.status)}>{statusText(entry.status)}</StatusBadge>
                    </HStack>
                  </Box>
                );
              })}
            </Stack>
          )}
          {focusedEntry && (
            <Box borderTopWidth="1px" borderColor="border.subtle" pt={3} minW={0}>
              <Stack spacing={2}>
                <Text fontSize="sm" fontWeight="semibold">Optional action for {shortLabel(focusedEntry.label)} · {scoreText(focusedEntry.score)}</Text>
                <Text fontSize="xs" color="text.secondary">Use these actions only when this suggestion needs a recorded clinician change. Other detections can remain visual evidence.</Text>
                <FormControl maxW={{ base: '100%', tablet: '280px' }}>
                  <FormLabel fontSize="sm">Reviewer for optional action</FormLabel>
                  <Input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Enter reviewer name" />
                </FormControl>
                {focusedEntry.status === 'AI_SUGGESTED' && !activeId && (
                  <HStack spacing={2} flexWrap="wrap">
                    <Button size="sm" variant="secondary" onClick={() => void submit(focusedEntry, 'CONFIRM')} isLoading={saving}>Confirm</Button>
                    <Button size="sm" variant="danger" onClick={() => void submit(focusedEntry, 'REJECT')} isLoading={saving}>Remove</Button>
                    <Button size="sm" variant="outline" onClick={() => beginCorrection(focusedEntry)} isDisabled={saving}>Edit</Button>
                  </HStack>
                )}
                {focusedEntry.status !== 'AI_SUGGESTED' && !activeId && <Text fontSize="sm" color="text.secondary">This suggestion already has a recorded action.</Text>}
                {activeId === focusedEntry.annotation_id && (
                  <Stack spacing={2} borderTopWidth="1px" borderColor="border.subtle" pt={3}>
                    <FormControl>
                      <FormLabel fontSize="sm">Edited label</FormLabel>
                      <Select size="sm" value={correctionLabel} onChange={(event) => setCorrectionLabel(event.target.value as LesionLabel)}>
                        {LABELS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </Select>
                    </FormControl>
                    <FormControl>
                      <FormLabel fontSize="sm">Edited rectangle (original pixels: x1, y1, x2, y2)</FormLabel>
                      <SimpleGrid columns={{ base: 2, tablet: 4 }} spacing={2}>
                        {correctionRectangle.map((value, index) => <Input key={index} size="sm" type="number" value={value} aria-label={`Edited coordinate ${index + 1}`} onChange={(event) => setCorrectionRectangle((current) => current.map((part, currentIndex) => currentIndex === index ? event.target.value : part) as [string, string, string, string])} />)}
                      </SimpleGrid>
                    </FormControl>
                    <HStack>
                      <Button size="sm" variant="solid" onClick={() => void submit(focusedEntry, 'CORRECT')} isLoading={saving}>Save edit</Button>
                      <Button size="sm" variant="ghost" onClick={() => setActiveId(null)} isDisabled={saving}>Cancel</Button>
                    </HStack>
                  </Stack>
                )}
                {focusedEntry.model_id && <Text fontSize="xs" color="text.muted">Model: {focusedEntry.model_id} - {focusedEntry.model_version}</Text>}
              </Stack>
            </Box>
          )}
          <Box borderTopWidth="1px" borderColor="border.subtle" pt={3}>
            <Text fontSize="xs" color="text.secondary">Technical details</Text>
            <Stack spacing={1} mt={1} fontSize="xs" color="text.muted">
              <Text>Source: AI lesion detection; model output and confidence remain unchanged.</Text>
              {evidence.source_sha256 && <Text>Source SHA-256: <Code fontSize="xs">{evidence.source_sha256}</Code></Text>}
              {evidence.analysis_sha256 && <Text>Analysis SHA-256: <Code fontSize="xs">{evidence.analysis_sha256}</Code></Text>}
            </Stack>
          </Box>
          <Text fontSize="xs" color="text.muted">{evidence.note}</Text>
        </Stack>
      )}
    </Section>
  );
}
