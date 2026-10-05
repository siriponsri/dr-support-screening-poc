import type { CaseRecord, ModelDescriptor } from './api';

const READY_MODEL_STATUSES = new Set(['LOADED', 'SYNTHETIC_FIXTURE']);
const BLOCKED_RELEASE_STATUSES = new Set(['COMPARATOR_ONLY', 'DISABLED', 'DEFERRED']);

export function releaseStatusBlocked(status?: string | null): boolean {
  const normalized = status?.trim().toUpperCase() ?? '';
  return BLOCKED_RELEASE_STATUSES.has(normalized)
    || normalized.startsWith('BLOCKED')
    || normalized.startsWith('DEFERRED');
}

export function isModelUsable(
  model: ModelDescriptor,
  modality: CaseRecord['modality'] | undefined,
  sourceOrigin: string,
): boolean {
  if (!modality || modality === 'UNKNOWN') return false;
  if (!READY_MODEL_STATUSES.has(model.status ?? '') || releaseStatusBlocked(model.release_status)) return false;
  if (model.model_id.startsWith('mock-') && sourceOrigin !== 'SYNTHETIC') return false;
  return (model.modalities ?? model.supported_modalities ?? []).includes(modality);
}

export function hasCompatibleModel(item: CaseRecord, models: ModelDescriptor[]): boolean {
  const sourceOrigin = item.source_origin ?? item.source_type ?? '';
  if (sourceOrigin === 'WORKSPACE') return false;
  return models.some((model) => (
    (model.task === 'global' || model.task === 'lesion-roi')
      && isModelUsable(model, item.modality, sourceOrigin)
  ));
}
