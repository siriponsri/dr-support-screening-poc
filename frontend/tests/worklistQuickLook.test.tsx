import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderAppAt } from './testUtils';
import type { CaseRecord } from '@/lib/api';

function makeCase(id: string, overrides: Partial<CaseRecord> = {}): CaseRecord {
  return {
    image_id: id, display_name: id, filename: `${id}.png`,
    source_type: 'SYNTHETIC', source_origin: 'SYNTHETIC', source: 'fixture', modality: 'CFP',
    width: 640, height: 480, image_url: `/v1/images/${id}/display`,
    state: 'PENDING', revision: 1, global: null, lesion: null, lesion_review: null,
    human_annotations: [], clinician_review: null, admission: null, admission_ui: null,
    patient_key: 'PAT001', laterality: 'LEFT', queue_state: 'INCLUDED',
    ...overrides,
  };
}

const notStarted = makeCase('synthetic-new');
const doneGrade2 = makeCase('synthetic-done', {
  admission_history: [{ action: 'CONFIRM_IMAGE' }],
  grade_status: 'CONFIRMED', annotation_confirmation_status: 'CONFIRMED',
  clinician_review: { final_grade: 2, reviewer: 'Dr. Example', timestamp: '2026-01-02T00:00:00Z', revision: 3 } as CaseRecord['clinician_review'],
  annotation_completeness: { CORE: { state: 'REVIEWED_NONE_FOUND' } } as CaseRecord['annotation_completeness'],
});
const doneGrade4 = makeCase('synthetic-done-4', {
  grade_status: 'CONFIRMED', annotation_confirmation_status: 'CONFIRMED',
  clinician_review: { final_grade: 4, reviewer: 'Dr. Example', timestamp: '2026-01-02T00:00:00Z', revision: 3 } as CaseRecord['clinician_review'],
});

function reply(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

function mockApi() {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
    if (path === '/v1/workspaces') return reply({ workspaces: [], active_workspace_id: null, active_workspace: null, warnings: [] });
    if (path === '/v1/workspaces/active') return reply({ workspace: null, database: { path: '', status: 'fallback' }, warnings: [] });
    if (path === '/v1/cases') return reply([notStarted, doneGrade2, doneGrade4]);
    return reply([]);
  });
}

describe('Worklist quick filter and quick look', () => {
  it('filters by status with counts and narrows done cases by final grade', async () => {
    const user = userEvent.setup();
    mockApi();
    renderAppAt('/worklist');
    const statusGroup = await screen.findByRole('group', { name: 'Filter by status' });
    expect(within(statusGroup).getByRole('button', { name: /Not started\s*1/ })).toBeInTheDocument();
    expect(within(statusGroup).getByRole('button', { name: /Done\s*2/ })).toBeInTheDocument();

    await user.click(within(statusGroup).getByRole('button', { name: /Done/ }));
    expect(screen.queryByTestId('case-row-synthetic-new')).not.toBeInTheDocument();
    const gradeGroup = screen.getByRole('group', { name: 'Filter done cases by final grade' });
    await user.click(within(gradeGroup).getByRole('button', { name: /Grade 4\s*1/ }));
    expect(screen.getByTestId('case-row-synthetic-done-4')).toBeInTheDocument();
    expect(screen.queryByTestId('case-row-synthetic-done')).not.toBeInTheDocument();
    expect(within(screen.getByTestId('case-row-synthetic-done-4')).getByText('Grade 4')).toBeInTheDocument();
  });

  it('opens a read-only quick look with the image and clinician record', async () => {
    const user = userEvent.setup();
    mockApi();
    renderAppAt('/worklist');
    const row = await screen.findByTestId('case-row-synthetic-done');
    await user.click(within(row).getByRole('button', { name: 'Quick look: synthetic-done.png' }));
    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('Grade 2: Moderate NPDR')).toBeInTheDocument();
    expect(within(drawer).getByText('Reviewed, none recorded')).toBeInTheDocument();
    expect(within(drawer).getByRole('link', { name: 'Open review' })).toHaveAttribute('href', '/review/synthetic-done');
    expect(within(row).queryByText('AI ready')).not.toBeInTheDocument();
  });
});
