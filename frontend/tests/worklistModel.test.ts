import { describe, expect, it } from 'vitest';
import type { CaseRecord } from '@/lib/api';
import { DEFAULT_FILTERS, filterCases, groupCases, identityNeedsAction, sortCases } from '@/components/worklist/worklistModel';

function makeCase(overrides: Partial<CaseRecord> = {}): CaseRecord {
  return {
    image_id: 'case-1',
    display_name: 'image_01',
    filename: 'image_01.jpg',
    source_type: 'PUBLIC', source: 'WORKSPACE_INPUT', modality: 'CFP', width: 640, height: 480,
    image_url: null, state: 'PENDING', revision: 0, global: null, lesion: null,
    lesion_review: null, human_annotations: [], clinician_review: null, admission: null, admission_ui: null,
    patient_key: null, laterality: 'UNKNOWN', queue_state: 'INCLUDED',
    resolver_ui: {
      label: 'Patient information needs review', note: 'Confirm patient and eye.', tone: 'warning', action_required: true,
      patient: { label: 'Patient not linked', note: 'Link patient.', tone: 'warning', action_required: true },
      laterality: { label: 'Eye not confirmed', note: 'Confirm eye.', tone: 'warning', action_required: true, value: 'UNKNOWN' },
    },
    ...overrides,
  };
}

describe('S3 worklist selectors', () => {
  it('groups only existing patient keys and keeps eye groups distinct', () => {
    const cases = [
      makeCase({ image_id: 'left', display_name: 'left', filename: 'left.jpg', patient_key: 'P0001', laterality: 'LEFT' }),
      makeCase({ image_id: 'right', display_name: 'right', filename: 'right.jpg', patient_key: 'P0001', laterality: 'RIGHT' }),
      makeCase({ image_id: 'unknown', display_name: 'unknown', filename: 'unknown.jpg', patient_key: 'P0001', laterality: 'UNKNOWN' }),
      makeCase({ image_id: 'unlinked', display_name: 'unlinked', filename: 'unlinked.jpg' }),
    ];

    const groups = groupCases(cases);
    expect(groups.map((group) => group.label)).toEqual(['P0001', 'Patient not linked']);
    expect(groups[0].eyes.map((eye) => eye.label)).toEqual(['Left', 'Right', 'Eye not confirmed']);
    expect(groups.flatMap((group) => group.eyes.flatMap((eye) => eye.cases))).toHaveLength(cases.length);
  });

  it('searches filename and patient key, then applies readiness and AI filters', () => {
    const resolved = makeCase({
      image_id: 'resolved', display_name: 'retina-left', filename: 'retina-left.jpg', patient_key: 'PAT0007', laterality: 'LEFT',
      resolver_ui: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false, patient: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false }, laterality: { label: 'Left eye', note: 'Left.', tone: 'success', action_required: false, value: 'LEFT' } },
      global: { model_id: 'model', model_version: '1', modality: 'CFP', state: 'COMPLETE', grade: 2, probabilities: [], confidence: 0.8, warnings: [] },
    });
    const unavailable = makeCase({ image_id: 'unavailable', display_name: 'other', filename: 'other.jpg', admission_ui: { label: 'Cannot analyze', note: 'Unavailable.', tone: 'danger', action_required: false }, resolver_ui: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false, patient: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false }, laterality: { label: 'Left eye', note: 'Left.', tone: 'success', action_required: false, value: 'LEFT' } } });
    const unsupported = makeCase({ image_id: 'unsupported', display_name: 'brain-mri', filename: 'brain-mri.dcm', admission_ui: { label: 'Unsupported modality', note: 'MRI is not supported.', tone: 'danger', action_required: false }, resolver_ui: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false, patient: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false }, laterality: { label: 'Left eye', note: 'Left.', tone: 'success', action_required: false, value: 'LEFT' } } });

    expect(filterCases([resolved, unavailable, unsupported], 'PAT0007', DEFAULT_FILTERS)).toEqual([resolved]);
    expect(filterCases([resolved, unavailable, unsupported], '', { ...DEFAULT_FILTERS, ai: 'analyzed' })).toEqual([resolved]);
    expect(filterCases([resolved, unavailable, unsupported], '', { ...DEFAULT_FILTERS, ai: 'unavailable' })).toEqual([unavailable, unsupported]);
    expect(filterCases([resolved, unavailable, unsupported], '', { ...DEFAULT_FILTERS, readiness: 'identity' })).toEqual([]);
    expect(identityNeedsAction(resolved)).toBe(false);
    expect(identityNeedsAction(makeCase({
      patient_key: 'PAT0008',
      laterality: 'UNKNOWN',
      laterality_resolution_state: 'RESOLVED',
      resolver_ui: {
        label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false,
        patient: { label: 'Patient matched', note: 'Matched.', tone: 'success', action_required: false },
        laterality: { label: 'Eye not confirmed', note: 'Explicitly left unknown.', tone: 'success', action_required: false, value: 'UNKNOWN' },
      },
    }))).toBe(false);
  });

  it('sorts operationally and uses a deterministic filename tie-breaker', () => {
    const right = makeCase({ image_id: 'right', display_name: 'b', filename: 'b.jpg', patient_key: 'P0002', laterality: 'RIGHT' });
    const left = makeCase({ image_id: 'left', display_name: 'a', filename: 'a.jpg', patient_key: 'P0001', laterality: 'LEFT' });
    expect(sortCases([right, left], 'filename').map((item) => item.image_id)).toEqual(['left', 'right']);
    expect(sortCases([right, left], 'patient-eye').map((item) => item.image_id)).toEqual(['left', 'right']);
  });

  it('treats incomplete review states as pending without including excluded cases', () => {
    const pending = makeCase({ image_id: 'pending' });
    const needsAnnotation = makeCase({ image_id: 'needs-annotation', state: 'NEEDS_CORRECTION' });
    const escalated = makeCase({ image_id: 'escalated', state: 'ESCALATED' });
    const reviewed = makeCase({ image_id: 'reviewed', state: 'REVIEWED' });
    const excluded = makeCase({ image_id: 'excluded', queue_state: 'EXCLUDED' });
    const pendingCases = filterCases([pending, needsAnnotation, escalated, reviewed, excluded], '', { ...DEFAULT_FILTERS, review: 'pending' });
    expect(pendingCases.map((item) => item.image_id)).toEqual(['pending', 'needs-annotation', 'escalated']);
  });
});
