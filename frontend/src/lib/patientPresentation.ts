import type { CaseRecord } from '@/lib/api';

export function hasInternalPatientKey(item: CaseRecord): boolean {
  return item.source_origin === 'HOSPITAL_AUTHORIZED'
    || Boolean(item.patient_key?.startsWith('HOSPITAL-'));
}

/** Presentation only: grouping and API writes must keep the original key. */
export function patientLabel(item: CaseRecord): string {
  if (hasInternalPatientKey(item)) return item.patient_display_label ?? (item.patient_key ? 'Patient linked' : 'Patient not linked');
  return item.patient_key ?? item.patient_candidate ?? item.resolver_ui?.patient.candidate ?? 'Patient not linked';
}
