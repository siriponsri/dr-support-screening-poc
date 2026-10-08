import { ChakraProvider } from '@chakra-ui/react';
import { render, screen, waitForElementToBeRemoved } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { GradeGuide } from '@/components/review/GradeGuide';
import { ReviewStatusCell } from '@/components/worklist/ReviewStatusCell';
import { GuideHint } from '@/components/common/GuideHint';
import { ReviewerPreference } from '@/components/settings/ReviewerPreference';
import { getGuideModeEnabled, setGuideModeEnabled } from '@/lib/hintPreference';
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
  it('opens the ICO guide as a focus-managed dialog with the explicit severe and proliferative criteria', async () => {
    const user = userEvent.setup();
    render(<ChakraProvider theme={theme}><GradeGuide /></ChakraProvider>);

    const trigger = screen.getByRole('button', { name: /Grade guide/i });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(trigger);

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('ICO diabetic retinopathy grade guide');
    expect(await screen.findByText('0 - No apparent DR')).toBeInTheDocument();
    expect(await screen.findByText('1 - Mild NPDR')).toBeInTheDocument();
    expect(await screen.findByText('2 - Moderate NPDR')).toBeInTheDocument();
    expect(await screen.findByText('3 - Severe NPDR')).toBeInTheDocument();
    expect(await screen.findByText('4 - Proliferative DR (PDR)')).toBeInTheDocument();
    expect(await screen.findByText(/>=20 intraretinal hemorrhages in each of 4 quadrants/i)).toBeInTheDocument();
    expect(await screen.findByText(/neovascularization and\/or vitreous or preretinal hemorrhage/i)).toBeInTheDocument();
    expect(await screen.findByText(/NVD.*NVE.*iris or anterior segment.*fibrous proliferation/i)).toBeInTheDocument();
    expect(await screen.findByText(/Ungradable and Needs Second Review are workflow states outside the 0-4 severity grades/i)).toBeInTheDocument();
    expect(await screen.findByText(/DME is a separate classification from DR grade/i)).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitForElementToBeRemoved(() => screen.queryByRole('dialog'));
    expect(trigger).toHaveFocus();
  });

  it('defaults Guide mode to ON and turns it off persistently without changing case data', async () => {
    const user = userEvent.setup();
    const item = makeCase({ clinician_review: null, human_annotations: [] });
    const originalCase = structuredClone(item);
    window.localStorage.clear();
    const renderGuide = () => render(<ChakraProvider theme={theme}><GuideHint step="grade" /></ChakraProvider>);

    expect(getGuideModeEnabled()).toBe(true);
    const first = renderGuide();
    expect(screen.getByTestId('guide-hint')).toHaveTextContent('Choose the final physician grade; AI is only a suggestion.');
    await user.click(screen.getByRole('button', { name: 'Turn off Guide mode' }));
    expect(getGuideModeEnabled()).toBe(false);
    first.unmount();

    renderGuide();
    expect(screen.queryByTestId('guide-hint')).not.toBeInTheDocument();
    expect(item).toEqual(originalCase);
  });

  it('re-enables Guide mode from Settings after an OFF preference', async () => {
    const user = userEvent.setup();
    setGuideModeEnabled(false);
    const screenView = render(<ChakraProvider theme={theme}><GuideHint step="review" /></ChakraProvider>);
    expect(screen.queryByTestId('guide-hint')).not.toBeInTheDocument();
    screenView.unmount();
    render(<ChakraProvider theme={theme}><ReviewerPreference /></ChakraProvider>);

    const control = screen.getByRole('checkbox', { name: 'Guide mode' });
    expect(control).not.toBeChecked();
    await user.click(control);
    expect(getGuideModeEnabled()).toBe(true);
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
