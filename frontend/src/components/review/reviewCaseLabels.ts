/** Plain-language labels and small decisions for the Review page (no React state). */
import { isModelUsable } from '@/lib/modelCapabilities';
import { hasInternalPatientKey, patientLabel } from '@/lib/patientPresentation';
import type { CaseRecord, ModelDescriptor } from '@/lib/api';

/** Plain clinician-facing model names; ids and versions stay in Processing details. */
export const MODEL_DISPLAY_NAMES: Record<string, string> = {
  'retfound-aptos5': 'RETFound (CFP grading)',
  'uspec-uwf-grading': 'USPEC (UWF grading)',
  'prism-dr-5fold': 'PRISM (lesion suggestions)',
};

export function modelDisplayName(modelId: string): string {
  return MODEL_DISPLAY_NAMES[modelId] ?? modelId;
}

export function clinicianResultState(state?: string | null) {
  switch (state) {
    case 'AI_SUGGESTION': return 'Model suggestion';
    case 'UNCERTAIN': return 'Uncertain result';
    case 'UNGRADABLE': return 'Image not gradable';
    case 'UNSUPPORTED': return 'Unsupported input';
    default: return state ? 'Result available' : 'Not analyzed';
  }
}

export const LESION_DISPLAY_LABELS: Record<string, string> = {
  MICROANEURYSM: 'Microaneurysm',
  HEMORRHAGE: 'Hemorrhage',
  HARD_EXUDATE: 'Hard exudate',
  SOFT_EXUDATE: 'Soft exudate',
};

export type AnalysisTask = 'global' | 'lesion-roi';

export function caseOrigin(item: CaseRecord | null): string {
  return item ? (item.source_origin ?? 'UNKNOWN') : '';
}

export function selectedModel(
  models: ModelDescriptor[],
  task: AnalysisTask,
  modality: CaseRecord['modality'] | undefined,
  sourceOrigin: string,
): ModelDescriptor | undefined {
  const selected = models
    .filter((model) => model.task === task && isModelUsable(model, modality, sourceOrigin))
    .sort((left, right) => Number(left.model_id.startsWith('mock-')) - Number(right.model_id.startsWith('mock-')))[0];
  return selected;
}

export function admissionAllowsAnalysis(item: CaseRecord | null) {
  return Boolean(
    item?.admission
      && item.admission.modality_admission === 'FUNDUS_ACCEPTED'
      && (item.admission.quality_state === 'GRADABLE' || item.admission.quality_state === 'NOT_EVALUATED'),
  );
}

export function patientEyeContext(item: CaseRecord) {
  const patient = hasInternalPatientKey(item) ? patientLabel(item) : item.patient_key ?? item.patient_candidate ?? item.display_name;
  const eye = item.laterality === 'LEFT' ? 'Left' : item.laterality === 'RIGHT' ? 'Right' : 'Eye not confirmed';
  return `${patient} / ${eye}`;
}

export function sourceOriginLabel(sourceOrigin: CaseRecord['source_origin']): string {
  if (sourceOrigin === 'PUBLIC') return 'Public source';
  if (sourceOrigin === 'SYNTHETIC') return 'Synthetic fixture';
  if (sourceOrigin === 'WORKSPACE') return 'Workspace input';
  if (sourceOrigin === 'HOSPITAL_AUTHORIZED') return 'Approved hospital source';
  return 'Not recorded';
}

export function processingAudit(item: CaseRecord) {
  return item.analysis_preparation?.derivative ?? item.analysis_derivative;
}

export function selectedMaskLabel(item: CaseRecord): string {
  const preparation = item.analysis_preparation;
  const audit = processingAudit(item);
  if (preparation?.status === 'NEEDS_REVIEW') {
    return preparation.candidate_mask_sha256
      ? 'Candidate mask recorded for inspection only; analysis not approved'
      : 'Unavailable - mask needs review; Original/manual review only';
  }
  if (preparation?.status === 'FAILED') {
    return 'Mask preparation failed; Original remains available; PRISM input is not established';
  }
  if (audit?.retinal_field_status === 'READY' && audit.valid_retina_mask_sha256) {
    return 'Retinal-field mask recorded; applied status is not established';
  }
  if (audit?.retinal_field_status === 'NOT_APPLICABLE') {
    return 'No mask recorded; source representation used';
  }
  if (item.modality === 'UWF') {
    return 'Unavailable - no mask record; Original/manual review only';
  }
  return 'Not applicable for this case';
}

export function analysisPreparationNote(item: CaseRecord): string {
  switch (item.analysis_preparation?.status) {
    case 'READY':
      if (processingAudit(item)?.retinal_field_status === 'NOT_APPLICABLE') {
        return 'No mask was recorded; the source representation is the analysis area. Original remains immutable.';
      }
      return 'Analysis area is a versioned, derived view; Original remains immutable.';
    case 'NEEDS_REVIEW':
      return item.analysis_preparation.candidate_mask_sha256
        ? 'A candidate mask is available in Mask preview for inspection only; it is not approved model input.'
        : 'No candidate mask is available; Original and manual review remain available.';
    case 'FAILED':
      return 'Mask preparation failed; Original remains available. A bound preview is required before PRISM submission.';
    default:
      return 'No recorded analysis-area or mask representation is available; Original remains the review source.';
  }
}

export function maskStatus(item: CaseRecord): { label: string; tone: 'success' | 'warning' } {
  if (item.analysis_preparation?.status === 'READY' && processingAudit(item)?.valid_retina_mask_sha256) {
    return { label: 'Ready', tone: 'success' };
  }
  if (item.analysis_preparation?.status === 'NEEDS_REVIEW' && item.analysis_preparation.candidate_mask_sha256) {
    return { label: 'Candidate - review only', tone: 'warning' };
  }
  return { label: 'Unavailable', tone: 'warning' };
}

export function analysisTransformLabel(item: CaseRecord): string {
  return processingAudit(item)?.transform_description ?? 'Unavailable - no transform recorded';
}

export function modelTransformLabel(item: CaseRecord): string {
  const preprocessing = item.global?.provenance?.preprocessing ?? item.lesion?.provenance?.preprocessing;
  if (preprocessing) return preprocessing;
  return item.global || item.lesion
    ? 'Unavailable - model transform not reported'
    : 'Unavailable - no model result recorded';
}

export function modelDomainWarningLabel(item: CaseRecord): string {
  const warnings = [...(item.global?.warnings ?? []), ...(item.lesion?.warnings ?? [])].filter(Boolean);
  if (warnings.length > 0) return warnings.join(' ');
  return item.global || item.lesion
    ? 'No model/domain warning recorded'
    : 'Unavailable - no model result recorded';
}
