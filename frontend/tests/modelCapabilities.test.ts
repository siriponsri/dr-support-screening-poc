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
  it('still enforces known task and modality boundaries when ready is advertised', () => {
    expect(isModelUsable({ ...knownGlobal, task: 'lesion-roi' }, 'CFP', 'PUBLIC')).toBe(false);
    expect(isModelUsable({ ...knownGlobal, modalities: ['CFP', 'UWF'] }, 'UWF', 'PUBLIC')).toBe(false);
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
