import type { CaseRecord } from './api';

export interface QaBatchContext {
  enabled: true;
  job_id: string;
  image_id: string;
  source_sha256: string;
  model_id: string;
  modality: 'CFP' | 'UWF';
  task: 'global' | 'lesion-roi';
  technical_only: true;
  clinical_use: false;
  one_attempt_max: true;
  quality_state: string | null;
  permitted_action: 'GLOBAL_ONCE' | 'PRISM_PREVIEW_ONCE';
  invocation_id: string | null;
}

/** This is display scope, not authority. The app profile enforces every call. */
export function validatedQaBatchContext(value: unknown, item: CaseRecord): QaBatchContext | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const context = value as Record<string, unknown>;
  const digest = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
  if (context.enabled !== true || context.technical_only !== true || context.clinical_use !== false
    || context.one_attempt_max !== true || !digest(context.job_id) || !digest(item.source_sha256)
    || context.image_id !== item.image_id || context.source_sha256 !== item.source_sha256
    || context.image_id !== context.source_sha256 || context.modality !== item.modality
    || context.quality_state !== (item.admission?.quality_state ?? null)) return null;
  if (context.model_id === 'prism-dr-5fold') {
    if (context.task !== 'lesion-roi' || context.permitted_action !== 'PRISM_PREVIEW_ONCE') return null;
  } else {
    if (!['uspec-uwf-grading', 'retfound-aptos5'].includes(String(context.model_id))
      || context.task !== 'global' || context.permitted_action !== 'GLOBAL_ONCE'
      || context.invocation_id !== `batch-${context.job_id.slice(0, 40)}`
      || (context.model_id === 'uspec-uwf-grading' ? item.modality !== 'UWF' : item.modality !== 'CFP')) return null;
  }
  return context as unknown as QaBatchContext;
}
