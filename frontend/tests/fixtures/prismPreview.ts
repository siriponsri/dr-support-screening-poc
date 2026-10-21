import { createHash } from 'node:crypto';
import type { CaseRecord, ModelDescriptor } from '@/lib/api';
import { preparationContext, type PrismInputPreview } from '@/lib/prismInputPreview';

export const pngBytes = Uint8Array.from(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhCkAAAAASUVORK5CYII=', 'base64'));
export const pngSha = createHash('sha256').update(pngBytes).digest('hex');
export const model: ModelDescriptor = { model_id: 'prism-dr-5fold', model_version: 'synthetic-v1', task: 'lesion-roi', status: 'LOADED', modalities: ['UWF'] };
export const previewCase: CaseRecord = {
  image_id: 'synthetic-preview', display_name: 'Synthetic preview', filename: null,
  source: 'fixture', source_type: 'SYNTHETIC', source_origin: 'SYNTHETIC', source_sha256: 'a'.repeat(64),
  modality: 'UWF', width: 1, height: 1, image_url: null, state: 'PENDING', revision: 7,
  global: null, lesion: null, lesion_review: null, human_annotations: [], clinician_review: null,
};

export function makePlan(item = previewCase): PrismInputPreview {
  return {
    schema_version: 'prism-input-preview.v1', status: 'READY', image_id: item.image_id, case_revision: item.revision,
    source_sha256: item.source_sha256!, source_rgb_sha256: 'b'.repeat(64), wire_sha256: 'c'.repeat(64),
    wire_byte_count: 72, wire_media_type: 'image/png', model_id: model.model_id, model_version: model.model_version!,
    preparation_context: preparationContext(item), plan_id: 'synthetic-plan', plan_sha256: 'd'.repeat(64),
    expires_at: '2099-01-01T00:00:00Z', baseline_preserved: true, candidate_applied: false,
    preview_scope: 'API_SUBMISSION', internal_roi: 'NOT_PREVIEWED', native_roi_status: 'NOT_RUN',
    native_roi_bbox: null, exact_lesion_input_available: false, final_crop_or_tensor_sha256: null,
    external_fov_status: 'UNAVAILABLE', external_fov_reason_code: 'SYNTHETIC_FIXTURE',
    mask_application: 'NONE_PLANNED', input_kind: 'ORIGINAL_FALLBACK', fallback_reason: 'No trusted external FOV candidate',
    mask: { kind: 'NONE', version: 'none', sha256: null },
    transform: { version: 'synthetic-identity-v1', sha256: 'e'.repeat(64), original_width: item.width, original_height: item.height,
      input_width: 1, input_height: 1, original_to_input: [1, 0, 0, 1, 0, 0] },
    original_preview: { url: '/v1/preview/original.png', sha256: pngSha },
    input_preview: { url: '/v1/preview/wire.png', sha256: pngSha, rgb_sha256: 'f'.repeat(64) },
    overlay: null, retained_fraction: 1, excluded_fraction: 0, uncertain_fraction: 0,
  };
}
