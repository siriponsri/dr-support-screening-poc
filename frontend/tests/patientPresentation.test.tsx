import { ChakraProvider } from '@chakra-ui/react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PatientEyeCell } from '@/components/worklist/PatientEyeCell';
import { ResolverDialog } from '@/components/worklist/ResolverDialog';
import { groupCases } from '@/components/worklist/worklistModel';
import { resolverApi, type CaseRecord } from '@/lib/api';
import { patientLabel } from '@/lib/patientPresentation';
import { setDefaultReviewer } from '@/lib/reviewerPreference';
import { theme } from '@/theme';

const key = 'HOSPITAL-' + 'A1'.repeat(12);
const record: CaseRecord = {
  image_id: 'private-synthetic', display_name: 'hospital-case-0001', filename: 'hospital-case-0001.jpg',
  source_type: 'HOSPITAL_AUTHORIZED', source_origin: 'HOSPITAL_AUTHORIZED', source: 'fixture', modality: 'CFP',
  width: 640, height: 480, image_url: null, state: 'PENDING', revision: 1,
  global: null, lesion: null, lesion_review: null, human_annotations: [], clinician_review: null,
  admission: null, admission_ui: null, patient_key: key, patient_display_label: 'Patient 1',
  laterality: 'LEFT', patient_resolution_method: 'AUTHORIZED_SOURCE', laterality_resolution_state: 'RESOLVED',
};
function show(element: React.ReactNode) { return render(<ChakraProvider theme={theme}>{element}</ChakraProvider>); }
beforeEach(() => { window.localStorage.clear(); setDefaultReviewer('Synthetic operator'); });

describe('Workspace patient presentation is separate from identity', () => {
  it('keeps opaque keys out of worklist text, titles and accessible controls', () => {
    const { container } = show(<PatientEyeCell item={record} onResolve={vi.fn()} />);
    expect(screen.getByText('Patient 1 / Left')).toBeInTheDocument();
    expect(container.innerHTML).not.toContain(key);
    expect(patientLabel({ ...record, patient_display_label: undefined })).toBe('Patient linked');
  });
  it('groups by complete identity, never by potentially identical display labels', () => {
    const otherKey = 'HOSPITAL-' + 'B2'.repeat(12);
    const cases = [record, { ...record, image_id: 'current' }, { ...record, image_id: 'other', patient_key: otherKey }];
    const groups = groupCases(cases);
    expect(groups).toHaveLength(2);
    expect(groups[0].eyes[0].cases).toHaveLength(2);
    expect(new Set(groups.map((g) => g.key))).toEqual(new Set([key, otherKey]));
    expect(groups.every((g) => !g.label.includes('HOSPITAL-'))).toBe(true);
  });
  it('uses existing KEEP for eye-only edits and never prefills a generated key', async () => {
    const save = vi.spyOn(resolverApi, 'review').mockResolvedValue(record);
    const user = userEvent.setup();
    show(<ResolverDialog item={record} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(document.body.innerHTML).not.toContain(key);
    expect(screen.queryByLabelText('Pseudonymous patient key')).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Eye'), 'RIGHT');
    await user.click(screen.getByRole('button', { name: 'Save patient / eye' }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(record.image_id, expect.objectContaining({ patient_action: 'KEEP', laterality: 'RIGHT' })));
  });
  it('does not silently unlink when correction is opened and left blank', async () => {
    const save = vi.spyOn(resolverApi, 'review').mockResolvedValue(record);
    const user = userEvent.setup();
    show(<ResolverDialog item={record} onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'Change patient link' }));
    await user.click(screen.getByRole('button', { name: 'Save patient / eye' }));
    expect(save).toHaveBeenLastCalledWith(record.image_id, expect.objectContaining({ patient_action: 'KEEP' }));
    await user.click(screen.getByRole('button', { name: 'Leave this image unlinked' }));
    await user.click(screen.getByRole('button', { name: 'Save patient / eye' }));
    expect(save).toHaveBeenLastCalledWith(record.image_id, expect.objectContaining({ patient_action: 'LEAVE_UNLINKED' }));
  });
  it('requires explicit correction and starts replacement blank', async () => {
    const save = vi.spyOn(resolverApi, 'review').mockResolvedValue(record);
    const user = userEvent.setup();
    show(<ResolverDialog item={record} onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'Change patient link' }));
    expect(screen.getByLabelText('Pseudonymous patient key')).toHaveValue('');
    expect(document.body.innerHTML).not.toContain(key);
    await user.type(screen.getByLabelText('Pseudonymous patient key'), 'demo008');
    await user.click(screen.getByRole('button', { name: 'Save patient / eye' }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(record.image_id, expect.objectContaining({ patient_action: 'SET', patient_key: 'DEMO008' })));
  });
});
