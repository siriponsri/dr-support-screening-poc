import type { CaseRecord, Laterality } from '@/lib/api';

export type ViewMode = 'cases' | 'patients';
export type ReadinessFilter = 'all' | 'identity' | 'image' | 'ready';
export type ReviewFilter = 'all' | 'pending' | 'reviewed' | 'excluded';
export type AiFilter = 'all' | 'analyzed' | 'not-analyzed' | 'unavailable';
export type SortOption = 'filename' | 'patient-eye' | 'review' | 'recent';

export interface WorklistFilters {
  readiness: ReadinessFilter;
  review: ReviewFilter;
  ai: AiFilter;
}

export interface PatientEyeGroup {
  laterality: Laterality;
  label: string;
  cases: CaseRecord[];
}

export interface PatientGroup {
  key: string | null;
  label: string;
  eyes: PatientEyeGroup[];
}

export const DEFAULT_FILTERS: WorklistFilters = {
  readiness: 'all',
  review: 'all',
  ai: 'all',
};

const LATERALITY_ORDER: Record<Laterality, number> = { LEFT: 0, RIGHT: 1, UNKNOWN: 2 };

export function identityNeedsAction(item: CaseRecord): boolean {
  if (item.resolver_ui) {
    return item.resolver_ui.patient.action_required || item.resolver_ui.laterality.action_required;
  }
  return !item.patient_key || !item.laterality;
}

export function imageNeedsAction(item: CaseRecord): boolean {
  return Boolean(item.admission_ui?.action_required);
}

export function caseNeedsAttention(item: CaseRecord): boolean {
  return identityNeedsAction(item) || imageNeedsAction(item);
}

export type AiState = 'analyzed' | 'not-analyzed' | 'unavailable';

export function aiState(item: CaseRecord): AiState {
  if (item.admission_ui?.label === 'Cannot analyze') return 'unavailable';
  if (item.global || item.lesion) return 'analyzed';
  return 'not-analyzed';
}

export type ReviewState = 'pending' | 'reviewed' | 'needs-annotation' | 'escalated' | 'excluded';

export function reviewState(item: CaseRecord): ReviewState {
  if (item.queue_state === 'EXCLUDED') return 'excluded';
  if (item.state === 'REVIEWED') return 'reviewed';
  if (item.state === 'NEEDS_CORRECTION') return 'needs-annotation';
  if (item.state === 'ESCALATED') return 'escalated';
  return 'pending';
}

export function reviewStateLabel(state: ReviewState): string {
  switch (state) {
    case 'reviewed': return 'Reviewed';
    case 'needs-annotation': return 'Needs annotation';
    case 'escalated': return 'Escalated';
    case 'excluded': return 'Excluded';
    default: return 'Pending review';
  }
}

function matchesReviewFilter(item: CaseRecord, filter: ReviewFilter): boolean {
  const state = reviewState(item);
  if (filter === 'all') return true;
  if (filter === 'pending') return state !== 'reviewed' && state !== 'excluded';
  return state === filter;
}

function displayFilename(item: CaseRecord): string {
  return item.filename || item.display_name;
}

function latestUpdatedAt(item: CaseRecord): string {
  const timestamps = [
    item.admission?.updated_at,
    item.clinician_review?.timestamp,
    ...(item.events ?? []).map((event) => typeof event.timestamp === 'string' ? event.timestamp : null),
    ...(item.queue_history ?? []).map((event) => typeof event.timestamp === 'string' ? event.timestamp : null),
    ...(item.resolution_history ?? []).map((event) => typeof event.timestamp === 'string' ? event.timestamp : null),
  ].filter((value): value is string => Boolean(value));
  return timestamps.sort().at(-1) ?? '';
}

function patientSortKey(item: CaseRecord): string {
  return item.patient_key ? `0-${item.patient_key}` : '1-unlinked';
}

function compareText(left: string, right: string): number {
  return left.localeCompare(right, undefined, { numeric: true, sensitivity: 'base' });
}

export function compareCases(left: CaseRecord, right: CaseRecord, sort: SortOption): number {
  let result = 0;
  if (sort === 'patient-eye') {
    result = compareText(patientSortKey(left), patientSortKey(right));
    if (result === 0) {
      result = LATERALITY_ORDER[left.laterality ?? 'UNKNOWN'] - LATERALITY_ORDER[right.laterality ?? 'UNKNOWN'];
    }
  } else if (sort === 'review') {
    const order: Record<ReviewState, number> = {
      pending: 0,
      'needs-annotation': 1,
      escalated: 2,
      reviewed: 3,
      excluded: 4,
    };
    result = order[reviewState(left)] - order[reviewState(right)];
  } else if (sort === 'recent') {
    result = compareText(latestUpdatedAt(right), latestUpdatedAt(left));
  } else {
    result = compareText(displayFilename(left), displayFilename(right));
  }

  if (result !== 0) return result;
  result = compareText(displayFilename(left), displayFilename(right));
  return result !== 0 ? result : compareText(left.image_id, right.image_id);
}

export function sortCases(cases: CaseRecord[], sort: SortOption): CaseRecord[] {
  return [...cases].sort((left, right) => compareCases(left, right, sort));
}

export function matchesSearch(item: CaseRecord, search: string): boolean {
  const query = search.trim().toLocaleLowerCase();
  if (!query) return true;
  return [item.filename, item.display_name, item.patient_key]
    .filter((value): value is string => Boolean(value))
    .some((value) => value.toLocaleLowerCase().includes(query));
}

export function matchesFilters(item: CaseRecord, filters: WorklistFilters): boolean {
  if (filters.readiness === 'identity' && !identityNeedsAction(item)) return false;
  if (filters.readiness === 'image' && !imageNeedsAction(item)) return false;
  if (filters.readiness === 'ready' && caseNeedsAttention(item)) return false;
  if (!matchesReviewFilter(item, filters.review)) return false;
  if (filters.ai !== 'all' && aiState(item) !== filters.ai) return false;
  return true;
}

export function filterCases(cases: CaseRecord[], search: string, filters: WorklistFilters): CaseRecord[] {
  return cases.filter((item) => matchesSearch(item, search) && matchesFilters(item, filters));
}

function lateralityLabel(laterality: Laterality): string {
  if (laterality === 'LEFT') return 'Left';
  if (laterality === 'RIGHT') return 'Right';
  return 'Eye not confirmed';
}

export function groupCases(cases: CaseRecord[]): PatientGroup[] {
  const grouped = new Map<string, PatientGroup>();
  for (const item of cases) {
    const key = item.patient_key ?? null;
    const groupKey = key ?? '__unlinked__';
    let group = grouped.get(groupKey);
    if (!group) {
      group = { key, label: key ?? 'Patient not linked', eyes: [] };
      grouped.set(groupKey, group);
    }
    const laterality = item.laterality ?? 'UNKNOWN';
    let eye = group.eyes.find((candidate) => candidate.laterality === laterality);
    if (!eye) {
      eye = { laterality, label: lateralityLabel(laterality), cases: [] };
      group.eyes.push(eye);
    }
    eye.cases.push(item);
  }

  return [...grouped.values()]
    .sort((left, right) => {
      if (!left.key) return 1;
      if (!right.key) return -1;
      return compareText(left.key, right.key);
    })
    .map((group) => ({
      ...group,
      eyes: [...group.eyes].sort((left, right) => LATERALITY_ORDER[left.laterality] - LATERALITY_ORDER[right.laterality]),
    }));
}
