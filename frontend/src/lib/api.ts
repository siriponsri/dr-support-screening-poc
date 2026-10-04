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
  source_detection_id?: string | null;
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

export interface HumanAnnotationDeriveRequest {
  revision: number;
  reviewer: string;
  detection_id: string;
  intent: 'USE_AS_HUMAN' | 'CORRECT_AS_HUMAN';
}

export type AnnotationCompletenessState =
  | 'NOT_REVIEWED'
  | 'PARTIALLY_REVIEWED'
  | 'REVIEWED_NONE_FOUND'
  | 'REVIEWED_FINDINGS_RECORDED';

export interface AnnotationCompletenessRecord {
  group: 'CORE' | 'ADVANCED';
  state: AnnotationCompletenessState;
  reviewer: string;
  timestamp: string;
  taxonomy_version: string;
  note: string;
}

export interface AnnotationCompletenessUpdateRequest {
  revision: number;
  reviewer: string;
  group: 'CORE' | 'ADVANCED';
  state: Exclude<AnnotationCompletenessState, 'NOT_REVIEWED'>;
  taxonomy_version: string;
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
  source_origin?: 'PUBLIC' | 'SYNTHETIC' | 'WORKSPACE' | 'UNKNOWN' | string;
  derivative_sha256: string;
  analysis_sha256: string;
  purpose: 'DISPLAY' | 'ANALYSIS' | 'MASTER';
  transform_id: string;
  transform_description: string;
  transform_version?: number;
  representation_version?: string;
  analysis_coordinate_space?: string;
  original_coordinate_space?: string;
  spatial_mapping_version?: string;
  valid_retina_mask_sha256?: string | null;
  valid_retina_fraction?: number | null;
  retinal_field_status?: 'READY' | 'NEEDS_REVIEW' | 'FAILED' | 'NOT_APPLICABLE';
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
  source_detection_id?: string | null;
  source: 'HUMAN';
  reviewer: string;
  created_at: string;
}

export interface ClinicianReview {
  reviewer: string;
  final_grade: number | null;
  review_action: 'ACCEPT' | 'MARK_INCORRECT' | 'CORRECT_GRADE' | 'ESCALATE' | 'CONFIRM_ANNOTATIONS' | 'MARK_UNGRADABLE' | 'REQUEST_SECOND_REVIEW' | 'ADJUDICATE_GRADE';
  remark: string;
  timestamp: string;
  revision: number;
}

export interface GradeReview {
  reviewer: string;
  grade: number | null;
  grade_label?: string | null;
  review_action: ClinicianReview['review_action'];
  remark?: string;
  timestamp: string | null;
  revision?: number;
  legacy?: boolean;
}

export interface SpatialAiDisplay {
  status: 'AVAILABLE' | 'UNAVAILABLE' | 'BLOCKED';
  reason?: string;
  coordinate_space?: string;
  note: string;
}

export interface ExplainabilityState {
  status: 'AVAILABLE' | 'UNAVAILABLE' | 'BLOCKED';
  note: string;
  [key: string]: unknown;
}

export interface ResolverEvidence {
  filename?: {
    patient_candidate?: string | null;
    laterality?: Laterality;
    capture_sequence?: number | null;
    parser_status?: 'MATCHED' | 'AMBIGUOUS' | 'NO_MATCH' | string;
    pattern?: string | null;
  };
  ocr?: {
    status?: string;
    patient_candidate?: string | null;
    laterality?: Laterality;
    strength?: string | null;
  };
}

export interface CaseRecord {
  image_id: string;
  display_name: string;
  filename: string | null;
  source_type: string;
  source_origin?: 'PUBLIC' | 'SYNTHETIC' | 'WORKSPACE' | 'UNKNOWN' | string;
  source: string;
  modality: RetinalModality;
  width: number;
  height: number;
  image_url: string | null;
  source_image_url?: string | null;
  source_sha256?: string | null;
  analysis_derivative?: AnalysisDerivativeAudit | null;
  analysis_preparation?: {
    status: 'READY' | 'NEEDS_REVIEW' | 'FAILED' | 'NOT_APPLICABLE';
    reason_code?: string;
    source_sha256?: string;
    candidate_mask_sha256?: string | null;
    candidate_mask_valid_fraction?: number | null;
    candidate_mask_representation_version?: string | null;
    derivative?: AnalysisDerivativeAudit;
  } | null;
  spatial_ai_display?: SpatialAiDisplay;
  explainability?: ExplainabilityState;
  grade_status?: 'NOT_REVIEWED' | 'CONFIRMED' | 'UNGRADABLE' | 'NEEDS_SECOND_REVIEW' | 'UNKNOWN' | string;
  reviewed_grade?: number | null;
  reviewed_grade_label?: string | null;
  grade_review_source?: string | null;
  grade_reviews?: GradeReview[];
  grade_adjudication?: Record<string, unknown> | null;
  visit_context?: {
    visit_key: string | null;
    captured_at: string | null;
    capture_sequence: number | null;
    device: string | null;
    evidence_state: 'PROVIDED' | 'UNKNOWN' | string;
  } | null;
  state: string;
  revision: number;
  global: GlobalResult | null;
  lesion: LesionResult | null;
  lesion_review: LesionReview | null;
  review_evidence?: ReviewEvidence;
  human_annotations: HumanAnnotation[];
  annotation_completeness?: Partial<Record<'CORE' | 'ADVANCED', AnnotationCompletenessRecord>>;
  clinician_review: ClinicianReview | null;
  annotation_hash?: string | null;
  annotation_set_hash?: string | null;
  annotation_confirmation_status?: 'CONFIRMED' | 'DRAFT';
  annotation_confirmation?: {
    status: 'CONFIRMED' | 'DRAFT';
    reviewer: string | null;
    timestamp: string | null;
    annotation_set_hash: string | null;
  };
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
  resolver_evidence?: ResolverEvidence | null;
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
export type RetinalModality = 'CFP' | 'UWF' | 'UNKNOWN';
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
  retinal_modality?: RetinalModality;
  retinal_modality_state?: 'RESOLVED' | 'NEEDS_CONFIRMATION';
  retinal_modality_method?: 'NONE' | 'MANUAL' | 'LEGACY_COMPAT' | 'DICOM_METADATA';
  retinal_modality_candidate?: RetinalModality | null;
  source_origin?: 'PUBLIC' | 'SYNTHETIC' | 'WORKSPACE' | 'UNKNOWN' | string;
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

export interface ConfirmImageRequest {
  revision: number;
  reviewer: string;
  patient_key?: string | null;
  laterality: Laterality;
  retinal_modality?: RetinalModality;
  visit_key?: string | null;
  captured_at?: string | null;
  capture_sequence?: number | null;
  device?: string | null;
  note?: string;
}

export const DR_GRADE_LABELS: Record<number, string> = {
  0: 'No apparent DR',
  1: 'Mild NPDR',
  2: 'Moderate NPDR',
  3: 'Severe NPDR',
  4: 'Proliferative DR (PDR)',
};

export function drGradeLabel(grade: number | null | undefined): string | null {
  return grade == null ? null : DR_GRADE_LABELS[grade] ?? null;
}

export interface AdmissionScanResponse {
  records: AdmissionMetadata[];
  warnings: string[];
  scanned: boolean;
}

export interface ModelDescriptor {
  model_id: string;
  task: string;
  capability_id?: string;
  provider_id?: string;
  model_version?: string;
  artifact_digest?: string | null;
  trained_domain?: string;
  supported_modalities?: string[];
  domain_status?: string;
  clinical_validation_status?: string;
  rights_status?: string;
  release_status?: string;
  explanation_types?: string[];
  enabled?: boolean;
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
  database_path: string | null;
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

export type WorkspaceDatabaseStatus = 'ready' | 'postgres' | 'fallback' | 'unavailable';

export interface ActiveWorkspaceResponse {
  workspace: WorkspaceProfile | null;
  database: {
    path: string | null;
    status: WorkspaceDatabaseStatus;
  };
  warnings: string[];
}

export interface WorkspaceMutationResponse {
  workspace: WorkspaceProfile;
  active: boolean;
  database?: ActiveWorkspaceResponse['database'];
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
  image_confirmation_status?: string;
  image_confirmed_by?: string | null;
  image_confirmed_at?: string | null;
  dr_grade_confirmation_status?: string;
  dr_grade_confirmed_by?: string | null;
  dr_grade_confirmed_at?: string | null;
  annotation_confirmation_status?: string;
  annotation_confirmed_by?: string | null;
  annotation_confirmed_at?: string | null;
  annotation_set_hash?: string | null;
  confirmed_annotation_hash?: string | null;
  dr_grade_training_ready?: boolean;
  grade_eligibility_reason?: string;
  lesion_training_ready?: boolean;
  lesion_eligibility_reason?: string;
  training_group_key?: string | null;
  source_sha256?: string | null;
  source_origin?: 'PUBLIC' | 'SYNTHETIC' | 'WORKSPACE' | 'UNKNOWN';
  source_available?: boolean;
  source_integrity_status?: string | null;
  export_authorization?: string;
  core_completeness_state?: string;
  advanced_completeness_state?: string;
  negative_training_authorized?: boolean;
  negative_eligibility_reason?: string;
  case_revision?: number;
  visit_evidence_state?: string;
  ai_evidence_status?: string;
  lesion_positive_training_ready?: boolean;
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
  source_detection_id?: string | null;
  original_label?: LesionLabel | null;
  original_score?: number | null;
  original_geometry_json?: string | null;
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
  dr_grade_ready_count?: number;
  lesion_ready_image_count?: number;
  lesion_ready_annotation_count?: number;
  coordinate_system?: string;
  lesion_taxonomy?: string[];
  eligibility_policy_version?: string;
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

export interface WorkspaceDataResponse {
  schema_version: string;
  workspace_id: string | null;
  workspace_name: string | null;
  page: number;
  limit: number;
  total: number;
  has_next: boolean;
  source_state_digest: string | null;
  source_state_digest_version: string;
  source_origin_summary: Record<string, number>;
  export_authorization_summary: Record<string, number>;
  records: DatasetImageRow[];
}

export interface WorkspaceDataDetail {
  schema_version: string;
  workspace_id: string | null;
  workspace_name: string | null;
  source_state_digest: string;
  record: DatasetImageRow;
  review_milestones: Record<string, { status?: string | null; reviewer?: string | null; timestamp?: string | null; provenance?: string | null; hash?: string | null; action?: string | null }>;
  completeness: Array<{ group: string; state: string; reviewer?: string | null; timestamp?: string | null; taxonomy_version?: string | null; negative_training_authorized: boolean; negative_eligibility_reason: string }>;
  gold_label_counts: { dr_grade: number; lesion_positive: number; lesion_negative: number };
  ai_evidence_counts: { items: number; unresolved: number };
  processing: Record<string, unknown>;
  explainability: { status: string; evidence_identity?: string | null; note?: string; ai_evidence?: unknown };
}

export interface DatasetSnapshotPreview {
  schema_version: string;
  workspace_id: string | null;
  workspace_name: string | null;
  source_state_digest: { digest: string; case_count: number };
  case_count: number;
  row_counts: Record<string, number>;
  source_origin_summary: Record<string, number>;
  export_authorization_summary: Record<string, number>;
  blocked_record_count: number;
  negative_policy_version: string;
  can_export: boolean;
}

export interface DatasetSnapshotResponse {
  schema_version: string;
  snapshot_id: string;
  workspace_id: string;
  workspace_name: string;
  directory_name: string;
  manifest: Record<string, unknown>;
  receipt: Record<string, unknown>;
}

export interface GroupedGradeExportResponse {
  directory_name: string;
  image_format: 'PNG' | 'JPEG';
  copied_count: number;
  identical_existing_count: number;
  skipped_count: number;
  manifest: string;
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
  confirmImage: (imageId: string, request: ConfirmImageRequest) => apiJson<CaseRecord>(
    `/v1/cases/${encodeURIComponent(imageId)}/confirm-image`,
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

export const humanAnnotationApi = {
  deriveFromAi: (imageId: string, request: HumanAnnotationDeriveRequest) => apiJson<CaseRecord>(
    `/v1/cases/${encodeURIComponent(imageId)}/annotations/from-ai`,
    jsonRequest({ method: 'POST', body: JSON.stringify(request) }),
  ),
};

export const annotationCompletenessApi = {
  update: (imageId: string, request: AnnotationCompletenessUpdateRequest) => apiJson<CaseRecord>(
    `/v1/cases/${encodeURIComponent(imageId)}/annotation-completeness`,
    jsonRequest({ method: 'PUT', body: JSON.stringify(request) }),
  ),
};

export const datasetApi = {
  manifest: () => apiJson<DatasetManifestResponse>('/v1/dataset/manifest?include_annotations=false'),
  export: () => apiJson<DatasetExportResponse>('/v1/dataset/export', jsonRequest({ method: 'POST' })),
  workspaceData: (params: { page: number; limit: number; readiness: string; laterality?: string; modality?: string; sourceOrigin?: string; q?: string }) => {
    const query = new URLSearchParams({ page: String(params.page), limit: String(params.limit), readiness: params.readiness });
    if (params.laterality) query.set('laterality', params.laterality);
    if (params.modality) query.set('modality', params.modality);
    if (params.sourceOrigin) query.set('source_origin', params.sourceOrigin);
    if (params.q) query.set('q', params.q);
    return apiJson<WorkspaceDataResponse>(`/v2/workspace-data/records?${query.toString()}`);
  },
  workspaceDataDetail: (imageId: string) => apiJson<WorkspaceDataDetail>(`/v2/workspace-data/records/${encodeURIComponent(imageId)}`),
  snapshotPreview: () => apiJson<DatasetSnapshotPreview>('/v2/dataset/snapshot/preview'),
  snapshot: () => apiJson<DatasetSnapshotResponse>('/v2/dataset/snapshot', jsonRequest({ method: 'POST' })),
  exportGrouped: (imageFormat: 'PNG' | 'JPEG', jpegQuality: number) => apiJson<GroupedGradeExportResponse>(
    '/v1/dataset/export/grouped-by-grade',
    jsonRequest({ method: 'POST', body: JSON.stringify({ image_format: imageFormat, jpeg_quality: jpegQuality }) }),
  ),
};

export const modelConnectionApi = {
  get: () => apiJson<ModelConnectionResponse>('/v1/model-connection'),
  test: (request: ModelConnectionInput) => apiJson<ModelConnectionResponse>('/v1/model-connection/test', jsonRequest({ method: 'POST', body: JSON.stringify(request) })),
  save: (request: ModelConnectionInput) => apiJson<ModelConnectionResponse>('/v1/model-connection', jsonRequest({ method: 'PUT', body: JSON.stringify(request) })),
};

export async function apiJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (!response.ok) {
    throw new Error(normalizeApiDetail(body?.detail) || `Request failed with HTTP ${response.status}`);
  }
  return body as T;
}

export function normalizeApiDetail(detail: unknown): string {
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) {
    const messages = detail
      .map((entry) => (entry && typeof entry === 'object' && 'msg' in entry ? entry.msg : entry))
      .filter((entry): entry is string => typeof entry === 'string' && Boolean(entry.trim()))
      .map((entry) => entry.trim());
    if (messages.length) return messages.join(' ');
  }
  if (detail && typeof detail === 'object') {
    const record = detail as Record<string, unknown>;
    for (const key of ['message', 'msg', 'error']) {
      if (typeof record[key] === 'string' && record[key].trim()) return record[key].trim();
    }
  }
  return '';
}
