import { useEffect, useState } from 'react';
import type { CaseRecord } from './api';
import { caseComplete } from './caseProgress';

export interface CaseNeighbors {
  previousId: string | null;
  nextId: string | null;
  /** Next Worklist image after the current one that is not yet complete. */
  nextIncompleteId: string | null;
  position: number | null;
  total: number;
  loading: boolean;
}

export function orderedCases(cases: CaseRecord[], currentId: string): CaseRecord[] {
  const visible = cases.filter((item) => item.queue_state !== 'EXCLUDED' || item.image_id === currentId);
  return [...visible].sort((left, right) => {
    const leftName = left.filename ?? left.display_name;
    const rightName = right.filename ?? right.display_name;
    return leftName.localeCompare(rightName, undefined, { numeric: true, sensitivity: 'base' })
      || left.image_id.localeCompare(right.image_id);
  });
}

/** Worklist order, starting after the current image and wrapping once. */
export function nextIncompleteCaseId(cases: CaseRecord[], currentId: string): string | null {
  const ordered = orderedCases(cases, currentId);
  const index = ordered.findIndex((item) => item.image_id === currentId);
  const rotated = index >= 0 ? [...ordered.slice(index + 1), ...ordered.slice(0, index)] : ordered;
  return rotated.find((item) => item.image_id !== currentId
    && item.queue_state !== 'EXCLUDED'
    && !caseComplete(item))?.image_id ?? null;
}

export async function loadCaseList(): Promise<CaseRecord[]> {
  try {
    const response = await fetch('/v1/cases');
    if (!response.ok) return [];
    const loaded = await response.json() as CaseRecord[];
    return Array.isArray(loaded) ? loaded : [];
  } catch {
    return [];
  }
}

export function useCaseNeighbors(currentId: string | undefined): CaseNeighbors {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(Boolean(currentId));

  useEffect(() => {
    if (!currentId) return;
    let active = true;
    setLoading(true);
    loadCaseList()
      .then((loaded) => { if (active) setCases(loaded); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [currentId]);

  const ordered = currentId ? orderedCases(cases, currentId) : [];
  const index = ordered.findIndex((item) => item.image_id === currentId);
  return {
    previousId: index > 0 ? ordered[index - 1].image_id : null,
    nextId: index >= 0 && index < ordered.length - 1 ? ordered[index + 1].image_id : null,
    nextIncompleteId: currentId ? nextIncompleteCaseId(cases, currentId) : null,
    position: index >= 0 ? index + 1 : null,
    total: ordered.length,
    loading,
  };
}
