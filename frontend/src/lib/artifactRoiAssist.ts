import type { CaseRecord } from './api';
import { displayedLesions } from '@/components/review/lesionPresentation';

export function artifactViewCurrent(item: CaseRecord): boolean {
  const view = item.artifact_roi_assist;
  return Boolean(view?.enabled && (view.status === 'READY' || view.status === 'SHADOW_ONLY') && view.binding_sha256
    && view.input_binding?.source_sha256 === item.source_sha256
    && view.input_binding?.image_id === item.image_id
    && view.input_binding?.width === item.width && view.input_binding?.height === item.height);
}

export function annotationAssistLesions(item: CaseRecord, showFiltered = false, failed = false, previewProposals = false) {
  const lesions = displayedLesions(item);
  const shadow = item.artifact_roi_assist?.status === 'SHADOW_ONLY';
  if (failed || !artifactViewCurrent(item) || (shadow && !previewProposals)) return lesions;
  const suppressed = new Set(shadow ? item.artifact_roi_assist?.shadow_proposals?.map((row) => row.detection_id)
    : item.artifact_roi_assist?.suppressed_ids ?? []);
  const protectedIds = new Set((item.review_evidence?.items ?? [])
    .filter((row) => row.status !== 'AI_SUGGESTED')
    .flatMap((row) => [row.annotation_id, row.source_detection_id]));
  const protectedRow = (row: typeof lesions[number]) => row.reviewState === 'CLINICIAN_CORRECTED'
    || Boolean(row.detection_id && protectedIds.has(row.detection_id));
  if (showFiltered) return lesions.map((row) => ({ ...row,
    artifactFiltered: !protectedRow(row) && Boolean(row.detection_id && suppressed.has(row.detection_id)) }));
  // An explicit physician correction is never hidden by an automatic policy.
  return lesions.filter((row) => protectedRow(row)
    || !row.detection_id || !suppressed.has(row.detection_id));
}

/** Count the effective review layer, keeping full raw model output separate. */
export function artifactVisibilityCounts(item: CaseRecord, showFiltered = false, failed = false, previewProposals = false) {
  const reviewSuggestionCount = displayedLesions(item).length;
  const marked = annotationAssistLesions(item, true, failed, previewProposals);
  const shown = showFiltered ? marked : annotationAssistLesions(item, false, failed, previewProposals);
  return {
    rawPredictionCount: item.lesion?.lesions.length ?? item.lesion_review?.raw_count ?? 0,
    reviewSuggestionCount,
    shownCount: shown.length,
    hiddenCount: reviewSuggestionCount - shown.length,
    filteredCount: marked.filter((row) => row.artifactFiltered).length,
  };
}
