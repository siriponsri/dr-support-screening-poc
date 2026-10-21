import { useEffect, useState } from 'react';
import { apiJson, type CaseRecord } from './api';
import { caseComplete, imageContextConfirmed } from './caseProgress';

export interface CaseNeighbors {
  previousId: string | null;
  nextId: string | null;
  previousImageConfirmed: boolean;
  nextImageConfirmed: boolean;
  /** Next Worklist image after the current one that is not yet complete. */
  nextIncompleteId: string | null;
  position: number | null;
  total: number;
  loading: boolean;
  error: string | null;
  retry: () => void;
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
  const loaded = await apiJson<CaseRecord[]>('/v1/cases');
  if (!Array.isArray(loaded)) throw new Error('The Worklist could not be loaded. Try again.');
  return loaded;
}

export function useCaseNeighbors(currentId: string | undefined): CaseNeighbors {
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(Boolean(currentId));

  useEffect(() => {
    if (!currentId) return;
    let active = true;
    setLoading(true);
    setError(null);
    loadCaseList()
      .then((loaded) => { if (active) setCases(loaded); })
      .catch(() => { if (active) { setCases([]); setError('Worklist unavailable'); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [currentId, attempt]);

  const ordered = currentId ? orderedCases(cases, currentId) : [];
  const index = ordered.findIndex((item) => item.image_id === currentId);
  return {
    previousId: index > 0 ? ordered[index - 1].image_id : null,
    nextId: index >= 0 && index < ordered.length - 1 ? ordered[index + 1].image_id : null,
    previousImageConfirmed: index > 0 && imageContextConfirmed(ordered[index - 1]),
    nextImageConfirmed: index >= 0 && index < ordered.length - 1 && imageContextConfirmed(ordered[index + 1]),
    nextIncompleteId: currentId ? nextIncompleteCaseId(cases, currentId) : null,
    position: index >= 0 ? index + 1 : null,
    total: ordered.length,
    loading,
    error,
    retry: () => setAttempt((value) => value + 1),
  };
}
