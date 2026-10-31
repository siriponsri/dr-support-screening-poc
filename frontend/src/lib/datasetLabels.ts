/**
 * Plain clinician wording for dataset readiness reasons and completeness states.
 * Display only: the stored codes and eligibility semantics are unchanged, and an
 * unknown code shows a neutral phrase instead of the raw rule text.
 */
const READINESS_REASONS: Record<string, string> = {
  ELIGIBLE: 'Ready',
  NO_FINAL_CLINICIAN_GRADE: 'No final clinician grade',
  IMAGE_NOT_CONFIRMED: 'Image not confirmed',
  NEEDS_SECOND_REVIEW: 'Needs a second review',
  NEEDS_REVIEW: 'Needs review',
  UNGRADABLE: 'Ungradable',
  QUALITY_REVIEW_REQUIRED: 'Image quality needs review',
  QUEUE_EXCLUDED: 'Excluded',
  EXCLUDED: 'Excluded',
  SOURCE_HASH_MISMATCH: 'Source file changed',
  ADMISSION_UNRESOLVED: 'Image admission not resolved',
  MISSING_PROVENANCE: 'Provenance missing',
  TEST_ONLY_LABEL: 'Test data (not for training)',
  AI_ONLY: 'AI suggestion only, not reviewed',
  AI_ONLY_UNVERIFIED: 'AI suggestion only, not reviewed',
  NO_ANNOTATION_CONFIRMATION: 'Findings not finished',
  NO_EXPLICIT_NEGATIVE_POLICY: 'Not a training negative',
  INVALID_IMAGE: 'Invalid image',
  NON_FUNDUS: 'Not a fundus image',
  DUPLICATE_CONTENT: 'Duplicate image',
  SOURCE_UNAVAILABLE: 'Source file unavailable',
  SOURCE_INTEGRITY_FAILED: 'Source file changed',
  MISSING_SOURCE_IDENTITY: 'Source identity missing',
  REVIEWED_NONE_FOUND_NOT_AUTHORIZED: 'Reviewed, none found (not a training negative)',
};

const COMPLETENESS_STATES: Record<string, string> = {
  NOT_REVIEWED: 'Not reviewed',
  NOT_EVALUATED: 'Not evaluated',
  REVIEWED: 'Reviewed',
  REVIEWED_NONE_FOUND: 'Reviewed, none found',
  NEEDS_REVIEW: 'Needs review',
};

export function readinessReasonLabel(reason: string | null | undefined): string {
  return (reason && READINESS_REASONS[reason]) || 'Needs review';
}

export function completenessLabel(state: string | null | undefined, fallback = 'Not reviewed'): string {
  if (!state) return fallback;
  return COMPLETENESS_STATES[state] || 'Needs review';
}
