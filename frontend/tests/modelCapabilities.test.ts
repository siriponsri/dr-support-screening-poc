import { describe, expect, it } from 'vitest';
import type { ModelDescriptor } from '@/lib/api';
import { isModelUsable } from '@/lib/modelCapabilities';

const knownGlobal: ModelDescriptor = {
  model_id: 'retfound-aptos5',
  task: 'global',
  status: 'LOADED',
  ready: true,
  modalities: ['CFP'],
};

describe('model capability routing guard', () => {
  it('preserves legacy CFP RETFound discovery and enforces fixed modalities', () => {
    expect(isModelUsable(knownGlobal, 'CFP', 'PUBLIC')).toBe(true);
    expect(isModelUsable({ ...knownGlobal, task: 'lesion-roi' }, 'CFP', 'PUBLIC')).toBe(false);
    expect(isModelUsable({ ...knownGlobal, modalities: ['CFP', 'UWF'] }, 'UWF', 'PUBLIC')).toBe(false);
  });

  it('routes CFP global grading to RETFound and UWF global grading to USPEC only', () => {
    const retfound: ModelDescriptor = {
      ...knownGlobal,
      release_status: 'RESEARCH_ONLY',
      capability_id: 'dr_grade',
      revision: 'retfound-locked-revision',
      preprocessing: 'retfound-cfp-v1',
    };
    const uspec: ModelDescriptor = {
      model_id: 'uspec-uwf-grading',
      task: 'global',
      status: 'QUALIFIED_NOT_LOADED',
      ready: true,
      modalities: ['UWF'],
      capability_id: 'dr_grade',
      revision: 'grading_state.pt-sha256:locked',
      preprocessing: 'uspec-source-rgb-v1',
      release_status: 'RESEARCH_ONLY',
      runtime_qualification: 'ENGINEERING_QUALIFIED',
      rights_status: 'UNVERIFIED',
      clinical_validation_status: 'NOT_ESTABLISHED',
      production_authorization: 'NOT_AUTHORIZED',
    };

    expect(isModelUsable(retfound, 'CFP', 'PUBLIC')).toBe(true);
    expect(isModelUsable(retfound, 'UWF', 'PUBLIC')).toBe(false);
    expect(isModelUsable(uspec, 'UWF', 'PUBLIC')).toBe(true);
    expect(isModelUsable(uspec, 'CFP', 'PUBLIC')).toBe(false);
    expect(isModelUsable({ ...uspec, modalities: ['UWF', 'CFP'] }, 'UWF', 'PUBLIC')).toBe(false);
    expect(isModelUsable({ ...uspec, task: 'lesion-roi' }, 'UWF', 'PUBLIC')).toBe(false);
  });

  it.each(['CFP', 'UWF'] as const)('keeps PRISM lesion capability explicitly experimental for %s', (modality) => {
    const prism: ModelDescriptor = {
      model_id: 'prism-dr-5fold',
      task: 'lesion-roi',
      status: 'LOADED',
      ready: true,
      modalities: ['CFP', 'UWF'],
      capability_id: 'core_lesion_localization',
      revision: '79637440a535e4f8118e939d3787121f82180125',
      preprocessing: 'prism-legacy-cfp-plus-experimental-uwf-v1',
      release_status: 'RESEARCH_ONLY',
      trained_domain: 'CFP',
      uwf_use: 'EXPERIMENTAL',
      clinical_validation_status: 'NOT_VALIDATED_FOR_UWF',
    };
    expect(isModelUsable(prism, modality, 'PUBLIC')).toBe(true);
    expect(isModelUsable({ ...prism, uwf_use: 'UNRESTRICTED' }, 'UWF', 'PUBLIC')).toBe(false);
  });

  it('requires qualification metadata for ready generic capabilities', () => {
    const incomplete: ModelDescriptor = {
      model_id: 'generic-uwf-grader',
      task: 'global',
      status: 'LOADED',
      ready: true,
      modalities: ['UWF'],
      release_status: 'QUALIFIED',
    };
    const complete: ModelDescriptor = {
      ...incomplete,
      capability_id: 'uwf-grade',
      revision: 'r1',
      preprocessing: 'uwf-v1',
    };
    expect(isModelUsable(incomplete, 'UWF', 'PUBLIC')).toBe(false);
    expect(isModelUsable(complete, 'UWF', 'PUBLIC')).toBe(true);
  });
});
