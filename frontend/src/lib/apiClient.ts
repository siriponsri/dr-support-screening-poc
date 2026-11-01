/** Fetch client for the review API: `apiJson` plus one small object per route group. */
import { requestTiming, type TimingModel } from './localTiming';
import type {
  LesionReviewActionRequest,
  HumanAnnotationDeriveRequest,
  AnnotationCompletenessUpdateRequest,
  CaseRecord,
  ResolverReviewRequest,
  AdmissionReviewRequest,
  ConfirmImageRequest,
  AdmissionScanResponse,
  WorkspaceDraft,
  WorkspaceListResponse,
  ActiveWorkspaceResponse,
  WorkspaceMutationResponse,
  WorkspaceDeleteResponse,
  FolderPickerPurpose,
  DatabasePickerMode,
  PickerResponse,
  QueueActionRequest,
  DatasetManifestResponse,
  DatasetExportResponse,
  WorkspaceDataResponse,
  WorkspaceDataDetail,
  DatasetSnapshotPreview,
  DatasetSnapshotResponse,
  GroupedGradeExportResponse,
  ModelConnectionResponse,
  ModelConnectionInput,
  RegularStatus,
  RegularBatch,
} from './apiTypes';

export function jsonRequest(init: RequestInit = {}): RequestInit {
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
  snapshotPreview: (includeGradeFolders = false, signal?: AbortSignal) => apiJson<DatasetSnapshotPreview>(`/v2/dataset/snapshot/preview${includeGradeFolders ? '?include_grade_folders=true' : ''}`, { signal }),
  snapshot: (options?: { include_grade_folders: true; expected_workspace_id: string; expected_source_state_digest: string; expected_grading_plan_sha256: string }, signal?: AbortSignal) => apiJson<DatasetSnapshotResponse>('/v2/dataset/snapshot', jsonRequest({ method: 'POST', signal, ...(options ? { body: JSON.stringify(options) } : {}) })),
  exportGrouped: (imageFormat: 'PNG' | 'JPEG', jpegQuality: number) => apiJson<GroupedGradeExportResponse>(
    '/v1/dataset/export/grouped-by-grade',
    jsonRequest({ method: 'POST', body: JSON.stringify({ image_format: imageFormat, jpeg_quality: jpegQuality }) }),
  ),
  /** Archive sorting by the AI grade only: a separate ai_predicted_unverified folder, never clinical grades. */
  exportAiPredicted: (imageFormat: 'PNG' | 'JPEG', jpegQuality: number) => apiJson<GroupedGradeExportResponse>(
    '/v1/dataset/export/ai-predicted-by-grade',
    jsonRequest({ method: 'POST', body: JSON.stringify({ image_format: imageFormat, jpeg_quality: jpegQuality }) }),
  ),
};

export const modelConnectionApi = {
  get: () => apiJson<ModelConnectionResponse>('/v1/model-connection'),
  test: (request: ModelConnectionInput) => apiJson<ModelConnectionResponse>('/v1/model-connection/test', jsonRequest({ method: 'POST', body: JSON.stringify(request) })),
  save: (request: ModelConnectionInput) => apiJson<ModelConnectionResponse>('/v1/model-connection', jsonRequest({ method: 'PUT', body: JSON.stringify(request) })),
};

/** Shared AI queue and daily batch; present only on the shared regular model server. */
export const regularApi = {
  status: () => apiJson<RegularStatus>('/v1/regular/status'),
  batches: () => apiJson<{ batches: RegularBatch[] }>('/v1/batches'),
  startAll: () => apiJson<RegularBatch>('/v1/batches', jsonRequest({ method: 'POST', body: JSON.stringify({ all_ready: true }) })),
  cancel: (batchId: string) => apiJson<RegularBatch>(`/v1/batches/${encodeURIComponent(batchId)}/cancel`, jsonRequest({ method: 'POST' })),
};

export async function apiJson<T>(input: RequestInfo | URL, init?: RequestInit, parameters?: TimingModel): Promise<T> {
  const timing = requestTiming(input, init?.method, parameters);
  try {
  const response = await fetch(input, init);
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (!response.ok) {
    throw new Error(normalizeApiDetail(body?.detail) || `Request failed with HTTP ${response.status}`);
  }
  if (body == null) {
    throw new Error('The server returned an invalid response. Reload and try again.');
  }
  timing.end('COMPLETED', response.headers?.get?.('Server-Timing'));
  return body as T;
  } catch (error) {
    timing.end(init?.signal?.aborted || (typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError') ? 'ABORTED' : 'FAILED');
    throw error;
  }
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
