import { webcrypto } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { PrismInputPreview } from '@/components/review/PrismInputPreview';
import { loadPreviewAsset, preparationContext, requiresPrismPreview, validatePrismPreview } from '@/lib/prismInputPreview';
import { makePlan, model, pngBytes, pngSha, previewCase } from './fixtures/prismPreview';

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto);
  URL.createObjectURL = vi.fn(() => `blob:synthetic-${Math.random()}`);
  URL.revokeObjectURL = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, arrayBuffer: async () => pngBytes.buffer.slice(0) })));
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('PRISM preview contract is explicit and fails closed', () => {
  it('accepts the unmasked wire fallback without claiming native ROI ran', () => {
    expect(validatePrismPreview(makePlan(), previewCase, model).native_roi_status).toBe('NOT_RUN');
  });
  it.each([
    ['absent', undefined], ['QC-only candidate', { status: 'QC_ONLY' }], ['unavailable', { status: 'UNAVAILABLE' }],
    ['wrong source', { ...makePlan(), source_sha256: '0'.repeat(64) }],
    ['wrong image', { ...makePlan(), image_id: 'other' }],
    ['wrong revision', { ...makePlan(), case_revision: 8 }],
    ['wrong model', { ...makePlan(), model_version: 'other' }],
    ['changed preparation', { ...makePlan(), preparation_context: 'old' }],
    ['expired', { ...makePlan(), expires_at: '2000-01-01T00:00:00Z' }],
    ['candidate adopted', { ...makePlan(), candidate_applied: true }],
    ['final input before native ROI', { ...makePlan(), preview_scope: 'FINAL_MODEL_INPUT' }],
    ['unqualified two-stage claim', { ...makePlan(), preview_scope: 'FINAL_MODEL_INPUT', internal_roi: 'BOUND_IN_PLAN' }],
    ['mask called applied', { ...makePlan(), mask_application: 'APPLIED' }],
    ['native ROI called run', { ...makePlan(), native_roi_status: 'SUCCEEDED' }],
    ['future native crop invented', { ...makePlan(), native_roi_bbox: [0, 0, 1, 1] }],
    ['final tensor invented', { ...makePlan(), final_crop_or_tensor_sha256: pngSha }],
    ['unavailable candidate presented as usable', { ...makePlan(), input_kind: 'UNMASKED_WIRE', mask_application: 'CONDITIONAL_ON_NATIVE_ROI_SUCCESS', mask: { kind: 'OPTICAL_FOV', version: 'fixture', sha256: pngSha } }],
    ['external asset', { ...makePlan(), input_preview: { url: 'https://external.invalid/patient.png', sha256: pngSha, rgb_sha256: pngSha } }],
    ['encoded traversal', { ...makePlan(), original_preview: { url: '/v1/%2e%2e/private.png', sha256: pngSha } }],
    ['missing wire hash', { ...makePlan(), wire_sha256: null }],
    ['singular transform', { ...makePlan(), transform: { ...makePlan().transform, original_to_input: [0, 0, 0, 0, 0, 0] } }],
    ['wrong dimensions', { ...makePlan(), transform: { ...makePlan().transform, original_width: 2 } }],
    ['invalid coverage', { ...makePlan(), excluded_fraction: 0.5 }],
  ])('rejects %s', (_name, plan) => {
    expect(() => validatePrismPreview(plan, previewCase, model)).toThrow();
  });
  it('detects changed candidate mask/version even when case revision is unchanged', () => {
    const changed = { ...previewCase, analysis_preparation: { status: 'NEEDS_REVIEW' as const, candidate_mask_sha256: '1'.repeat(64), candidate_mask_representation_version: 'v4' } };
    expect(preparationContext(changed)).not.toBe(preparationContext(previewCase));
    expect(() => validatePrismPreview(makePlan(), changed, model)).toThrow(/stale/);
  });
  it('recognizes provider aliases as PRISM and preserves synthetic mock models', () => {
    expect(requiresPrismPreview({ ...model, model_id: 'custom', provider_id: 'PRISM' })).toBe(true);
    expect(requiresPrismPreview({ ...model, model_id: 'mock-lesion' })).toBe(false);
  });
});

describe('immutable preview bytes', () => {
  it('verifies bytes before creating a display URL', async () => {
    await expect(loadPreviewAsset(makePlan().input_preview, 1, 1, new AbortController().signal)).resolves.toMatch(/^blob:/);
    expect(fetch).toHaveBeenCalledWith('/v1/preview/wire.png', expect.objectContaining({ method: 'GET', redirect: 'error' }));
  });
  it('rejects a different encoded input instead of showing a hypothetical replacement', async () => {
    await expect(loadPreviewAsset({ ...makePlan().input_preview, sha256: '0'.repeat(64) }, 1, 1, new AbortController().signal)).rejects.toThrow(/bytes changed/);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
  it('rejects incorrect PNG dimensions', async () => {
    await expect(loadPreviewAsset(makePlan().input_preview, 2, 1, new AbortController().signal)).rejects.toThrow(/dimensions/);
  });
  it('rejects excessive decoded dimensions before fetching any bytes', async () => {
    await expect(loadPreviewAsset(makePlan().input_preview, 10000, 10000, new AbortController().signal)).rejects.toThrow(/limit/);
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('single Review UI preparation panel', () => {
  const node = (item = previewCase) => <PrismInputPreview item={item} model={model} />;
  it('shows unavailable honestly and never fetches or submits when no contract exists', () => {
    render(<ChakraProvider>{node()}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    expect(screen.getByText('PRISM input preview unavailable')).toBeInTheDocument();
    expect(screen.getByText(/No PRISM request is sent/)).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('shows Original versus wire input, full-original fallback caveat and separate provenance', async () => {
    render(<ChakraProvider>{node({ ...previewCase, prism_input_preview: makePlan() })}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    expect(await screen.findByAltText('Verified planned input preview')).toBeInTheDocument();
    expect(screen.getByText('Planned API submission')).toBeInTheDocument();
    expect(screen.getByText(/internal model crop not yet previewed/)).toBeInTheDocument();
    expect(screen.getByText(/Native ROI may still crop internally/)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Show conditional FOV overlay' })).toBeDisabled();
    expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true);
  });
  it('keeps conditional FOV candidate separate from actual wire pixels and supports opacity/toggle', async () => {
    const plan = { ...makePlan(), input_kind: 'UNMASKED_WIRE' as const, mask_application: 'CONDITIONAL_ON_NATIVE_ROI_SUCCESS' as const, external_fov_status: 'READY' as const,
      mask: { kind: 'OPTICAL_FOV' as const, version: 'uwf_white_rim_fov_v1', sha256: '1'.repeat(64) },
      overlay: { url: '/v1/preview/overlay.png', sha256: pngSha }, retained_fraction: 0.8, excluded_fraction: 0.1, uncertain_fraction: 0.1 };
    render(<ChakraProvider>{node({ ...previewCase, prism_input_preview: plan })}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    const mask = await screen.findByAltText('Processing overlay in original-image coordinates');
    expect(screen.getByText(/If native ROI fails, the baseline discards the candidate/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Processing overlay opacity'), { target: { value: '25' } });
    expect(mask).toHaveStyle({ opacity: '0.25' });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show conditional FOV overlay' }));
    expect(screen.queryByAltText('Processing overlay in original-image coordinates')).not.toBeInTheDocument();
    expect(screen.getByAltText('Verified planned input preview')).toBeInTheDocument();
  });
  it('hides the previous preview immediately when the source or model changes', async () => {
    const item = { ...previewCase, prism_input_preview: makePlan() };
    const view = render(<ChakraProvider>{node(item)}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    await screen.findByAltText('Verified planned input preview');
    view.rerender(<ChakraProvider><PrismInputPreview item={{ ...item, source_sha256: '2'.repeat(64) }} model={model} /></ChakraProvider>);
    expect(screen.queryByAltText('Verified planned input preview')).not.toBeInTheDocument();
    expect(screen.getByText(/Preview is stale/)).toBeInTheDocument();
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalled());
  });
  it('ignores deferred asset responses after a cross-case switch', async () => {
    const resolve: Array<(value: unknown) => void> = [];
    vi.mocked(fetch).mockImplementation(() => new Promise((done) => { resolve.push(done); }) as Promise<Response>);
    const view = render(<ChakraProvider>{node({ ...previewCase, prism_input_preview: makePlan() })}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    view.rerender(<ChakraProvider><PrismInputPreview item={{ ...previewCase, image_id: 'next', prism_input_preview: undefined }} model={model} /></ChakraProvider>);
    await act(async () => { resolve.forEach((done) => done({ ok: true, arrayBuffer: async () => pngBytes.buffer.slice(0) })); });
    expect(screen.queryByAltText('Verified planned input preview')).not.toBeInTheDocument();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
  it('invalidates a visible preview when it expires', async () => {
    const plan = makePlan();
    render(<ChakraProvider>{node({ ...previewCase, prism_input_preview: plan })}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    await screen.findByAltText('Verified planned input preview');
    const clock = vi.spyOn(Date, 'now').mockReturnValue(Date.parse(plan.expires_at) + 1);
    fireEvent.change(screen.getByLabelText('PRISM preview zoom'), { target: { value: '150' } });
    expect(screen.queryByAltText('Verified planned input preview')).not.toBeInTheDocument();
    expect(screen.getByText(/expired/)).toBeInTheDocument();
    clock.mockRestore();
  });
  it('invalidates displayed assets on decode failure', async () => {
    render(<ChakraProvider>{node({ ...previewCase, prism_input_preview: makePlan() })}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    fireEvent.error(await screen.findByAltText('Verified planned input preview'));
    expect(screen.queryByAltText('Verified planned input preview')).not.toBeInTheDocument();
    expect(screen.getByText(/could not be decoded/)).toBeInTheDocument();
  });
});
