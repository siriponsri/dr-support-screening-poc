/**
 * Sidebar workspace context — the "CURRENT WORKSPACE" panel.
 *
 * The demo workspace reads its admitted-case count from the existing API and
 * keeps a small offline fallback so the shell remains useful during startup.
 */
import { useEffect, useState } from 'react';
import { apiJson, type CaseRecord } from '@/lib/api';

export interface WorkspaceSummary {
  id: string;
  label: string;
  modality: string;
  caseCount: number;
}

const DEMO_WORKSPACE: WorkspaceSummary = {
  id: 'dr-demo',
  label: 'DR Demo',
  modality: 'Color fundus photography',
  caseCount: 3,
};

export interface WorkspaceState {
  workspace: WorkspaceSummary | null;
  selectWorkspace: (id: string) => void;
}

export function useWorkspace(): WorkspaceState {
  const [workspace, setWorkspace] = useState<WorkspaceSummary>(DEMO_WORKSPACE);
  useEffect(() => {
    void apiJson<CaseRecord[]>('/v1/cases')
      .then((cases) => setWorkspace((current) => ({ ...current, caseCount: cases.length })))
      .catch(() => {
        // Keep the small demo fallback visible while the API is offline.
      });
  }, []);
  return {
    workspace,
    selectWorkspace: (_id: string) => {
      // Round 3 will plumb this through the Datasets workspace backend.
    },
  };
}
