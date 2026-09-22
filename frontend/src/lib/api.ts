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
  detection_id?: string;
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

export type LesionReviewAction = 'CONFIRM' | 'REJECT' | 'CORRECT';

export interface ReviewEvidenceItem {
  annotation_id: string | null;
  source: 'AI' | 'HUMAN';
  label: string | null;
  score: number | null;
  original_score: number | null;
  status: 'AI_SUGGESTED' | 'CLINICIAN_CONFIRMED' | 'CLINICIAN_REMOVED' | 'CLINICIAN_ADDED' | 'LABEL_CHANGED' | 'GEOMETRY_CHANGED' | 'CORRECTED';
  model_id: string | null;
  model_version: string | null;
  reviewer: string | null;
  timestamp: string | null;
  original_label: string | null;
  original_rectangle: [number, number, number, number] | null;
  corrected_label: string | null;
  corrected_rectangle: [number, number, number, number] | null;
}

export interface ReviewEvidence {
  status: string;
  reviewer: string | null;
  timestamp: string | null;
  summary: { confirmed: number; added: number; removed: number; corrected: number };
  unresolved_count: number;
  items: ReviewEvidenceItem[];
  model_id: string | null;
  model_version: string | null;
  source_sha256: string | null;
  analysis_sha256: string | null;
  note: string;
}

export interface LesionReviewActionRequest {
  revision: number;
  reviewer: string;
  detection_id: string;
  action: LesionReviewAction;
  label?: LesionLabel;
  rectangle?: [number, number, number, number];
  note?: string;
}

export interface CoordinateMapping {
  kind: 'IDENTITY' | 'SCALE';
  canonical_width: number;
  canonical_height: number;
  analysis_width: number;
  analysis_height: number;
  scale_x: number;
  scale_y: number;
}

export interface DerivativeLineage {
  source_sha256: string;
  derivative_sha256: string;
  purpose: 'DISPLAY' | 'ANALYSIS' | 'MASTER';
  format: string;
  media_type: string;
  width: number;
  height: number;
  bit_depth: number | null;
  transform_id: string;
  transform_description: string;
  coordinate_space: string;
  created_at: string;
}

export interface AnalysisDerivativeAudit {
  source_sha256: string;
  derivative_sha256: string;
  analysis_sha256: string;
  purpose: 'DISPLAY' | 'ANALYSIS' | 'MASTER';
  transform_id: string;
  transform_description: string;
  source_dimensions: { width: number; height: number; bit_depth: number | null; channels?: number | null };
  analysis_dimensions: { width: number; height: number; bit_depth: number | null; channels?: number | null };
  coordinate_mapping: CoordinateMapping;
  lineage: DerivativeLineage;
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
  image_url: string | null;
  source_image_url?: string | null;
  source_sha256?: string | null;
  analysis_derivative?: AnalysisDerivativeAudit | null;
  state: string;
  revision: number;
  global: GlobalResult | null;
  lesion: LesionResult | null;
  lesion_review: LesionReview | null;
  review_evidence?: ReviewEvidence;
  human_annotations: HumanAnnotation[];
  clinician_review: ClinicianReview | null;
  events?: Array<Record<string, unknown>>;
  review_history?: Array<Record<string, unknown>>;
  annotations?: Array<Record<string, unknown>> | null;
  cvat?: Record<string, unknown> | null;
  warnings?: string[];
  admission: AdmissionMetadata | null;
  admission_ui: AdmissionUi | null;
  admission_history?: Array<Record<string, unknown>>;
  patient_key?: string | null;
  patient_resolution_state?: ResolverState;
  patient_resolution_method?: string;
  patient_reason_code?: string;
  patient_candidate?: string | null;
  laterality?: Laterality;
  laterality_resolution_state?: ResolverState;
  laterality_resolution_method?: string;
  laterality_reason_code?: string;
  laterality_candidate?: Laterality | null;
  resolver_state?: ResolverState;
  resolver_ui?: ResolverUi;
  resolution_history?: Array<Record<string, unknown>>;
  queue_state?: 'INCLUDED' | 'EXCLUDED';
  queue_history?: Array<Record<string, unknown>>;
}

export type Laterality = 'LEFT' | 'RIGHT' | 'UNKNOWN';
export type ResolverState = 'RESOLVED' | 'NEEDS_CONFIRMATION' | 'UNLINKED' | 'CONFLICT';

export interface ResolverUiItem {
  label: string;
  note: string;
  tone: 'neutral' | 'success' | 'warning' | 'danger';
  action_required: boolean;
  patient_key?: string | null;
  candidate?: string | null;
  value?: Laterality;
}

export interface ResolverUi {
  label: string;
  note: string;
  tone: 'neutral' | 'success' | 'warning' | 'danger';
  action_required: boolean;
  patient: ResolverUiItem;
  laterality: ResolverUiItem;
}

export interface ResolverReviewRequest {
  revision: number;
  reviewer: string;
  patient_action?: 'KEEP' | 'CONFIRM' | 'SET' | 'LEAVE_UNLINKED';
  patient_key?: string | null;
  laterality_action?: 'KEEP' | 'SET';
  laterality?: Laterality;
  note?: string;
}

export type ModalityAdmission = 'FUNDUS_ACCEPTED' | 'NEEDS_REVIEW' | 'REJECTED_NON_FUNDUS' | 'REJECTED_INVALID';
export type QualityState = 'GRADABLE' | 'UNGRADABLE' | 'NEEDS_REVIEW' | 'NOT_EVALUATED';

export interface AdmissionMetadata {
  image_id: string;
  source_reference: string;
  filename: string;
  file_extension: string;
  file_size_bytes: number;
  width: number | null;
  height: number | null;
  channels_or_mode: string | null;
  modality_admission: ModalityAdmission;
  quality_state: QualityState;
  admission_method: 'AUTOMATIC' | 'MANUAL' | 'LEGACY_COMPAT' | 'DATASET_IMPORT';
  admission_reason_code: string;
  quality_reason_code: string | null;
  created_at: string;
  updated_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
}

export interface AdmissionUi {
  label: string;
  note: string;
  tone: 'neutral' | 'success' | 'warning' | 'danger';
  action_required: boolean;
}

export type AdmissionReviewAction =
  | 'ACCEPT_RETINAL'
  | 'MARK_NON_FUNDUS'
  | 'QUALITY_ACCEPTABLE'
  | 'QUALITY_INADEQUATE'
  | 'LEAVE_UNRESOLVED';

export interface AdmissionReviewRequest {
  revision: number;
  reviewer: string;
  action: AdmissionReviewAction;
  note?: string;
}

export interface AdmissionScanResponse {
  records: AdmissionMetadata[];
  warnings: string[];
  scanned: boolean;
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
  note?: string | null;
  created_at: string;
  updated_at: string;
  last_opened: string | null;
}

export type WorkspaceDraft = Pick<
  WorkspaceProfile,
  'name' | 'input_folder' | 'output_folder' | 'database_path'
> & { note: string | null };

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

export interface WorkspaceDeleteResponse {
  deleted: boolean;
  workspace_id: string;
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

export interface QueueActionRequest {
  revision: number;
  action: 'EXCLUDE' | 'RESTORE';
  note?: string;
}

export interface DatasetImageRow {
  image_id: string;
  filename: string;
  image_sha256: string | null;
  width: number | null;
  height: number | null;
  modality: string | null;
  source_type: string | null;
  patient_key: string | null;
  laterality: Laterality;
  patient_resolution_method: string;
  laterality_resolution_method: string;
  modality_admission: string | null;
  quality_state: string | null;
  queue_state: 'INCLUDED' | 'EXCLUDED';
  ai_grade: number | null;
  ai_model_id: string | null;
  ai_model_version: string | null;
  ai_confidence: number | null;
  clinician_grade: number | null;
  grade_review_source: string | null;
  review_status: string;
  reviewer: string | null;
  reviewed_at: string | null;
  human_annotation_count: number;
  ai_lesion_count: number;
  cvat_annotation_count: number;
  verification_status: string;
  include_in_training: boolean;
  eligibility_reason: string;
  dataset_status: 'Ready for dataset' | 'Needs review' | 'Excluded' | 'AI only';
}

export interface DatasetAnnotationRow {
  annotation_id: string;
  image_id: string;
  label: LesionLabel;
  shape_type: string;
  geometry_json: string;
  annotation_source: 'AI' | 'HUMAN' | 'CVAT_IMPORTED';
  reviewer: string | null;
  created_at: string | null;
  model_id: string | null;
  model_version: string | null;
  score: number | null;
  verification_status: string;
  include_in_training: boolean;
  eligibility_reason: string;
}

export interface DatasetManifestResponse {
  schema_version: string;
  export_id: string | null;
  created_at: string;
  workspace_id: string | null;
  workspace_name: string | null;
  image_count: number;
  annotation_count: number;
  training_ready_count: number;
  needs_review_count: number;
  excluded_count: number;
  can_export: boolean;
  images: DatasetImageRow[];
  annotations: DatasetAnnotationRow[];
}

export interface DatasetExportResponse {
  schema_version: string;
  export_id: string;
  created_at: string;
  workspace_id: string;
  workspace_name: string;
  directory_name: string;
  image_count: number;
  annotation_count: number;
  training_ready_count: number;
  files: string[];
}

export interface ModelConnectionModel {
  model_id: string;
  ready: boolean;
  status?: string | null;
}

export interface ModelConnectionResponse {
  name: string | null;
  url: string | null;
  token_configured: boolean;
  status: 'CONNECTED' | 'NOT_CONFIGURED' | 'UNAVAILABLE' | 'UNVERIFIED';
  message: string;
  models: ModelConnectionModel[];
}

export interface ModelConnectionInput {
  name: string;
  url: string;
  token?: string;
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
  remove: (id: string) => apiJson<WorkspaceDeleteResponse>(
    `/v1/workspaces/${encodeURIComponent(id)}`,
    jsonRequest({ method: 'DELETE' }),
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

export const admissionApi = {
  scan: () => apiJson<AdmissionScanResponse>('/v1/admissions/scan', jsonRequest({ method: 'POST' })),
  review: (imageId: string, request: AdmissionReviewRequest) => apiJson<CaseRecord>(
    `/v1/cases/${encodeURIComponent(imageId)}/admission`,
    jsonRequest({ method: 'POST', body: JSON.stringify(request) }),
  ),
};

export const resolverApi = {
  review: (imageId: string, request: ResolverReviewRequest) => apiJson<CaseRecord>(
    `/v1/cases/${encodeURIComponent(imageId)}/resolver`,
    jsonRequest({ method: 'POST', body: JSON.stringify(request) }),
  ),
};

export const queueApi = {
  update: (imageId: string, request: QueueActionRequest) => apiJson<CaseRecord>(
    `/v1/cases/${encodeURIComponent(imageId)}/queue`,
    jsonRequest({ method: 'POST', body: JSON.stringify(request) }),
  ),
};

export const lesionReviewApi = {
  review: (imageId: string, request: LesionReviewActionRequest) => apiJson<CaseRecord>(
    `/v1/cases/${encodeURIComponent(imageId)}/lesion-review`,
    jsonRequest({ method: 'POST', body: JSON.stringify(request) }),
  ),
};

export const datasetApi = {
  manifest: () => apiJson<DatasetManifestResponse>('/v1/dataset/manifest?include_annotations=false'),
  export: () => apiJson<DatasetExportResponse>('/v1/dataset/export', jsonRequest({ method: 'POST' })),
};

export const modelConnectionApi = {
  get: () => apiJson<ModelConnectionResponse>('/v1/model-connection'),
  test: (request: ModelConnectionInput) => apiJson<ModelConnectionResponse>('/v1/model-connection/test', jsonRequest({ method: 'POST', body: JSON.stringify(request) })),
  save: (request: ModelConnectionInput) => apiJson<ModelConnectionResponse>('/v1/model-connection', jsonRequest({ method: 'PUT', body: JSON.stringify(request) })),
};

export async function apiJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const body = await response.json().catch(() => null) as { detail?: string } | null;
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed with HTTP ${response.status}`);
  }
  return body as T;
}
