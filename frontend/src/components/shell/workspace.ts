/**
 * Sidebar workspace context — the "CURRENT WORKSPACE" panel.
 *
 * For Round 2 the workspace is an in-memory placeholder. A future round
 * will wire this to the Dataset Workspace backend; the public surface
 * (label + counts + selector hook) is designed to be source-agnostic so
 * the eventual data layer can drop in without changes to consumers.
 */
import { useMemo } from 'react';

export interface WorkspaceSummary {
  id: string;
  label: string;
  modality: string;
  caseCount: number;
  reviewedCount: number;
}

const APRIL_WORKSPACE: WorkspaceSummary = {
  id: 'april-dr',
  label: 'April DR Screening',
  modality: 'Color fundus photography',
  caseCount: 12,
  reviewedCount: 3,
};

export interface WorkspaceState {
  workspace: WorkspaceSummary | null;
  selectWorkspace: (id: string) => void;
}

export function useWorkspace(): WorkspaceState {
  // Placeholder behaviour: a stable "demo" workspace is pre-selected so
  // the chrome reads as populated without pretending to be real data.
  const workspace = useMemo(() => APRIL_WORKSPACE, []);
  return {
    workspace,
    selectWorkspace: (_id: string) => {
      // Round 3 will plumb this through the Datasets workspace backend.
    },
  };
}
