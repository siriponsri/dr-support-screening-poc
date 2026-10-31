import { describe, expect, it } from 'vitest';
import { completenessLabel, readinessReasonLabel } from '@/lib/datasetLabels';

describe('dataset readiness labels are plain words, never raw rule codes', () => {
  it.each([
    ['NO_FINAL_CLINICIAN_GRADE', 'No final clinician grade'],
    ['IMAGE_NOT_CONFIRMED', 'Image not confirmed'],
    ['TEST_ONLY_LABEL', 'Test data (not for training)'],
    ['REVIEWED_NONE_FOUND_NOT_AUTHORIZED', 'Reviewed, none found (not a training negative)'],
    ['NO_EXPLICIT_NEGATIVE_POLICY', 'Not a training negative'],
    ['NON_FUNDUS', 'Not a fundus image'],
    ['DUPLICATE_CONTENT', 'Duplicate image'],
    ['SOURCE_INTEGRITY_FAILED', 'Source file changed'],
    ['SOMETHING_NEW_FROM_THE_SERVER', 'Needs review'],
    [null, 'Needs review'],
  ])('%s', (code, label) => {
    expect(readinessReasonLabel(code)).toBe(label);
  });
  it('maps completeness states and keeps the caller fallback when missing', () => {
    expect(completenessLabel('REVIEWED_NONE_FOUND')).toBe('Reviewed, none found');
    expect(completenessLabel(undefined, 'Core not reviewed')).toBe('Core not reviewed');
    expect(completenessLabel('UNKNOWN_STATE')).toBe('Needs review');
  });
});
