import { describe, expect, it } from 'vitest';
import { drGradeLabel, type CaseRecord } from '@/lib/api';
import { reviewState } from '@/components/worklist/worklistModel';

const base = { queue_state: 'INCLUDED', state: 'PENDING', clinician_review: null } as CaseRecord;

describe('Chunk A grade states', () => {
  it('uses descriptive DR labels while keeping numeric compatibility values', () => {
    expect(drGradeLabel(0)).toBe('No apparent DR');
    expect(drGradeLabel(1)).toBe('Mild NPDR');
    expect(drGradeLabel(2)).toBe('Moderate NPDR');
    expect(drGradeLabel(3)).toBe('Severe NPDR');
    expect(drGradeLabel(4)).toBe('Proliferative DR');
  });

  it('keeps Ungradable and Needs Second Review distinct from confirmed grading', () => {
    expect(reviewState({ ...base, grade_status: 'UNGRADABLE' })).toBe('ungradable');
    expect(reviewState({ ...base, grade_status: 'NEEDS_SECOND_REVIEW' })).toBe('needs-second-review');
    expect(reviewState({ ...base, grade_status: 'CONFIRMED', state: 'REVIEWED', clinician_review: {
      reviewer: 'Fixture', final_grade: 2, review_action: 'CORRECT_GRADE', remark: '', timestamp: '2026-01-01T00:00:00Z', revision: 1,
    } })).toBe('reviewed');
  });

  it('keeps historical Unknown readable without treating it as a grade', () => {
    expect(reviewState({ ...base, grade_status: 'UNKNOWN' })).toBe('legacy-unknown');
  });
});
