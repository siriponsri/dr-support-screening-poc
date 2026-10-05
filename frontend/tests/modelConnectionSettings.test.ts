import { describe, expect, it } from 'vitest';
import { releaseStatusView } from '@/components/settings/ModelConnectionSettings';

describe('model connection release state labels', () => {
  it('keeps release state plain-language and visible for known boundaries', () => {
    expect(releaseStatusView('RESEARCH_ONLY')).toEqual({ label: 'Research use', tone: 'info' });
    expect(releaseStatusView('BLOCKED_ARTIFACT')).toEqual({ label: 'Blocked for review', tone: 'warning' });
    expect(releaseStatusView('DEFERRED_NO_QUALIFIED_CANDIDATE')).toEqual({ label: 'Deferred', tone: 'warning' });
    expect(releaseStatusView(null)).toEqual({ label: 'Not stated', tone: 'warning' });
  });
});
