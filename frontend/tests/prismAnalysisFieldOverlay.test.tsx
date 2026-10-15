import { ChakraProvider } from '@chakra-ui/react';
import { render, screen } from '@testing-library/react';
import { PrismAnalysisFieldOverlay } from '@/components/review/PrismAnalysisFieldOverlay';
import { theme } from '@/theme';

const readyEvidence = {
  fieldMaskImageUrl: '/field-mask.png',
  maskSha256: 'a'.repeat(64),
  maskVersion: 'uwf_white_rim_fov_v1',
  excludedFraction: 0.28412,
  boundary: [[32, 128], [128, 32], [224, 128], [128, 224]] as const,
};

function renderOverlay(
  status: 'READY' | 'UNCERTAIN' | 'UNAVAILABLE',
  overrides: Partial<typeof readyEvidence> = {},
) {
  return render(
    <ChakraProvider theme={theme}>
      <PrismAnalysisFieldOverlay
        imageUrl="/synthetic-uwf.png"
        imageWidth={256}
        imageHeight={256}
        status={status}
        {...readyEvidence}
        {...overrides}
      />
    </ChakraProvider>,
  );
}

describe('PrismAnalysisFieldOverlay', () => {
  it('renders a formal processing overlay from the supplied mask and contour', () => {
    const { container } = renderOverlay('READY');
    const overlay = screen.getByRole('img', { name: /PRISM analysis boundary/ });

    expect(screen.getByRole('heading', { name: 'PRISM Lesion Analysis Field' })).toBeInTheDocument();
    expect(screen.getByText('Region included in lesion-analysis preprocessing')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Original image, unchanged' })).toHaveAttribute('src', '/synthetic-uwf.png');
    expect(screen.getByText('Included in PRISM lesion analysis')).toBeInTheDocument();
    expect(screen.getByText('Excluded camera rim / outside analysis field')).toBeInTheDocument();
    expect(screen.getByText('PRISM analysis boundary')).toBeInTheDocument();
    expect(screen.getByText('uwf_white_rim_fov_v1')).toBeInTheDocument();
    expect(screen.getByText('28.4%')).toBeInTheDocument();
    expect(screen.getByText('Unchanged')).toBeInTheDocument();
    expect(screen.getByText('Processing evidence only; not anatomical segmentation.')).toBeInTheDocument();
    expect(screen.getByText('PRISM remains experimental and is not validated for UWF.')).toBeInTheDocument();
    expect(screen.getByText('Field prepared')).toBeInTheDocument();

    expect(overlay).toHaveAttribute('data-mask-sha256', 'a'.repeat(64));
    expect(overlay.querySelectorAll('image')).toHaveLength(2);
    expect(Array.from(overlay.querySelectorAll('image')).every((image) => (
      image.getAttribute('href') === '/field-mask.png'
    ))).toBe(true);
    const [includedRegion, excludedRegion] = overlay.querySelectorAll('rect');
    expect(includedRegion).toHaveAttribute('fill-opacity', '0.04');
    expect(excludedRegion).toHaveAttribute('fill-opacity', '0.24');
    expect(overlay.querySelector('mask image[filter]')).toHaveAttribute(
      'filter',
      expect.stringMatching(/^url\(#prismVeilMask-/),
    );
    expect(overlay.querySelector('feGaussianBlur')).toHaveAttribute('stdDeviation', '3.25');
    expect(overlay.querySelector('pattern')).not.toBeInTheDocument();
    const boundaryPaths = Array.from(overlay.querySelectorAll('path'));
    expect(boundaryPaths).toHaveLength(2);
    expect(boundaryPaths.every((path) => (
      path.getAttribute('d') === 'M 32 128 L 128 32 L 224 128 L 128 224 Z'
    ))).toBe(true);
    expect(boundaryPaths[0]).toHaveAttribute('stroke-opacity', '0.4');
    expect(boundaryPaths[1]).toHaveAttribute('stroke-opacity', '0.82');
    expect(boundaryPaths[1]).toHaveAttribute('stroke-width', '1.3');
    expect(boundaryPaths[1]).not.toHaveAttribute('stroke-dasharray');
    expect(container.querySelector('[aria-label="Analysis field legend"]')).toBeInTheDocument();
  });

  it.each([
    ['UNCERTAIN', 'Boundary uncertain'],
    ['UNAVAILABLE', 'Not available'],
  ] as const)(
    'does not display or imply an analysis area when status is %s',
    (status, label) => {
      renderOverlay(status);

      expect(screen.getByRole('img', { name: 'Original image, unchanged' })).toBeInTheDocument();
      expect(screen.queryByRole('img', { name: /PRISM analysis boundary/ })).not.toBeInTheDocument();
      expect(screen.getByText(label, { selector: 'span' })).toBeInTheDocument();
      expect(screen.getByText('A validated PRISM analysis field is unavailable.')).toBeInTheDocument();
      expect(screen.getByText('Unchanged')).toBeInTheDocument();
      expect(screen.getByText('Processing evidence only; not anatomical segmentation.')).toBeInTheDocument();
      expect(screen.queryByText('Included in PRISM lesion analysis')).not.toBeInTheDocument();
    },
  );

  it.each([
    { boundary: [[32, 128], [Number.NaN, 32], [224, 128]] as const },
    { fieldMaskImageUrl: '' },
    { maskSha256: 'not-a-mask-hash' },
    { excludedFraction: 1.1 },
  ])('fails closed when READY mask evidence is invalid: %o', (overrides) => {
    renderOverlay('READY', overrides);

    expect(screen.queryByRole('img', { name: /PRISM analysis boundary/ })).not.toBeInTheDocument();
    expect(screen.getByText('Boundary unavailable')).toBeInTheDocument();
    expect(screen.getByText('A validated PRISM analysis field is unavailable.')).toBeInTheDocument();
  });
});
