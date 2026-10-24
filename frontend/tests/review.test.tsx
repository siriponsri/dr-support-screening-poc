import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { CaseRecord, ModelDescriptor } from '@/lib/api';
import { renderAppAt } from './testUtils';

const readyCase: CaseRecord = {
  image_id: 'ready',
  display_name: 'IMG13',
  filename: 'img13_L1.jpg',
  source_type: 'PUBLIC',
  source_origin: 'PUBLIC',
  source: 'WORKSPACE_INPUT',
  modality: 'CFP',
  width: 640,
  height: 480,
  image_url: null,
  state: 'PENDING',
  revision: 0,
  global: {
    model_id: 'retfound-aptos5',
    model_version: 'fixture',
    modality: 'CFP',
    state: 'AI_SUGGESTION',
    grade: 2,
    probabilities: [],
    confidence: 0.8,
    warnings: [],
  },
  lesion: {
    model_id: 'prism-dr-5fold',
    model_version: 'fixture',
    modality: 'CFP',
    state: 'AI_SUGGESTION',
    width: 640,
    height: 480,
    lesions: [{ detection_id: 'ai-aaaaaaaaaaaaaaaaaaaa', source_label: 'HE', canonical_label: 'HEMORRHAGE', rectangle: [10, 20, 30, 40], score: 0.9, state: 'AI_SUGGESTION' }],
    warnings: [],
  },
  lesion_review: {
    raw_count: 1,
    suggestion_count: 1,
    filtered_count: 0,
    lesions: [{ detection_id: 'ai-aaaaaaaaaaaaaaaaaaaa', source_label: 'HE', canonical_label: 'HEMORRHAGE', rectangle: [10, 20, 30, 40], score: 0.9, state: 'AI_SUGGESTION' }],
    policy: { thresholds: {}, max_per_class: 25, max_total: 80 },
  },
  human_annotations: [],
  clinician_review: null,
  admission: {
    image_id: 'ready',
    source_reference: 'WORKSPACE_INPUT/img13_L1.jpg',
    filename: 'img13_L1.jpg',
    file_extension: '.jpg',
    file_size_bytes: 1200,
    width: 640,
    height: 480,
    channels_or_mode: 'RGB',
    modality_admission: 'FUNDUS_ACCEPTED',
    quality_state: 'NOT_EVALUATED',
    admission_method: 'AUTOMATIC',
    admission_reason_code: 'FUNDUS_CONFIDENT',
    quality_reason_code: null,
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-01T00:00:00+00:00',
    reviewed_by: null,
    reviewed_at: null,
    review_note: null,
  },
  admission_ui: {
    label: 'Ready for analysis',
    note: 'This image can be analyzed.',
    tone: 'success',
    action_required: false,
  },
  patient_key: 'IMG13',
  laterality: 'LEFT',
  resolver_state: 'RESOLVED',
};

const processingCase: CaseRecord = {
  ...readyCase,
  source_origin: 'PUBLIC',
  global: {
    ...readyCase.global!,
    warnings: ['CFP-trained AI - not validated for UWF.'],
    provenance: {
      image_sha256: 'b'.repeat(64),
      source_type: 'PUBLIC',
      preprocessing: 'RGB model transform fixture',
      checkpoint_sha256: {},
      source_revision: 'fixture-v1',
    },
  },
  analysis_preparation: {
    status: 'READY',
    derivative: {
      source_sha256: 'a'.repeat(64),
      source_origin: 'PUBLIC',
      derivative_sha256: 'b'.repeat(64),
      analysis_sha256: 'b'.repeat(64),
      purpose: 'ANALYSIS',
      transform_id: 'analysis-uwf-retinal-mask-v1',
      transform_description: 'Deterministic bounded retinal-field mask',
      transform_version: 1,
      representation_version: 'uwf-analysis-representation-v1',
      analysis_coordinate_space: 'analysis_pixels',
      original_coordinate_space: 'original_image_pixels',
      spatial_mapping_version: 'analysis-to-original-v1',
      valid_retina_mask_sha256: 'c'.repeat(64),
      valid_retina_fraction: 0.6,
      retinal_field_status: 'READY',
      source_dimensions: { width: 640, height: 480, bit_depth: 8, channels: 3 },
      analysis_dimensions: { width: 640, height: 480, bit_depth: 8, channels: 3 },
      coordinate_mapping: {
        kind: 'IDENTITY',
        canonical_width: 640,
        canonical_height: 480,
        analysis_width: 640,
        analysis_height: 480,
        scale_x: 1,
        scale_y: 1,
      },
      lineage: {
        source_sha256: 'a'.repeat(64),
        derivative_sha256: 'b'.repeat(64),
        purpose: 'ANALYSIS',
        format: 'PNG',
        media_type: 'image/png',
        width: 640,
        height: 480,
        bit_depth: 8,
        transform_id: 'analysis-uwf-retinal-mask-v1',
        transform_description: 'Deterministic bounded retinal-field mask',
        coordinate_space: 'analysis_pixels',
        created_at: '2026-01-01T00:00:00Z',
      },
    },
  },
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestPath(input: RequestInfo | URL) {
  if (typeof input === 'string') return new URL(input, window.location.origin).pathname;
  if (input instanceof URL) return input.pathname;
  return new URL(input.url, window.location.origin).pathname;
}

function mockReviewApi(onReview?: (request: Record<string, unknown>) => void, currentCase: CaseRecord = readyCase, models: ModelDescriptor[] = []) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = requestPath(input);
    if (path === '/v1/cases/ready') return jsonResponse(currentCase);
    if (path === '/v1/cases') return jsonResponse([currentCase]);
    if (path === '/v1/infer/global') return jsonResponse({ state: 'AI_SUGGESTION' });
    if (path === '/v1/cases/ready/review') {
      expect(init?.method).toBe('POST');
      const request = JSON.parse(String(init?.body)) as Record<string, unknown>;
      onReview?.(request);
      return jsonResponse({
        ...currentCase,
        revision: 1,
        state: request.action === 'ESCALATE' ? 'ESCALATED' : 'REVIEWED',
        clinician_review: {
          reviewer: 'Review clinician',
          final_grade: request.action === 'ESCALATE' ? null : 2,
          review_action: request.action,
          remark: '',
          timestamp: '2026-01-01T00:00:00+00:00',
          revision: 1,
        },
      });
    }
    if (path === '/v1/models') return jsonResponse(models);
    return jsonResponse({ detail: `Unexpected test request: ${path}` }, 404);
  });
}

describe('Review responsibility boundary', () => {
  it('runs global grading separately and never silently submits PRISM without a bound preview', async () => {
    const requests = mockReviewApi(undefined, readyCase, [
      { model_id: 'retfound-aptos5', task: 'global', modalities: ['CFP'], status: 'LOADED' },
      { model_id: 'prism-dr-5fold', task: 'lesion-roi', modalities: ['CFP'], status: 'LOADED', release_status: 'RESEARCH_ONLY' },
    ]);
    renderAppAt('/review/ready');
    const grading = await screen.findByRole('button', { name: 'Analyze grading only' });
    await userEvent.setup().click(grading);
    await waitFor(() => expect(grading).not.toBeDisabled());
    const mutations = requests.mock.calls.filter(([, options]) => options?.method === 'POST').map(([input]) => requestPath(input));
    expect(mutations).toEqual(['/v1/infer/global']);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Preview PRISM input' }));
    expect(screen.getByText('PRISM input preview unavailable')).toBeInTheDocument();
    expect(requests.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1);
  });

  it('shows unsupported assistance separately from an empty successful lesion result', async () => {
    mockReviewApi(undefined, { ...readyCase, global: { ...readyCase.global!, grade: null, confidence: null, state: 'UNSUPPORTED' }, lesion: { ...readyCase.lesion!, state: 'UNSUPPORTED', lesions: [] } });
    renderAppAt('/review/ready');
    expect((await screen.findAllByText('Unsupported input')).length).toBeGreaterThan(0);
    expect(screen.getByText('Lesion assistance is unavailable for this image. Continue with manual review.')).toBeInTheDocument();
    expect(screen.queryByText('UNSUPPORTED')).not.toBeInTheDocument();
    expect(screen.queryByText('No lesion suggestions')).not.toBeInTheDocument();
  });

  it('does not describe empty AI regions as a negative finding', async () => {
    mockReviewApi(undefined, { ...readyCase, lesion: { ...readyCase.lesion!, lesions: [] } });
    renderAppAt('/review/ready');
    expect(await screen.findByText('No AI regions returned. This does not establish absence of lesions.')).toBeInTheDocument();
  });

  it('keeps eligible analysis available while showing compact read-only context and downstream actions', async () => {
    const user = userEvent.setup();
    let reviewRequest: Record<string, unknown> | undefined;
    mockReviewApi((request) => { reviewRequest = request; }, readyCase, [
      { model_id: 'retfound-aptos5', task: 'global', modalities: ['CFP'], status: 'LOADED', release_status: 'RESEARCH_ONLY' },
      { model_id: 'prism-dr-5fold', task: 'lesion-roi', modalities: ['CFP'], status: 'LOADED', release_status: 'RESEARCH_ONLY' },
    ]);
    renderAppAt('/review/ready');

    expect(await screen.findByText('IMG13 / Left')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeEnabled();
    expect(screen.queryByLabelText('Pseudonymous patient key')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Image admission' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Accept as retinal fundus image/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Continue to clinician review' })).toHaveAttribute('href', '/clinician-review/ready');

    await user.click(screen.getByRole('link', { name: 'Continue to clinician review' }));
    expect(await screen.findByRole('heading', { name: 'Clinician decision' })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('Reviewer name'), 'Review clinician');
    await user.click(await screen.findByRole('radio', { name: /^2 / }));
    await user.click(screen.getByRole('button', { name: 'Grade guide' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('3 - Severe NPDR');
    await user.keyboard('{Escape}');
    expect(screen.getByPlaceholderText('Reviewer name')).toHaveValue('Review clinician');
    expect(screen.getByRole('radio', { name: /^2 / })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getAllByRole('radio')).toHaveLength(6);
    expect(screen.queryByRole('button', { name: 'Send for senior review' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirm DR grade' }));
    expect(reviewRequest).toMatchObject({ action: 'ACCEPT', grade: 2, reviewer: 'Review clinician' });
    expect(await screen.findByRole('button', { name: 'Finish: no findings added (1 AI suggestion not accepted)' })).toBeInTheDocument();
  });

  it('shows recorded mask, transforms, and model-domain warning in Processing details', async () => {
    mockReviewApi(undefined, processingCase);
    renderAppAt('/review/ready');

    expect(await screen.findByText('Retinal-field mask recorded; applied status is not established')).toBeInTheDocument();
    expect(screen.getByText('Deterministic bounded retinal-field mask')).toBeInTheDocument();
    expect(screen.getByText('RGB model transform fixture')).toBeInTheDocument();
    expect(screen.getByText('Separate records; linkage not verified')).toBeInTheDocument();
    expect(screen.getByText('CFP-trained AI - not validated for UWF.')).toBeInTheDocument();
    expect(screen.getByText('Public source')).toBeInTheDocument();
  });

  it('states when processing and model provenance are unavailable', async () => {
    const unavailableCase: CaseRecord = {
      ...readyCase,
      modality: 'UWF',
      image_url: '/v1/images/ready/display',
      global: null,
      lesion: null,
      analysis_preparation: { status: 'FAILED' },
    };
    mockReviewApi(undefined, unavailableCase);
    renderAppAt('/review/ready');

    expect(await screen.findByText('Mask preparation failed; Original remains available; PRISM input is not established')).toBeInTheDocument();
    // Processing views sit behind progressive disclosure.
    expect(screen.queryByLabelText('Mask status')).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'More views' }));
    expect(screen.getByLabelText('Mask status')).toHaveTextContent('Unavailable');
    expect(screen.getByRole('button', { name: 'Mask preview' })).toBeEnabled();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Mask preview' }));
    expect(screen.getByText(/A mask preview is unavailable.*PRISM submission requires/i)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Continue with original' }));
    expect(screen.getByRole('button', { name: 'Original' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Unavailable - no transform recorded')).toBeInTheDocument();
    expect(screen.getAllByText('Unavailable - no model result recorded')).toHaveLength(2);
  });

  it('keeps a needs-review UWF candidate inspectable while disabling analysis input', async () => {
    const needsReviewCase: CaseRecord = {
      ...readyCase,
      modality: 'UWF',
      source_origin: 'WORKSPACE',
      source_type: 'WORKSPACE',
      source: 'WORKSPACE_INPUT',
      image_url: '/v1/images/ready/display',
      global: null,
      lesion: null,
      lesion_review: null,
      analysis_preparation: { status: 'NEEDS_REVIEW', candidate_mask_sha256: 'c'.repeat(64) },
    };
    mockReviewApi(undefined, needsReviewCase);
    renderAppAt('/review/ready');

    await userEvent.setup().click(await screen.findByRole('button', { name: 'More views' }));
    expect(screen.getByText('Candidate - review only')).toBeInTheDocument();
    expect(screen.getByText('A candidate mask is available in Mask preview for inspection only; it is not approved model input.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Analysis area' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Mask preview' })).toBeEnabled();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Mask preview' }));
    expect(screen.getByTestId('mask-overlay')).toHaveAttribute('src', '/v1/images/ready/mask-overlay');
    expect(screen.getByTestId('mask-overlay')).toHaveStyle({ opacity: '0.6', mixBlendMode: 'normal' });
    expect(screen.getByText('Retained retinal area')).toBeInTheDocument();
    expect(screen.getByText('Excluded border / artifact area')).toBeInTheDocument();
    expect(screen.getByText('Mask boundary (retained / excluded edge)')).toBeInTheDocument();
    expect(screen.getByText('Documented processing path (when approved)')).toBeInTheDocument();
    expect(screen.getByText('Original -> Analysis area -> provider transform -> actual model input')).toBeInTheDocument();
    expect(screen.getByText(/candidate mask remains inspection-only/i)).toBeInTheDocument();

    fireEvent.error(screen.getByTestId('mask-overlay'));
    expect(screen.queryByTestId('mask-overlay')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Original' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Mask preview' })).toBeEnabled();
    expect(screen.getByText(/Mask preview unavailable.*original image remains available/i)).toBeInTheDocument();
  });

  it('collapses unavailable model states into the manual-review path', async () => {
    const unavailableCase: CaseRecord = { ...readyCase, global: null, lesion: null, lesion_review: null };
    mockReviewApi(undefined, unavailableCase, [
      { model_id: 'retfound-aptos5', task: 'global', status: 'REMOTE_AUTH_FAILED' },
      { model_id: 'prism-dr-5fold', task: 'lesion-roi', status: 'REMOTE_UNREACHABLE' },
    ]);
    renderAppAt('/review/ready');

    expect(await screen.findByRole('heading', { name: 'AI assistance' })).toBeInTheDocument();
    expect(screen.getAllByText(/Manual review remains available/i)).not.toHaveLength(0);
    expect(screen.queryByRole('heading', { name: 'Analysis' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'DR assessment' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Lesion suggestions' })).not.toBeInTheDocument();
  });

  it('does not infer source origin from source type for model assistance', async () => {
    const unknownOriginCase: CaseRecord = {
      ...readyCase,
      source_origin: undefined,
      global: null,
      lesion: null,
      lesion_review: null,
    };
    mockReviewApi(undefined, unknownOriginCase, [
      { model_id: 'retfound-aptos5', task: 'global', modalities: ['CFP'], status: 'LOADED', release_status: 'RESEARCH_ONLY' },
      { model_id: 'prism-dr-5fold', task: 'lesion-roi', modalities: ['CFP'], status: 'LOADED', release_status: 'RESEARCH_ONLY' },
    ]);
    renderAppAt('/review/ready');

    expect(await screen.findByRole('heading', { name: 'Analysis' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Analyze/ })).toBeDisabled();
    expect(screen.getByText('Not recorded')).toBeInTheDocument();
  });

  it('keeps an incomplete generic UWF capability in the manual-review path', async () => {
    const uwfCase: CaseRecord = {
      ...readyCase,
      modality: 'UWF',
      admission: { ...readyCase.admission!, retinal_modality: 'UWF' },
      global: null,
      lesion: null,
      lesion_review: null,
    };
    mockReviewApi(undefined, uwfCase, [{
      model_id: 'generic-uwf-grader', task: 'global', modalities: ['UWF'], status: 'LOADED', ready: false,
      capability_id: 'dr_grade', model_version: 'unknown', preprocessing_version: 'UNKNOWN',
    }]);
    renderAppAt('/review/ready');

    expect(await screen.findByRole('heading', { name: 'AI assistance' })).toBeInTheDocument();
    expect(screen.getByText('No ready UWF model capability is connected.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Analysis' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Analyze' })).not.toBeInTheDocument();
  });

  it('keeps recorded evidence visible when new model analysis is unavailable', async () => {
    const recordedCase: CaseRecord = {
      ...readyCase,
      image_url: '/v1/images/ready/display',
      explainability: { status: 'UNAVAILABLE', note: 'No explainability receipt was returned for this case.' },
    };
    mockReviewApi(undefined, recordedCase, [
      { model_id: 'retfound-aptos5', task: 'global', status: 'REMOTE_UNREACHABLE' },
      { model_id: 'prism-dr-5fold', task: 'lesion-roi', status: 'REMOTE_UNREACHABLE' },
    ]);
    renderAppAt('/review/ready');

    expect(await screen.findByRole('heading', { name: 'Analysis' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Analyze again' })).toBeDisabled();
    expect(screen.getByRole('heading', { name: 'DR assessment' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Lesion suggestions' })).toBeInTheDocument();
    expect(screen.getByText(/Recorded model evidence remains visible/i)).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole('button', { name: 'More views' }));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Explainability' }));
    expect(screen.getByLabelText('Retinal image viewer stage')).toBeInTheDocument();
    expect(screen.getByText('No explainability receipt was returned for this case.')).toBeInTheDocument();
  });

  it('keeps stored UWF Workspace evidence visible while disabling new analysis', async () => {
    const recordedUwfCase: CaseRecord = {
      ...readyCase,
      modality: 'UWF',
      source_origin: 'WORKSPACE',
      source_type: 'WORKSPACE',
      source: 'WORKSPACE_INPUT',
      image_url: '/v1/images/ready/display',
    };
    mockReviewApi(undefined, recordedUwfCase, [
      { model_id: 'retfound-aptos5', task: 'global', status: 'REMOTE_UNREACHABLE' },
      { model_id: 'prism-dr-5fold', task: 'lesion-roi', status: 'REMOTE_UNREACHABLE' },
    ]);
    renderAppAt('/review/ready');

    expect(await screen.findByRole('heading', { name: 'Analysis' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Analyze again' })).toBeDisabled();
    expect(screen.getByRole('heading', { name: 'DR assessment' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Lesion suggestions' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Moderate NPDR' })).toBeInTheDocument();
    expect(screen.getByText('AI lesion suggestions')).toBeInTheDocument();
    expect(screen.getByText(/Recorded model evidence remains visible/i)).toBeInTheDocument();
  });



  const prismUwfDescriptor: ModelDescriptor = {
    model_id: 'prism-dr-5fold',
    task: 'lesion-roi',
    status: 'LOADED',
    ready: true,
    modalities: ['CFP', 'UWF'],
    capability_id: 'core_lesion_localization',
    revision: '79637440a535e4f8118e939d3787121f82180125',
    preprocessing: 'prism-legacy-cfp-plus-experimental-uwf-v1',
    release_status: 'RESEARCH_ONLY',
    trained_domain: 'CFP',
    uwf_use: 'EXPERIMENTAL',
    clinical_validation_status: 'NOT_VALIDATED_FOR_UWF',
    rights_status: 'ACADEMIC_USE_REVIEW_REQUIRED',
  };

  function prismUwfCase(processingMode: 'PREPARED' | 'FALLBACK'): CaseRecord {
    const imageHash = 'd'.repeat(64);
    const prepared = processingMode === 'PREPARED';
    return {
      ...readyCase,
      modality: 'UWF',
      image_url: '/v1/images/ready/display',
      admission: { ...readyCase.admission!, retinal_modality: 'UWF' },
      global: null,
      lesion: {
        ...readyCase.lesion!,
        modality: 'UWF',
        provenance: {
          image_sha256: imageHash,
          source_type: 'PUBLIC',
          preprocessing: 'PRISM UWF provider input',
          checkpoint_sha256: {},
          source_revision: '79637440a535e4f8118e939d3787121f82180125',
        },
      },
      prism_processing: {
        input_image_sha256: imageHash,
        processing_mode: processingMode,
        native_roi_status: prepared ? 'SUCCEEDED' : 'FAILED',
        native_roi_bbox: prepared ? [8, 12, 632, 468] : null,
        native_roi_failure_code: prepared ? null : 'NO_VALID_NATIVE_ROI',
        external_fov_status: prepared ? 'READY' : 'UNCERTAIN',
        external_fov_reason_code: null,
        fov_used_for_model_input: prepared,
        raw_boundary_classes: prepared ? ['INSIDE_ANALYSIS_FIELD'] : [null],
        analysis_field: prepared ? {
          status: 'READY',
          mask_version: 'uwf_white_rim_fov_v1',
          mask_sha256: 'a'.repeat(64),
          source_rgb_sha256: 'b'.repeat(64),
          image_width: 640,
          image_height: 480,
          boundary_confidence: 0.98,
          excluded_fraction: 0.2,
          boundary: [[32, 240], [160, 40], [480, 40], [608, 240], [480, 440], [160, 440]],
          used_for_model_input: true,
          field_mask_png_base64: 'iVBORw0KGgo=',
        } : null,
      },
    };
  }

  it('shows previous source-bound PRISM field while requiring a new bound input preview', async () => {
    const preparedCase = prismUwfCase('PREPARED');
    mockReviewApi(undefined, preparedCase, [prismUwfDescriptor]);
    renderAppAt('/review/ready');

    expect(await screen.findByLabelText('AI availability')).toHaveTextContent('PRISM PREVIEW REQUIRED');
    expect(screen.queryByText('AI UNAVAILABLE')).not.toBeInTheDocument();
    const fieldButton = screen.getByRole('button', { name: 'PRISM analysis field' });
    expect(fieldButton).toBeEnabled();
    await userEvent.setup().click(fieldButton);

    expect(screen.getByRole('region', { name: 'PRISM Lesion Analysis Field' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Original image, unchanged' })).toHaveAttribute(
      'src', preparedCase.image_url,
    );
    expect(screen.getByRole('img', { name: /PRISM analysis boundary/ })).toHaveAttribute(
      'data-mask-sha256', 'a'.repeat(64),
    );
    expect(screen.getByText('PRISM remains experimental and is not validated for UWF.')).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole('button', { name: 'Show details' }));
    expect(screen.getByText('PREPARED')).toBeInTheDocument();
  });

  it('keeps previous FALLBACK image unbounded and requires a new bound input preview', async () => {
    const fallbackCase = prismUwfCase('FALLBACK');
    mockReviewApi(undefined, fallbackCase, [prismUwfDescriptor]);
    renderAppAt('/review/ready');

    expect(await screen.findByLabelText('AI availability')).toHaveTextContent('PRISM PREVIEW REQUIRED');
    expect(screen.queryByRole('button', { name: 'PRISM analysis field' })).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /PRISM analysis boundary/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Original' })).toHaveAttribute('aria-pressed', 'true');
    const processingMode = screen.getByText('FALLBACK');
    expect(processingMode.closest('#processing-details-panel')).not.toBeNull();
    expect(processingMode).not.toBeVisible();
    expect(screen.getByText('Fallback processing used')).not.toBeVisible();

    await userEvent.setup().click(screen.getByRole('button', { name: 'Show details' }));
    await waitFor(() => {
      expect(processingMode).toBeVisible();
      expect(screen.getByText('Fallback processing used')).toBeVisible();
    });
  });


  it('keeps a legacy escalation record readable without restoring the retired action', async () => {
    const legacy = {
      ...readyCase,
      state: 'ESCALATED' as const,
      clinician_review: {
        reviewer: 'Legacy reviewer',
        final_grade: null,
        review_action: 'ESCALATE' as const,
        remark: 'Historical escalation',
        timestamp: '2026-01-01T00:00:00+00:00',
        revision: 4,
      },
    };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = requestPath(input);
      if (path === '/v1/cases/ready') return jsonResponse(legacy);
      if (path === '/v1/cases') return jsonResponse([legacy]);
      if (path === '/v1/models') return jsonResponse([]);
      return jsonResponse({ detail: `Unexpected test request: ${path}` }, 404);
    });
    renderAppAt('/clinician-review/ready');

    expect(await screen.findByRole('heading', { name: 'Clinician decision' })).toBeInTheDocument();
    expect(screen.getByText('Legacy senior-review record')).toBeInTheDocument();
    expect(screen.getByRole('radiogroup', { name: 'Final DR grade' })).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(6);
  });
});
