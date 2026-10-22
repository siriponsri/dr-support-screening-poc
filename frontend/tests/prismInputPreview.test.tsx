import { webcrypto } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import userEvent from '@testing-library/user-event';
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
  it('keeps PRISM unavailable while the independent CPU field makes no model calls', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: false, status: 404 } as Response);
    render(<ChakraProvider>{node()}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    expect(screen.getByText('PRISM input preview unavailable')).toBeInTheDocument();
    expect(screen.getByText(/PRISM cannot be submitted without a verified receipt/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('artifact-field-preview')).not.toBeInTheDocument());
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledWith('/v1/cases/synthetic-preview/artifact-roi/field',
      expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }));
    expect(vi.mocked(fetch).mock.calls.every(([, options]) => (options?.method ?? 'GET') === 'GET')).toBe(true);
    expect(screen.queryByRole('button', { name: 'Submit prepared input to PRISM' })).not.toBeInTheDocument();
  });
  it('shows Original versus wire input, full-original fallback caveat and separate provenance', async () => {
    render(<ChakraProvider>{node({ ...previewCase, prism_input_preview: makePlan() })}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    expect(await screen.findByAltText('Verified planned input preview')).toBeInTheDocument();
    expect(screen.getByText('Planned API submission')).toBeInTheDocument();
    expect(screen.getByText('Planned API input — internal model crop not previewed')).toBeInTheDocument();
    expect(screen.getByText(/Native ROI may still crop internally/)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Show conditional FOV overlay' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'Show conditional FOV overlay' })).not.toBeChecked();
    expect(vi.mocked(fetch).mock.calls.every(([, options]) => (options?.method ?? 'GET') === 'GET')).toBe(true);
  });
  it('does not offer submission for a display-only fixture even when all PNG bytes verify', async () => {
    render(<ChakraProvider>{node({ ...previewCase, prism_input_preview: makePlan() })}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    await screen.findByAltText('Verified planned input preview');
    expect(screen.queryByRole('button', { name: 'Submit prepared input to PRISM' })).not.toBeInTheDocument();
    expect(screen.getByText(/does not attest backend execution binding/)).toBeInTheDocument();
  });
  it('submits only verified plan fields once, using keyboard acknowledgement, and records no clinical decision', async () => {
    const complete = vi.fn();
    const plan = { ...makePlan(), submission_binding_enforced: true };
    vi.mocked(fetch).mockImplementation(async (_url, init) => init?.method === 'POST'
      ? ({ ok: true, json: async () => ({ state: 'AI_SUGGESTION' }) } as Response)
      : ({ ok: true, arrayBuffer: async () => pngBytes.buffer.slice(0) } as Response));
    render(<ChakraProvider><PrismInputPreview item={{ ...previewCase, prism_input_preview: plan }} model={model} onInferenceComplete={complete} /></ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    await screen.findByAltText('Verified planned input preview');
    const button = screen.getByRole('button', { name: 'Submit prepared input to PRISM' });
    expect(button).toBeDisabled();
    const acknowledgement = screen.getByRole('checkbox', { name: /I inspected the planned API input/ });
    act(() => acknowledgement.focus());
    await userEvent.setup().keyboard(' ');
    expect(button).toBeEnabled();
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(complete).toHaveBeenCalledOnce());
    const posts = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST');
    expect(posts).toHaveLength(1);
    expect(posts[0][0]).toBe('/v1/cases/synthetic-preview/prism-input-preview/synthetic-plan/infer');
    expect(JSON.parse(String(posts[0][1]?.body))).toEqual({ revision: 7, source_sha256: plan.source_sha256,
      wire_sha256: plan.wire_sha256, plan_sha256: plan.plan_sha256, mask_sha256: null,
      transform_sha256: plan.transform.sha256, model_version: plan.model_version });
    expect(button).toBeDisabled();
  });
  it('does not replay a failed invocation and requires a new preparation', async () => {
    const plan = { ...makePlan(), submission_binding_enforced: true };
    vi.mocked(fetch).mockImplementation(async (_url, init) => init?.method === 'POST'
      ? ({ ok: false, json: async () => ({ detail: 'Synthetic timeout' }) } as Response)
      : ({ ok: true, arrayBuffer: async () => pngBytes.buffer.slice(0) } as Response));
    render(<ChakraProvider>{node({ ...previewCase, prism_input_preview: plan })}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    await screen.findByAltText('Verified planned input preview');
    fireEvent.click(screen.getByRole('checkbox', { name: /I inspected/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Submit prepared input to PRISM' }));
    expect(await screen.findByText(/Synthetic timeout/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Submit prepared input to PRISM' })).toBeDisabled();
    expect(vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  });
  it('prepares through the CPU route and verifies returned assets before enabling acknowledgement', async () => {
    const plan = { ...makePlan(), submission_binding_enforced: true };
    vi.mocked(fetch).mockImplementation(async (_url, init) => init?.method === 'POST'
      ? ({ ok: true, json: async () => plan } as Response)
      : ({ ok: true, arrayBuffer: async () => pngBytes.buffer.slice(0) } as Response));
    render(<ChakraProvider>{node()}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    fireEvent.click(screen.getByRole('button', { name: 'Prepare / refresh API input' }));
    await screen.findByAltText('Verified planned input preview');
    const posts = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST');
    expect(posts).toHaveLength(1);
    expect(posts[0][0]).toBe('/v1/cases/synthetic-preview/prism-input-preview');
    expect(JSON.parse(String(posts[0][1]?.body))).toEqual({ revision: 7, model_id: model.model_id });
    expect(screen.getByRole('button', { name: 'Submit prepared input to PRISM' })).toBeDisabled();
  });
  it('ignores a deferred preparation response after a case switch and clears loading ownership', async () => {
    let resolve!: (value: unknown) => void;
    vi.mocked(fetch).mockImplementation(() => new Promise((done) => { resolve = done; }) as Promise<Response>);
    const view = render(<ChakraProvider>{node()}</ChakraProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    fireEvent.click(screen.getByRole('button', { name: 'Prepare / refresh API input' }));
    view.rerender(<ChakraProvider>{node({ ...previewCase, image_id: 'next-case' })}</ChakraProvider>);
    await act(async () => { resolve({ ok: true, json: async () => ({ ...makePlan(), submission_binding_enforced: true }) }); });
    expect(screen.queryByAltText('Verified planned input preview')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Submit prepared input to PRISM' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Prepare / refresh API input' })).toBeEnabled();
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
