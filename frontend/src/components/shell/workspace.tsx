import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  workspaceApi,
  type ActiveWorkspaceResponse,
  type DatabasePickerMode,
  type FolderPickerPurpose,
  type PickerResponse,
  type WorkspaceDatabaseStatus,
  type WorkspaceDraft,
  type WorkspaceMutationResponse,
  type WorkspaceProfile,
} from '@/lib/api';

export type WorkspaceLoadStatus = 'loading' | 'ready' | 'error' | 'degraded';

export interface WorkspaceState {
  workspaces: WorkspaceProfile[];
  activeWorkspace: WorkspaceProfile | null;
  activeDatabase: ActiveWorkspaceResponse['database'] | null;
  status: WorkspaceLoadStatus;
  warnings: string[];
  error: string | null;
  isMutating: boolean;
  refresh: () => Promise<void>;
  createWorkspace: (draft: WorkspaceDraft) => Promise<WorkspaceProfile>;
  updateWorkspace: (id: string, draft: WorkspaceDraft) => Promise<WorkspaceProfile>;
  openWorkspace: (id: string) => Promise<WorkspaceProfile>;
  pickFolder: (purpose: FolderPickerPurpose, initialPath: string) => Promise<PickerResponse>;
  pickDatabase: (mode: DatabasePickerMode, initialPath: string, suggestedName: string) => Promise<PickerResponse>;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);

function errorText(error: unknown) {
  return error instanceof Error ? error.message : 'The workspace request could not be completed.';
}

function uniqueWarnings(...groups: Array<string[] | undefined>) {
  return [...new Set(groups.flatMap((group) => group ?? []).filter(Boolean))];
}

function mergeWorkspace(workspaces: WorkspaceProfile[], next: WorkspaceProfile) {
  const existing = workspaces.some((workspace) => workspace.id === next.id);
  return existing
    ? workspaces.map((workspace) => workspace.id === next.id ? next : workspace)
    : [next, ...workspaces];
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<WorkspaceProfile[]>([]);
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceProfile | null>(null);
  const [activeDatabase, setActiveDatabase] = useState<WorkspaceState['activeDatabase']>(null);
  const [status, setStatus] = useState<WorkspaceLoadStatus>('loading');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isMutating, setIsMutating] = useState(false);
  const requestVersion = useRef(0);

  const refresh = useCallback(async () => {
    const version = ++requestVersion.current;
    setStatus('loading');
    setError(null);

    const [listResult, activeResult] = await Promise.allSettled([
      workspaceApi.list(),
      workspaceApi.active(),
    ]);
    if (version !== requestVersion.current) return;

    const list = listResult.status === 'fulfilled' ? listResult.value : null;
    const active = activeResult.status === 'fulfilled' ? activeResult.value : null;
    const nextWarnings = uniqueWarnings(
      list?.warnings,
      active?.warnings,
      listResult.status === 'rejected'
        ? ['Workspace list could not be loaded.']
        : undefined,
      activeResult.status === 'rejected'
        ? ['Active workspace details are unavailable; the workspace list may still be used.']
        : undefined,
    );

    if (list) {
      setWorkspaces(list.workspaces);
      setActiveWorkspace(active?.workspace ?? list.active_workspace);
    } else if (active) {
      setWorkspaces(active.workspace ? [active.workspace] : []);
      setActiveWorkspace(active.workspace);
    } else {
      setWorkspaces([]);
      setActiveWorkspace(null);
    }
    if (active) setActiveDatabase(active.database);
    else setActiveDatabase(null);
    setWarnings(nextWarnings);

    if (!list && !active) {
      setStatus('error');
      setError('Workspace service is unavailable. Check the local review API and retry.');
    } else {
      setStatus(nextWarnings.length > 0 || (active ? active.database.status !== 'ready' : false) ? 'degraded' : 'ready');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const applyMutation = useCallback((response: WorkspaceMutationResponse) => {
    setWorkspaces((current) => mergeWorkspace(current, response.workspace));
    setActiveWorkspace(response.workspace);
    setActiveDatabase({ path: response.workspace.database_path, status: 'ready' as WorkspaceDatabaseStatus });
    setWarnings(response.warnings);
    setError(null);
    setStatus(response.warnings.length > 0 ? 'degraded' : 'ready');
  }, []);

  const runMutation = useCallback(async (
    request: () => Promise<WorkspaceMutationResponse>,
  ) => {
    setIsMutating(true);
    try {
      const response = await request();
      applyMutation(response);
      return response.workspace;
    } catch (mutationError) {
      setError(errorText(mutationError));
      throw mutationError;
    } finally {
      setIsMutating(false);
    }
  }, [applyMutation]);

  const createWorkspace = useCallback(
    (draft: WorkspaceDraft) => runMutation(() => workspaceApi.create(draft)),
    [runMutation],
  );
  const updateWorkspace = useCallback(
    (id: string, draft: WorkspaceDraft) => runMutation(() => workspaceApi.update(id, draft)),
    [runMutation],
  );
  const openWorkspace = useCallback(
    (id: string) => runMutation(() => workspaceApi.open(id)),
    [runMutation],
  );
  const pickFolder = useCallback(
    (purpose: FolderPickerPurpose, initialPath: string) => workspaceApi.pickFolder(purpose, initialPath),
    [],
  );
  const pickDatabase = useCallback(
    (mode: DatabasePickerMode, initialPath: string, suggestedName: string) => workspaceApi.pickDatabase(mode, initialPath, suggestedName),
    [],
  );

  const value = useMemo<WorkspaceState>(() => ({
    workspaces,
    activeWorkspace,
    activeDatabase,
    status,
    warnings,
    error,
    isMutating,
    refresh,
    createWorkspace,
    updateWorkspace,
    openWorkspace,
    pickFolder,
    pickDatabase,
  }), [
    workspaces,
    activeWorkspace,
    activeDatabase,
    status,
    warnings,
    error,
    isMutating,
    refresh,
    createWorkspace,
    updateWorkspace,
    openWorkspace,
    pickFolder,
    pickDatabase,
  ]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error('useWorkspace must be used inside <WorkspaceProvider>');
  return context;
}
