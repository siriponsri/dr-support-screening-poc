import type { CaseRecord } from './api';

/**
 * Clinician-facing progress helpers for the single-line review flow.
 *
 * These summarize existing persisted fields; they do not redefine dataset
 * readiness. DR-grade readiness and lesion readiness stay separate in the
 * backend and dataset export.
 */
export function imageContextConfirmed(item: Pick<CaseRecord, 'admission_history'>): boolean {
  return (item.admission_history ?? []).some((event) => event.action === 'CONFIRM_IMAGE');
}

export function gradeConfirmed(item: Pick<CaseRecord, 'clinician_review'> | null | undefined): boolean {
  const grade = item?.clinician_review?.final_grade;
  return grade !== null && grade !== undefined;
}

export function annotationsConfirmed(item: Pick<CaseRecord, 'annotation_confirmation_status'> | null | undefined): boolean {
  return item?.annotation_confirmation_status === 'CONFIRMED';
}

/** Both human milestones after Confirm Image are current for this image. */
export function caseComplete(item: Pick<CaseRecord, 'clinician_review' | 'annotation_confirmation_status'> | null | undefined): boolean {
  return gradeConfirmed(item) && annotationsConfirmed(item);
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
