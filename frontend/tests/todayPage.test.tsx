import { describe, expect, it } from 'vitest';
import { todayCounts } from '@/pages/TodayPage';
import type { CaseRecord } from '@/lib/api';

const confirmed = { admission_history: [{ action: 'CONFIRM_IMAGE' }] };

function item(id: string, extra: Record<string, unknown>): CaseRecord {
  return { image_id: id, ...extra } as unknown as CaseRecord;
}

describe('Today counts', () => {
  it('separates waiting for AI, to review, reviewed and needs attention', () => {
    const counts = todayCounts([
      item('new', { admission_history: [] }),
      item('noai', { ...confirmed, global: null, lesion: null }),
      item('ai1', { ...confirmed, global: { grade: 2 }, lesion: null }),
      item('ai2', { ...confirmed, global: { grade: 1 }, lesion: { detections: [] } }),
      item('done', { ...confirmed, global: { grade: 2 }, clinician_review: { final_grade: 3 }, grade_status: 'CONFIRMED',
        annotation_confirmation_status: 'CONFIRMED' }),
      item('gradeonly', { ...confirmed, global: { grade: 2 }, clinician_review: { final_grade: 2 }, grade_status: 'CONFIRMED',
        annotation_confirmation_status: 'DRAFT' }),
    ]);
    expect(counts).toEqual({ total: 6, toReview: 3, waitingForAi: 1, reviewed: 1, needsAttention: 1, nextToReview: 'ai1' });
  });
});
