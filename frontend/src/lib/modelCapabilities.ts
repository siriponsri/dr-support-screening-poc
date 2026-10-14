import type { CaseRecord, ModelDescriptor } from './api';

const READY_MODEL_STATUSES = new Set(['LOADED', 'SYNTHETIC_FIXTURE', 'QUALIFIED_NOT_LOADED']);
const BLOCKED_RELEASE_STATUSES = new Set(['COMPARATOR_ONLY', 'DISABLED', 'DEFERRED']);
const KNOWN_RELEASE_STATUSES = new Set(['AVAILABLE', 'QUALIFIED', 'RESEARCH_ONLY', 'COMPARATOR_ONLY', 'DISABLED', 'DEFERRED']);
const CFP_ONLY_MODEL_IDS = new Set(['retfound-aptos5']);
const FIXED_MODEL_MODALITIES: Record<string, readonly string[]> = {
  'retfound-aptos5': ['CFP'],
  'uspec-uwf-grading': ['UWF'],
};
const EXPECTED_MODEL_TASKS: Record<string, string> = {
  'retfound-aptos5': 'global',
  'uspec-uwf-grading': 'global',
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

function releaseStatusKnown(status?: string | null): boolean {
  const normalized = status?.trim().toUpperCase() ?? '';
  return KNOWN_RELEASE_STATUSES.has(normalized)
    || normalized.startsWith('BLOCKED')
    || normalized.startsWith('DEFERRED');
}

function hasQualifiedCapability(model: ModelDescriptor): boolean {
  const modalities = model.modalities ?? model.supported_modalities ?? [];
  const expectedTask = EXPECTED_MODEL_TASKS[model.model_id];
  if (expectedTask && model.task !== expectedTask) return false;
  const fixedModalities = FIXED_MODEL_MODALITIES[model.model_id];
  if (fixedModalities && (
    modalities.length === 0
    || !modalities.some((modality) => fixedModalities.includes(modality))
    || !modalities.every((modality) => fixedModalities.includes(modality))
  )) return false;
  if (model.model_id === 'retfound-aptos5') {
    // Preserve the legacy Bridge descriptor contract while keeping RETFound
    // strictly CFP-only.
    return modalities.includes('CFP');
  }
  if (model.model_id === 'prism-dr-5fold') {
    return releaseStatusKnown(model.release_status) && modalities.includes('CFP');
  }
  if (model.model_id.startsWith('mock-')) {
    return Boolean(model.task && modalities.length > 0);
  }
  if (!releaseStatusKnown(model.release_status)) return false;
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
  if (model.ready === false || !hasQualifiedCapability(model)) return false;
  if (model.model_id.startsWith('mock-') && sourceOrigin !== 'SYNTHETIC') return false;
  const modalities = model.modalities ?? model.supported_modalities ?? [];
  if (modality === 'UWF' && model.model_id === 'prism-dr-5fold') {
    if (model.uwf_use !== 'EXPERIMENTAL'
      || !['NOT_VALIDATED_FOR_UWF', 'NOT_ESTABLISHED'].includes(model.clinical_validation_status ?? '')
      || model.trained_domain !== 'CFP') return false;
  }
  return modalities.includes(modality);
}

export function hasCompatibleModel(item: CaseRecord, models: ModelDescriptor[]): boolean {
  const sourceOrigin = item.source_origin ?? 'UNKNOWN';
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
