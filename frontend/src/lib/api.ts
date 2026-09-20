export interface GlobalResult {
  schema_version?: string;
  model_id: string;
  model_version: string;
  modality: string;
  state: string;
  grade: number | null;
  probabilities: number[];
  confidence: number | null;
  warnings: string[];
  provenance?: Provenance;
}

export interface Provenance {
  image_sha256: string;
  source_type: string;
  preprocessing: string;
  checkpoint_sha256: Record<string, string>;
  source_revision: string;
}

export interface Lesion {
  source_label: string;
  canonical_label: string;
  rectangle: [number, number, number, number];
  score: number;
  state: string;
}

export interface LesionResult {
  schema_version?: string;
  model_id: string;
  model_version: string;
  modality: string;
  state: string;
  width: number;
  height: number;
  lesions: Lesion[];
  warnings: string[];
  provenance?: Provenance;
}

export interface LesionReview {
  raw_count: number;
  suggestion_count: number;
  filtered_count: number;
  lesions: Lesion[];
  policy: {
    thresholds: Record<string, number>;
    max_per_class: number;
    max_total: number;
  };
  note?: string;
}

export type LesionLabel = 'MICROANEURYSM' | 'HEMORRHAGE' | 'HARD_EXUDATE' | 'SOFT_EXUDATE';
export type AnnotationType = 'rectangle' | 'polygon' | 'point' | 'circle';
export type AnnotationGeometry =
  | { x: number; y: number; width: number; height: number }
  | { points: [number, number][] }
  | { x: number; y: number }
  | { cx: number; cy: number; radius: number };

export interface HumanAnnotation {
  shape_id: string;
  type: AnnotationType;
  label: LesionLabel;
  geometry: AnnotationGeometry;
  /** Legacy records omit this field; the editor treats those records as locked. */
  locked?: boolean;
  source: 'HUMAN';
  reviewer: string;
  created_at: string;
}

export interface ClinicianReview {
  reviewer: string;
  final_grade: number | null;
  review_action: 'ACCEPT' | 'MARK_INCORRECT' | 'CORRECT_GRADE' | 'ESCALATE' | 'CONFIRM_ANNOTATIONS';
  remark: string;
  timestamp: string;
  revision: number;
}

export interface CaseRecord {
  image_id: string;
  display_name: string;
  filename: string | null;
  source_type: string;
  source: string;
  modality: string;
  width: number;
  height: number;
  image_url: string;
  state: string;
  revision: number;
  global: GlobalResult | null;
  lesion: LesionResult | null;
  lesion_review: LesionReview | null;
  human_annotations: HumanAnnotation[];
  clinician_review: ClinicianReview | null;
  events?: Array<Record<string, unknown>>;
  warnings?: string[];
}

export interface ModelDescriptor {
  model_id: string;
  task: string;
  runtime?: string;
  status?: string;
  warnings?: string[];
  modalities?: string[];
  revision?: string;
  preprocessing?: string;
}

export interface WorkspaceProfile {
  id: string;
  name: string;
  input_folder: string;
  output_folder: string;
  database_path: string;
  created_at: string;
  updated_at: string;
  last_opened: string | null;
}

export type WorkspaceDraft = Pick<
  WorkspaceProfile,
  'name' | 'input_folder' | 'output_folder' | 'database_path'
>;

export interface WorkspaceListResponse {
  workspaces: WorkspaceProfile[];
  active_workspace_id: string | null;
  active_workspace: WorkspaceProfile | null;
  warnings: string[];
}

export type WorkspaceDatabaseStatus = 'ready' | 'fallback' | 'unavailable';

export interface ActiveWorkspaceResponse {
  workspace: WorkspaceProfile | null;
  database: {
    path: string;
    status: WorkspaceDatabaseStatus;
  };
  warnings: string[];
}

export interface WorkspaceMutationResponse {
  workspace: WorkspaceProfile;
  active: boolean;
  warnings: string[];
}

export type FolderPickerPurpose = 'input' | 'output';
export type DatabasePickerMode = 'open' | 'create';

export interface PickerResponse {
  status: 'selected' | 'cancelled' | 'unavailable';
  path: string | null;
  code: string | null;
  message: string | null;
}

function jsonRequest(init: RequestInit = {}): RequestInit {
  return {
    credentials: 'same-origin',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  };
}

export const workspaceApi = {
  list: () => apiJson<WorkspaceListResponse>('/v1/workspaces'),
  active: () => apiJson<ActiveWorkspaceResponse>('/v1/workspaces/active'),
  create: (draft: WorkspaceDraft) => apiJson<WorkspaceMutationResponse>('/v1/workspaces', jsonRequest({
    method: 'POST',
    body: JSON.stringify(draft),
  })),
  update: (id: string, draft: WorkspaceDraft) => apiJson<WorkspaceMutationResponse>(
    `/v1/workspaces/${encodeURIComponent(id)}`,
    jsonRequest({ method: 'PUT', body: JSON.stringify(draft) }),
  ),
  open: (id: string) => apiJson<WorkspaceMutationResponse>(
    `/v1/workspaces/${encodeURIComponent(id)}/open`,
    jsonRequest({ method: 'POST' }),
  ),
  pickFolder: (purpose: FolderPickerPurpose, initialPath: string) => apiJson<PickerResponse>(
    '/v1/workspaces/pickers/folder',
    jsonRequest({ method: 'POST', body: JSON.stringify({ purpose, initial_path: initialPath }) }),
  ),
  pickDatabase: (mode: DatabasePickerMode, initialPath: string, suggestedName: string) => apiJson<PickerResponse>(
    '/v1/workspaces/pickers/database',
    jsonRequest({
      method: 'POST',
      body: JSON.stringify({ mode, initial_path: initialPath, suggested_name: suggestedName }),
    }),
  ),
};

export async function apiJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const body = await response.json().catch(() => null) as { detail?: string } | null;
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed with HTTP ${response.status}`);
  }
  return body as T;
}
