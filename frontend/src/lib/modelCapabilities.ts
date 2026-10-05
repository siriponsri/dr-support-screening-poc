import type { CaseRecord, ModelDescriptor } from './api';

const READY_MODEL_STATUSES = new Set(['LOADED', 'SYNTHETIC_FIXTURE']);
const BLOCKED_RELEASE_STATUSES = new Set(['COMPARATOR_ONLY', 'DISABLED', 'DEFERRED']);
const CFP_ONLY_MODEL_IDS = new Set(['retfound-aptos5', 'prism-dr-5fold']);
const EXPECTED_MODEL_TASKS: Record<string, string> = {
  'retfound-aptos5': 'global',
  'prism-dr-5fold': 'lesion-roi',
};

export function isCfpOnlyModel(modelId: string): boolean {
  return CFP_ONLY_MODEL_IDS.has(modelId);
}

export function releaseStatusBlocked(status?: string | null): boolean {
  const normalized = status?.trim().toUpperCase() ?? '';
  return BLOCKED_RELEASE_STATUSES.has(normalized)
    || normalized.startsWith('BLOCKED')
    || normalized.startsWith('DEFERRED');
}

function hasQualifiedCapability(model: ModelDescriptor): boolean {
  const modalities = model.modalities ?? model.supported_modalities ?? [];
  const expectedTask = EXPECTED_MODEL_TASKS[model.model_id];
  if (expectedTask) {
    return model.task === expectedTask && modalities.includes('CFP');
  }
  if (model.model_id.startsWith('mock-')) {
    return Boolean(model.task && modalities.length > 0);
  }
  const capabilityId = model.capability_id?.trim();
  const revision = model.revision?.trim();
  const preprocessing = (model.preprocessing ?? model.preprocessing_version)?.trim();
  return Boolean(
    capabilityId
      && revision
      && preprocessing
      && !['UNKNOWN', 'NOT_REPORTED'].includes(revision.toUpperCase())
      && !['UNKNOWN', 'NOT_REPORTED'].includes(preprocessing.toUpperCase()),
  );
}

export function isModelUsable(
  model: ModelDescriptor,
  modality: CaseRecord['modality'] | undefined,
  sourceOrigin: string,
): boolean {
  if (!modality || modality === 'UNKNOWN') return false;
  if (!READY_MODEL_STATUSES.has(model.status ?? '') || releaseStatusBlocked(model.release_status)) return false;
  if (model.ready === false || (model.ready !== true && !hasQualifiedCapability(model))) return false;
  if (model.model_id.startsWith('mock-') && sourceOrigin !== 'SYNTHETIC') return false;
  if (modality === 'UWF' && isCfpOnlyModel(model.model_id)) return false;
  return (model.modalities ?? model.supported_modalities ?? []).includes(modality);
}

export function hasCompatibleModel(item: CaseRecord, models: ModelDescriptor[]): boolean {
  const sourceOrigin = item.source_origin ?? item.source_type ?? '';
  if (
    !['PUBLIC', 'SYNTHETIC'].includes(sourceOrigin)
    || item.admission?.modality_admission !== 'FUNDUS_ACCEPTED'
    || !['GRADABLE', 'NOT_EVALUATED'].includes(item.admission?.quality_state ?? '')
  ) return false;
  return models.some((model) => (
    (model.task === 'global' || model.task === 'lesion-roi')
      && isModelUsable(model, item.modality, sourceOrigin)
  ));
}
