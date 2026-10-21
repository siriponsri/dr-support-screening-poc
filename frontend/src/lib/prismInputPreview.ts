import type { CaseRecord, ModelDescriptor } from './api';

/** Proposed read-only DTO. No current inference route accepts this plan yet. */
export interface PrismInputPreview {
  schema_version: 'prism-input-preview.v1';
  status: 'READY';
  image_id: string;
  case_revision: number;
  source_sha256: string;
  source_rgb_sha256: string;
  wire_sha256: string;
  wire_byte_count: number;
  wire_media_type: string;
  model_id: string;
  model_version: string;
  preparation_context: string;
  plan_id: string;
  plan_sha256: string;
  expires_at: string;
  baseline_preserved: true;
  candidate_applied: false;
  preview_scope: 'API_SUBMISSION';
  internal_roi: 'NOT_PREVIEWED';
  native_roi_status: 'NOT_RUN';
  native_roi_bbox: null;
  exact_lesion_input_available: false;
  final_crop_or_tensor_sha256: null;
  external_fov_status: 'READY' | 'UNCERTAIN' | 'UNAVAILABLE' | 'NOT_APPLICABLE';
  external_fov_reason_code: string | null;
  mask_application: 'CONDITIONAL_ON_NATIVE_ROI_SUCCESS' | 'NONE_PLANNED';
  input_kind: 'ORIGINAL_FALLBACK' | 'UNMASKED_WIRE';
  fallback_reason?: string;
  mask: { kind: 'NONE' | 'ARTIFACT_EXCLUSION' | 'OPTICAL_FOV'; version: string; sha256: string | null };
  transform: {
    version: string; sha256: string;
    original_width: number; original_height: number; input_width: number; input_height: number;
    original_to_input: number[];
  };
  original_preview: PreviewAsset;
  input_preview: PreviewAsset & { rgb_sha256: string };
  overlay: PreviewAsset | null;
  retained_fraction: number;
  excluded_fraction: number;
  uncertain_fraction: number;
}

export interface PreviewAsset { url: string; sha256: string }

const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
const dimension = (value: unknown) => Number.isSafeInteger(value) && Number(value) > 0 && Number(value) <= 100000;

export function requiresPrismPreview(model: ModelDescriptor | undefined): boolean {
  return Boolean(model && [model.model_id, model.provider_id, model.capability_id].some((name) => name?.toLowerCase().includes('prism')));
}

// A byte-for-byte context identifier, not a new mask or clinical approval.
// Main-lane contract must use these same ordered JSON fields if adopting v1.
export function preparationContext(item: CaseRecord): string {
  const prep = item.analysis_preparation;
  const derivative = prep?.derivative ?? item.analysis_derivative;
  return JSON.stringify([
    prep?.status ?? null, prep?.source_sha256 ?? null,
    prep?.candidate_mask_sha256 ?? null, prep?.candidate_mask_representation_version ?? null,
    derivative?.derivative_sha256 ?? null, derivative?.valid_retina_mask_sha256 ?? null,
    derivative?.transform_id ?? null, derivative?.transform_version ?? null,
    derivative?.representation_version ?? null,
  ]);
}

export function previewContextKey(item: CaseRecord, model: ModelDescriptor): string {
  return JSON.stringify([item.image_id, item.revision, item.source_sha256, item.width, item.height,
    item.modality, item.source_origin, item.admission, model, preparationContext(item), item.prism_input_preview]);
}

function safeAsset(value: unknown): value is PreviewAsset {
  if (!record(value) || !hash(value.sha256) || typeof value.url !== 'string') return false;
  // Asset bytes must stay on this application's API, never an external upload/fetch.
  return /^\/v1\/[A-Za-z0-9_./%-]+$/.test(value.url)
    && !value.url.includes('..') && !/%(?:2f|5c|2e)/i.test(value.url);
}

export function validatePrismPreview(value: unknown, item: CaseRecord, model: ModelDescriptor, now = Date.now()): PrismInputPreview {
  if (!record(value) || value.schema_version !== 'prism-input-preview.v1' || value.status !== 'READY') {
    throw new Error('A bound PRISM preview is unavailable. Candidate overlays are inspection only.');
  }
  if (!hash(item.source_sha256) || value.source_sha256 !== item.source_sha256
    || !Number.isSafeInteger(item.revision) || item.revision < 0
    || value.image_id !== item.image_id || value.case_revision !== item.revision
    || value.model_id !== model.model_id || !nonempty(model.model_version) || value.model_version !== model.model_version
    || value.preparation_context !== preparationContext(item)) {
    throw new Error('Preview is stale or belongs to a different image, mask, revision or model. Refresh the case.');
  }
  if (!hash(value.wire_sha256) || !hash(value.source_rgb_sha256)
    || !Number.isSafeInteger(value.wire_byte_count) || Number(value.wire_byte_count) <= 0
    || !['image/png', 'image/jpeg'].includes(String(value.wire_media_type))) {
    throw new Error('Frozen API wire-byte identity is unavailable.');
  }
  if (!nonempty(value.plan_id) || !hash(value.plan_sha256) || typeof value.expires_at !== 'string'
    || !/(?:Z|\+00:00)$/.test(value.expires_at)
    || !Number.isFinite(Date.parse(value.expires_at)) || Date.parse(value.expires_at) <= now
    || value.baseline_preserved !== true || value.candidate_applied !== false) {
    throw new Error('Preview is expired or does not preserve the selected baseline.');
  }
  if (!['API_SUBMISSION', 'FINAL_MODEL_INPUT'].includes(String(value.preview_scope))
    || !['NOT_PREVIEWED', 'BOUND_IN_PLAN', 'NOT_APPLICABLE'].includes(String(value.internal_roi))
    || (value.preview_scope === 'FINAL_MODEL_INPUT' && value.internal_roi === 'NOT_PREVIEWED')) {
    throw new Error('Internal PRISM ROI processing is not bound to this final-input preview.');
  }
  // Native YOLO ROI runs inside inference. A future exact crop/tensor preview
  // requires a separately qualified two-stage contract and new schema version.
  if (value.preview_scope !== 'API_SUBMISSION' || value.internal_roi !== 'NOT_PREVIEWED'
    || value.native_roi_status !== 'NOT_RUN'
    || value.native_roi_bbox !== null || value.exact_lesion_input_available !== false
    || value.final_crop_or_tensor_sha256 !== null
    || !['READY', 'UNCERTAIN', 'UNAVAILABLE', 'NOT_APPLICABLE'].includes(String(value.external_fov_status))
    || !['CONDITIONAL_ON_NATIVE_ROI_SUCCESS', 'NONE_PLANNED'].includes(String(value.mask_application))) {
    throw new Error('Exact final lesion input requires a separately qualified two-stage contract.');
  }
  const mask = value.mask;
  const transform = value.transform;
  if (!record(mask) || !['NONE', 'ARTIFACT_EXCLUSION', 'OPTICAL_FOV'].includes(String(mask.kind))
    || !nonempty(mask.version) || (mask.kind === 'NONE' ? mask.sha256 !== null : !hash(mask.sha256))
    || !record(transform) || !hash(transform.sha256) || !nonempty(transform.version)
    || !dimension(item.width) || !dimension(item.height)
    || transform.original_width !== item.width || transform.original_height !== item.height
    || !dimension(transform.input_width) || !dimension(transform.input_height)
    || !Array.isArray(transform.original_to_input) || transform.original_to_input.length !== 6
    || !transform.original_to_input.every((n) => typeof n === 'number' && Number.isFinite(n))) {
    throw new Error('Mask identity or original-image coordinate transform is incomplete.');
  }
  const [a, b, c, d] = transform.original_to_input as number[];
  if (Math.abs(a * d - b * c) < 1e-12) throw new Error('Preview transform is singular.');
  if (!['ORIGINAL_FALLBACK', 'UNMASKED_WIRE'].includes(String(value.input_kind))
    || (value.input_kind === 'ORIGINAL_FALLBACK' && (mask.kind !== 'NONE' || !nonempty(value.fallback_reason)))
    || (value.mask_application === 'NONE_PLANNED' && mask.kind !== 'NONE')
    || (value.mask_application === 'CONDITIONAL_ON_NATIVE_ROI_SUCCESS'
      && (mask.kind !== 'OPTICAL_FOV' || value.external_fov_status !== 'READY'))) {
    throw new Error('A conditional FOV candidate cannot be presented as an applied mask or native crop.');
  }
  const fractions = [value.retained_fraction, value.excluded_fraction, value.uncertain_fraction];
  if (!fractions.every((n) => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1)
    || Math.abs((fractions as number[]).reduce((sum, n) => sum + n, 0) - 1) > 1e-6
    || (mask.kind === 'NONE' && (value.excluded_fraction !== 0 || value.uncertain_fraction !== 0))
    || ((value.excluded_fraction !== 0 || value.uncertain_fraction !== 0) && value.overlay === null)) {
    throw new Error('Retained, excluded and uncertain coverage is incomplete.');
  }
  if (!safeAsset(value.original_preview) || !safeAsset(value.input_preview)
    || !('rgb_sha256' in value.input_preview) || !hash(value.input_preview.rgb_sha256)
    || (value.overlay !== null && !safeAsset(value.overlay))) {
    throw new Error('Immutable preview assets or input-pixel provenance are unavailable.');
  }
  return value as unknown as PrismInputPreview;
}

/** Verifies encoded PNG bytes and dimensions. RGB digest remains server attestation. */
export async function loadPreviewAsset(asset: PreviewAsset, width: number, height: number, signal: AbortSignal): Promise<string> {
  if (!safeAsset(asset)) throw new Error('Preview asset must be an immutable local API reference.');
  if (!dimension(width) || !dimension(height) || width * height > 50_000_000) throw new Error('Preview dimensions exceed the browser verification limit.');
  const response = await fetch(asset.url, { method: 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal });
  if (!response.ok) throw new Error('Preview asset is unavailable.');
  const bytes = await response.arrayBuffer();
  if (signal.aborted) throw new Error('Preview changed while loading.');
  if (bytes.byteLength < 24 || bytes.byteLength > 32 * 1024 * 1024) throw new Error('Preview PNG size is invalid.');
  const view = new DataView(bytes);
  if (view.getUint32(0) !== 0x89504e47 || view.getUint32(4) !== 0x0d0a1a0a
    || view.getUint32(12) !== 0x49484452 || view.getUint32(16) !== width || view.getUint32(20) !== height) {
    throw new Error('Preview PNG dimensions do not match its coordinate transform.');
  }
  if (!globalThis.crypto?.subtle) throw new Error('Secure preview verification is unavailable in this browser.');
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), (b) => b.toString(16).padStart(2, '0')).join('');
  if (signal.aborted || digest !== asset.sha256) throw new Error('Preview bytes changed. Reload before continuing.');
  return URL.createObjectURL(new Blob([bytes], { type: 'image/png' }));
}
