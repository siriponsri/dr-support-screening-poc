import type { CaseRecord, Lesion, LesionLabel, ReviewEvidenceItem } from '@/lib/api';

export interface DisplayedLesion extends Lesion {
  displayScore: number | null;
  reviewState: 'AI_SUGGESTION' | 'CLINICIAN_CORRECTED';
  originalLabel?: LesionLabel;
  originalScore?: number;
}

function isLabel(value: string | null | undefined): value is LesionLabel {
  return value === 'MICROANEURYSM'
    || value === 'HEMORRHAGE'
    || value === 'HARD_EXUDATE'
    || value === 'SOFT_EXUDATE';
}

function sourceLabel(label: LesionLabel): string {
  return label === 'MICROANEURYSM' ? 'MA'
    : label === 'HEMORRHAGE' ? 'HE'
      : label === 'HARD_EXUDATE' ? 'EX' : 'SE';
}

function evidenceByDetection(item: CaseRecord): Map<string, ReviewEvidenceItem> {
  return new Map(
    (item.review_evidence?.items ?? [])
      .filter((entry) => entry.source === 'AI' && entry.annotation_id)
      .map((entry) => [entry.annotation_id as string, entry]),
  );
}

/** Derive the active visual layer without mutating raw model output. */
export function displayedLesions(item: CaseRecord): DisplayedLesion[] {
  const evidence = evidenceByDetection(item);
  const raw = item.lesion_review?.lesions ?? item.lesion?.lesions ?? [];

  return raw.flatMap((lesion) => {
    const detectionId = lesion.detection_id;
    const entry = detectionId ? evidence.get(detectionId) : undefined;
    if (entry?.status === 'CLINICIAN_REMOVED') return [];

    const correctedLabel = isLabel(entry?.corrected_label) && entry.corrected_label !== lesion.canonical_label
      ? entry.corrected_label
      : null;
    const correctedRectangle = entry?.corrected_rectangle?.length === 4
      ? entry.corrected_rectangle as [number, number, number, number]
      : null;
    return [{
      ...lesion,
      rectangle: correctedRectangle ?? lesion.rectangle,
      canonical_label: correctedLabel ?? lesion.canonical_label,
      source_label: correctedLabel ? sourceLabel(correctedLabel) : lesion.source_label,
      displayScore: correctedLabel ? null : lesion.score,
      reviewState: correctedLabel || entry?.status === 'LABEL_CHANGED' ? 'CLINICIAN_CORRECTED' : 'AI_SUGGESTION',
      originalLabel: correctedLabel ? lesion.canonical_label as LesionLabel : undefined,
      originalScore: correctedLabel ? lesion.score : undefined,
    }];
  });
}

export function aiEvidenceForLesion(item: CaseRecord, detectionId: string | null | undefined) {
  if (!detectionId) return null;
  return (item.review_evidence?.items ?? []).find(
    (entry) => entry.source === 'AI' && entry.annotation_id === detectionId,
  ) ?? null;
}
