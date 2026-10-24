import { ChakraProvider } from '@chakra-ui/react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { CaseRecord } from '@/lib/api';
import { annotationAssistLesions, artifactVisibilityCounts } from '@/lib/artifactRoiAssist';
import { ArtifactRoiControls } from '@/components/review/ArtifactRoiControls';

function fixture(): CaseRecord {
  return {
    image_id: 'A', source_sha256: 'a'.repeat(64), display_name: 'Synthetic A', filename: null,
    source_type: 'SYNTHETIC', source: 'generated fixture', modality: 'UWF', width: 640, height: 480,
    image_url: null, state: 'PENDING', revision: 1, global: null, human_annotations: [],
    clinician_review: null, admission: null, admission_ui: null, lesion_review: null,
    lesion: { model_id: 'prism-dr-5fold', model_version: 'fixture', modality: 'UWF', state: 'AI_SUGGESTION',
      width: 640, height: 480, warnings: [], lesions: [
        { detection_id: 'roi-a', source_label: 'MA', canonical_label: 'MICROANEURYSM', rectangle: [0, 0, 5, 5], score: .9, state: 'AI_SUGGESTION' },
        { detection_id: 'roi-b', source_label: 'HE', canonical_label: 'HEMORRHAGE', rectangle: [100, 100, 110, 110], score: .8, state: 'AI_SUGGESTION' },
      ] },
    artifact_roi_assist: { enabled: true, status: 'READY', binding_sha256: 'b'.repeat(64),
      scope_sha256: 'd'.repeat(64),
      policy_version: 'annotation-artifact-visibility.v1',
      input_binding: { image_id: 'A', source_sha256: 'a'.repeat(64), raw_result_sha256: 'c'.repeat(64), width: 640, height: 480 },
      suppressed_ids: ['roi-a'], visible_ids: ['roi-b'], suppressed: [{ detection_id: 'roi-a', reason: 'SURE_EXCLUDED_ARTIFACT' }],
      restored_ids: [], overlay_url: '/v1/cases/A/artifact-roi/overlay?binding_sha256=fixture',
      provenance_class: 'NON_GOLD_AI_VISIBILITY_ONLY', negative_labels_from_suppression: false },
  };
}

function controls(item: CaseRecord, change = vi.fn(), show = vi.fn(), overlay = vi.fn()) {
  return <ChakraProvider><ArtifactRoiControls item={item} showFiltered={false} showOverlay={false}
    onShowFiltered={show} onShowOverlay={overlay} onCaseChange={change} /></ChakraProvider>;
}

describe('annotation-assist visibility', () => {
  it('identifies the saved ROI post-filter field and policy without claiming model input masking', async () => {
    const item = fixture(); const overlay = vi.fn();
    const fetch = vi.spyOn(globalThis, 'fetch');
    render(controls(item, vi.fn(), vi.fn(), overlay));
    expect(screen.getByText('ROI post-filter: 1 ROI suggestion hidden')).toBeInTheDocument();
    expect(screen.getByText(/After inference: changes ROI visibility only/)).toHaveTextContent('Original and model input are unchanged');
    expect(screen.getByText('Review suggestions shown: 1 of 2. Raw model ROIs retained: 2.')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Post-filter decision details'));
    expect(screen.getByText(item.artifact_roi_assist!.policy_version)).toBeVisible();
    expect(screen.getByText(item.artifact_roi_assist!.binding_sha256!)).toBeVisible();
    expect(screen.getByText('The overlay uses the saved, source-bound decision field.')).toBeVisible();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Show saved post-filter field' }));
    expect(overlay).toHaveBeenCalledWith(true);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('counts the effective layer separately from the full raw prediction and protects physician decisions', () => {
    const item = fixture();
    item.lesion!.lesions.push({ ...item.lesion!.lesions[1], detection_id: 'raw-only' });
    item.lesion_review = { lesions: item.lesion!.lesions.slice(0, 2), raw_count: 3 } as CaseRecord['lesion_review'];
    const before = JSON.stringify(item);
    expect(artifactVisibilityCounts(item)).toEqual({
      rawPredictionCount: 3, reviewSuggestionCount: 2, shownCount: 1, hiddenCount: 1, filteredCount: 1,
    });
    expect(artifactVisibilityCounts(item, true)).toEqual({
      rawPredictionCount: 3, reviewSuggestionCount: 2, shownCount: 2, hiddenCount: 0, filteredCount: 1,
    });
    expect(JSON.stringify(item)).toBe(before);
    item.review_evidence = { status: 'REVIEWED', reviewer: null, timestamp: null, summary: {},
      unresolved_count: 0, items: [{ annotation_id: 'roi-a', source: 'AI', label: 'MICROANEURYSM',
        score: .9, status: 'CLINICIAN_CONFIRMED', model_id: 'prism-dr-5fold', model_version: 'fixture',
        reviewer: 'synthetic reviewer', timestamp: null }] } as CaseRecord['review_evidence'];
    expect(artifactVisibilityCounts(item)).toMatchObject({ shownCount: 2, hiddenCount: 0, filteredCount: 0 });
  });

  it('updates visibility counts when filtered suggestions are shown without changing saved predictions', () => {
    const item = fixture(); const before = JSON.stringify(item);
    const mounted = render(controls(item));
    mounted.rerender(<ChakraProvider><ArtifactRoiControls item={item} showFiltered={true} showOverlay={false}
      onShowFiltered={vi.fn()} onShowOverlay={vi.fn()} onCaseChange={vi.fn()} /></ChakraProvider>);
    expect(screen.getByText('ROI post-filter: 1 filtered ROI suggestion shown for inspection')).toBeInTheDocument();
    expect(screen.getByText('Review suggestions shown: 2 of 2. Raw model ROIs retained: 2.')).toBeInTheDocument();
    expect(JSON.stringify(item)).toBe(before);
  });

  it('never presents a stale binding as the current saved field', () => {
    const item = fixture(); item.source_sha256 = 'e'.repeat(64);
    render(controls(item));
    expect(screen.getByText('ROI post-filter: Unavailable / all review suggestions retained')).toBeInTheDocument();
    expect(screen.getByText('Review suggestions shown: 2 of 2. Raw model ROIs retained: 2.')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Show saved post-filter field' })).toBeDisabled();
    expect(screen.queryByText(item.artifact_roi_assist!.binding_sha256!)).not.toBeInTheDocument();
  });

  it('reversibly previews cached proposals locally, defaulting to all suggestions', () => {
    const item = fixture(); item.artifact_roi_assist!.status = 'SHADOW_ONLY';
    item.artifact_roi_assist!.suppressed_ids = [];
    item.artifact_roi_assist!.shadow_proposals = [{ detection_id: 'roi-a', reason: 'EMPIRICAL_ARTIFACT_PROPOSAL' }];
    const before = JSON.stringify(item);
    expect(annotationAssistLesions(item)).toHaveLength(2);
    expect(annotationAssistLesions(item, false, false, true).map((row) => row.detection_id)).toEqual(['roi-b']);
    expect(annotationAssistLesions(item, false, false, false)).toHaveLength(2);
    expect(annotationAssistLesions(item, false, true, true)).toHaveLength(2);
    item.source_sha256 = 'e'.repeat(64);
    expect(annotationAssistLesions(item, false, false, true)).toHaveLength(2);
    item.source_sha256 = 'a'.repeat(64);
    expect(JSON.stringify(item)).toBe(before);
  });

  it('never hides a physician-confirmed ROI in the optional preview', () => {
    const item = fixture(); item.artifact_roi_assist!.status = 'SHADOW_ONLY';
    item.artifact_roi_assist!.shadow_proposals = [{ detection_id: 'roi-a', reason: 'EMPIRICAL_ARTIFACT_PROPOSAL' }];
    item.review_evidence = { status: 'REVIEWED', reviewer: null, timestamp: null, summary: {},
      unresolved_count: 0, items: [{ annotation_id: 'roi-a', source: 'AI', label: 'MICROANEURYSM',
        score: .9, status: 'CLINICIAN_CONFIRMED', model_id: 'prism-dr-5fold', model_version: 'fixture',
        reviewer: 'synthetic reviewer', timestamp: null }] } as CaseRecord['review_evidence'];
    expect(annotationAssistLesions(item, false, false, true)).toHaveLength(2);
  });

  it('optional replay toggle and restore do not issue network or clinical actions', async () => {
    const item = fixture(); item.artifact_roi_assist!.status = 'SHADOW_ONLY';
    item.artifact_roi_assist!.shadow_proposals = [{ detection_id: 'roi-a', reason: 'EMPIRICAL_ARTIFACT_PROPOSAL' }];
    const preview = vi.fn(); const fetch = vi.spyOn(globalThis, 'fetch');
    render(<ChakraProvider><ArtifactRoiControls item={item} showFiltered={false} showOverlay={false}
      previewProposals={true} onPreviewProposals={preview} onShowFiltered={vi.fn()}
      onShowOverlay={vi.fn()} onCaseChange={vi.fn()} /></ChakraProvider>);
    const checkbox = screen.getByRole('checkbox', { name: 'Preview hiding proposed artifact ROIs' });
    checkbox.focus(); await userEvent.keyboard(' ');
    await userEvent.click(screen.getByRole('button', { name: 'Restore all filtered ROIs' }));
    expect(preview).toHaveBeenCalledWith(false);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps raw and human state immutable while toggle reversibly shows filtered IDs', () => {
    const item = fixture(); const raw = JSON.stringify(item);
    expect(annotationAssistLesions(item).map((row) => row.detection_id)).toEqual(['roi-b']);
    const all = annotationAssistLesions(item, true);
    expect(all.map((row) => row.detection_id)).toEqual(['roi-a', 'roi-b']);
    expect(all[0].artifactFiltered).toBe(true);
    expect(annotationAssistLesions(item, false, true)).toHaveLength(2);
    expect(JSON.stringify(item)).toBe(raw);
  });

  it('retains all for stale source, unavailable mask and shadow-only proposal', () => {
    const item = fixture();
    item.source_sha256 = 'd'.repeat(64);
    expect(annotationAssistLesions(item)).toHaveLength(2);
    item.source_sha256 = 'a'.repeat(64);
    item.artifact_roi_assist!.status = 'CORE_FAILED_RETAINED_ALL';
    expect(annotationAssistLesions(item)).toHaveLength(2);
    item.artifact_roi_assist!.status = 'SHADOW_ONLY';
    expect(annotationAssistLesions(item)).toHaveLength(2);
  });

  it('adds no control or request when disabled', () => {
    const item = fixture(); item.artifact_roi_assist!.enabled = false;
    const fetch = vi.spyOn(globalThis, 'fetch');
    render(controls(item));
    expect(screen.queryByTestId('artifact-roi-controls')).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('keyboard toggle does not submit a medical or confirmation action', async () => {
    const show = vi.fn(); const fetch = vi.spyOn(globalThis, 'fetch');
    render(controls(fixture(), vi.fn(), show));
    const checkbox = screen.getByRole('checkbox', { name: 'Show filtered artifact ROIs' });
    checkbox.focus(); await userEvent.keyboard(' ');
    expect(show).toHaveBeenCalledWith(true);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('restores all with a binding/revision write, without per-box confirmation', async () => {
    const item = fixture(); const change = vi.fn();
    const saved = { ...item, revision: 2, artifact_roi_assist: { ...item.artifact_roi_assist!, suppressed_ids: [], visible_ids: ['roi-a', 'roi-b'] } };
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(saved), { status: 200 }));
    render(controls(item, change));
    await userEvent.click(screen.getByRole('button', { name: 'Restore all filtered ROIs' }));
    await waitFor(() => expect(change).toHaveBeenCalledWith(saved));
    const [url, request] = fetch.mock.calls[0];
    expect(url).toBe('/v1/cases/A/artifact-roi/restore');
    expect(JSON.parse(request!.body as string)).toEqual({ revision: 1, scope_sha256: 'd'.repeat(64), binding_sha256: 'b'.repeat(64), detection_ids: ['roi-a'] });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('rejects late restore response across case switches', async () => {
    const item = fixture(); const change = vi.fn(); let resolve!: (value: Response) => void;
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise<Response>((done) => { resolve = done; }));
    const mounted = render(controls(item, change));
    await userEvent.click(screen.getByRole('button', { name: 'Restore all filtered ROIs' }));
    mounted.rerender(controls({ ...item, image_id: 'B' }, change));
    await act(async () => {
      resolve(new Response(JSON.stringify({ ...item, revision: 2 }), { status: 200 }));
      await Promise.resolve();
    });
    expect(change).not.toHaveBeenCalled();
  });

  it('shows all after restore failure and never turns it into a negative', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'stale fixture' }), { status: 409 }));
    const show = vi.fn(); const overlay = vi.fn(); const change = vi.fn();
    render(controls(fixture(), change, show, overlay));
    await userEvent.click(screen.getByRole('button', { name: 'Restore all filtered ROIs' }));
    expect(await screen.findByText(/All AI suggestions are shown/)).toBeInTheDocument();
    expect(show).toHaveBeenCalledWith(true); expect(overlay).toHaveBeenCalledWith(false);
    expect(change).not.toHaveBeenCalled();
  });

  it.each(['source', 'scope', 'binding', 'revision'])('ignores late restore after same-image %s changes', async (kind) => {
    const item = fixture(); const change = vi.fn(); let resolve!: (value: Response) => void;
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise<Response>((done) => { resolve = done; }));
    const mounted = render(controls(item, change));
    await userEvent.click(screen.getByRole('button', { name: 'Restore all filtered ROIs' }));
    const next = { ...item, artifact_roi_assist: { ...item.artifact_roi_assist! } };
    if (kind === 'source') next.source_sha256 = 'e'.repeat(64);
    if (kind === 'scope') next.artifact_roi_assist.scope_sha256 = 'e'.repeat(64);
    if (kind === 'binding') next.artifact_roi_assist.binding_sha256 = 'e'.repeat(64);
    if (kind === 'revision') next.revision += 1;
    mounted.rerender(controls(next, change));
    await act(async () => {
      resolve(new Response(JSON.stringify({ ...item, revision: 2 }), { status: 200 }));
      await Promise.resolve();
    });
    expect(change).not.toHaveBeenCalled();
  });
});
