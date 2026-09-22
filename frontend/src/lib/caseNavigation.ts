import { useEffect, useState } from 'react';
import type { CaseRecord } from './api';

export interface CaseNeighbors {
  previousId: string | null;
  nextId: string | null;
  position: number | null;
  total: number;
  loading: boolean;
}

function orderedCases(cases: CaseRecord[], currentId: string): CaseRecord[] {
  const visible = cases.filter((item) => item.queue_state !== 'EXCLUDED' || item.image_id === currentId);
  return [...visible].sort((left, right) => {
    const leftName = left.filename ?? left.display_name;
    const rightName = right.filename ?? right.display_name;
    return leftName.localeCompare(rightName, undefined, { numeric: true, sensitivity: 'base' })
      || left.image_id.localeCompare(right.image_id);
  });
}

export function useCaseNeighbors(currentId: string | undefined): CaseNeighbors {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(Boolean(currentId));

  useEffect(() => {
    if (!currentId) return;
    let active = true;
    setLoading(true);
    fetch('/v1/cases')
      .then((response) => response.ok ? response.json() as Promise<CaseRecord[]> : [])
      .then((loaded) => { if (active) setCases(Array.isArray(loaded) ? loaded : []); })
      .catch(() => { if (active) setCases([]); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [currentId]);

  const ordered = currentId ? orderedCases(cases, currentId) : [];
  const index = ordered.findIndex((item) => item.image_id === currentId);
  return {
    previousId: index > 0 ? ordered[index - 1].image_id : null,
    nextId: index >= 0 && index < ordered.length - 1 ? ordered[index + 1].image_id : null,
    position: index >= 0 ? index + 1 : null,
    total: ordered.length,
    loading,
  };
}
