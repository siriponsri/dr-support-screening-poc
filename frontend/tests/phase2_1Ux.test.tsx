import { ChakraProvider } from '@chakra-ui/react';
import { fireEvent, render, screen } from '@testing-library/react';
import { GradeGuide } from '@/components/review/GradeGuide';
import { ReviewStatusCell } from '@/components/worklist/ReviewStatusCell';
import { NextActionHint, contextWarnings, nextAction } from '@/components/common/NextActionHint';
import type { CaseRecord } from '@/lib/api';
import { theme } from '@/theme';

function makeCase(overrides: Partial<CaseRecord> = {}): CaseRecord {
  return {
    image_id: 'phase2-1',
    display_name: 'phase2-1.jpg',
    filename: 'phase2-1.jpg',
    source_type: 'SYNTHETIC',
    source: 'fixture',
    modality: 'CFP',
    width: 640,
    height: 480,
    image_url: null,
    state: 'PENDING',
    revision: 0,
    global: null,
    lesion: null,
    lesion_review: null,
    human_annotations: [],
    clinician_review: null,
    admission: null,
    admission_ui: null,
    ...overrides,
  };
}

describe('M1 Phase 2.1 clinician UX contracts', () => {
  it('exposes the ICO guide progressively with the explicit severe and proliferative criteria', async () => {
    render(<ChakraProvider theme={theme}><GradeGuide /></ChakraProvider>);

    const trigger = screen.getByRole('button', { name: /Grade guide/i });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(trigger);

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByText('0 - No apparent DR')).toBeInTheDocument();
    expect(await screen.findByText('1 - Mild NPDR')).toBeInTheDocument();
    expect(await screen.findByText('2 - Moderate NPDR')).toBeInTheDocument();
    expect(await screen.findByText('3 - Severe NPDR')).toBeInTheDocument();
    expect(await screen.findByText('4 - Proliferative DR (PDR)')).toBeInTheDocument();
    expect(await screen.findByText(/>=20 intraretinal hemorrhages in each of 4 quadrants/i)).toBeInTheDocument();
    expect(await screen.findByText(/neovascularization and\/or vitreous or preretinal hemorrhage/i)).toBeInTheDocument();
    expect(await screen.findByText(/Ungradable and Needs Second Review are workflow states outside the 0-4 severity grades/i)).toBeInTheDocument();
    expect(await screen.findByText(/DME is a separate classification from DR grade/i)).toBeInTheDocument();
  });

  it('separates workflow guidance from context warnings after the grade milestone', () => {
    const item = makeCase({
      clinician_review: {
        reviewer: 'Clinician', final_grade: 2, review_action: 'CORRECT_GRADE', remark: '', timestamp: '', revision: 1,
      },
      resolver_ui: {
        label: 'Patient information needs review', note: 'Confirm context.', tone: 'warning', action_required: true,
        patient: { label: 'Patient not linked', note: 'Confirm patient.', tone: 'warning', action_required: true },
        laterality: { label: 'Eye not confirmed', note: 'Confirm eye.', tone: 'warning', action_required: true, value: 'UNKNOWN' },
      },
    });
    window.localStorage.removeItem('dr-support-screening.next-action-hints.v1');
    render(<ChakraProvider theme={theme}><NextActionHint item={item} /></ChakraProvider>);

    expect(nextAction(item)).toBe('Review findings and finish the case');
    expect(contextWarnings(item)).toContain('Patient and eye context needs confirmation.');
    const hint = screen.getByRole('alert');
    expect(hint).toHaveTextContent('Workflow: Review findings and finish the case');
    expect(hint).toHaveTextContent('Context: Patient and eye context needs confirmation.');
    expect(screen.queryByText(/Confirm image/i)).not.toBeInTheDocument();
  });

  it('keeps complete worklist status compact while retaining accessible detail', () => {
    const item = makeCase({
      clinician_review: {
        reviewer: 'Clinician', final_grade: 2, review_action: 'CORRECT_GRADE', remark: '', timestamp: '', revision: 1,
      },
      annotation_confirmation_status: 'CONFIRMED',
    });
    render(<ChakraProvider theme={theme}><ReviewStatusCell item={item} /></ChakraProvider>);

    expect(screen.getByText('Complete')).toBeInTheDocument();
    expect(screen.getByText('Grade ✓ · Findings ✓')).toBeInTheDocument();
    expect(screen.queryByText('DR grade confirmed · Annotations confirmed')).not.toBeInTheDocument();
  });
});
