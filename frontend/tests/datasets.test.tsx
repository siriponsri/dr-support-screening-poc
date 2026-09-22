import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DatasetsPage } from '@/pages/DatasetsPage';
import type { DatasetManifestResponse } from '@/lib/api';
import { withProviders } from './testUtils';

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const manifest: DatasetManifestResponse = {
  schema_version: 's4.dataset-manifest.v1',
  export_id: null,
  created_at: '2026-09-21T00:00:00+00:00',
  workspace_id: 'ws_demo',
  workspace_name: 'April DR Screening',
  image_count: 2,
  annotation_count: 2,
  training_ready_count: 1,
  needs_review_count: 1,
  excluded_count: 0,
  can_export: true,
  images: [
    {
      image_id: 'sha-ready', filename: 'ready.png', image_sha256: 'a'.repeat(64), width: 640, height: 480,
      modality: 'CFP', source_type: 'PUBLIC', patient_key: 'PAT0001', laterality: 'LEFT',
      patient_resolution_method: 'MANUAL', laterality_resolution_method: 'MANUAL',
      modality_admission: 'FUNDUS_ACCEPTED', quality_state: 'NOT_EVALUATED', queue_state: 'INCLUDED',
      ai_grade: 2, ai_model_id: 'retfound-aptos5', ai_model_version: 'v1', ai_confidence: 0.7,
      clinician_grade: 2, grade_review_source: 'AI_ACCEPTED', review_status: 'CLINICIAN_REVIEWED',
      reviewer: 'Clinician', reviewed_at: '2026-09-21T00:00:00+00:00', human_annotation_count: 1,
      ai_lesion_count: 1, cvat_annotation_count: 0, verification_status: 'CLINICIAN_REVIEWED',
      include_in_training: true, eligibility_reason: 'ELIGIBLE', dataset_status: 'Ready for dataset',
    },
    {
      image_id: 'sha-review', filename: 'review.png', image_sha256: 'b'.repeat(64), width: 400, height: 300,
      modality: 'CFP', source_type: 'PUBLIC', patient_key: null, laterality: 'UNKNOWN',
      patient_resolution_method: 'NONE', laterality_resolution_method: 'NONE',
      modality_admission: 'FUNDUS_ACCEPTED', quality_state: 'NOT_EVALUATED', queue_state: 'INCLUDED',
      ai_grade: 3, ai_model_id: 'retfound-aptos5', ai_model_version: 'v1', ai_confidence: 0.8,
      clinician_grade: null, grade_review_source: null, review_status: 'AI_ONLY', reviewer: null, reviewed_at: null,
      human_annotation_count: 0, ai_lesion_count: 1, cvat_annotation_count: 0, verification_status: 'AI_ONLY',
      include_in_training: false, eligibility_reason: 'NO_FINAL_CLINICIAN_GRADE', dataset_status: 'AI only',
    },
  ],
  annotations: [],
};

describe('Datasets page', () => {
  it('shows active workspace scope, status views, and export action', async () => {
    const user = userEvent.setup();
    let exportMethod = '';
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname;
      if (path === '/v1/dataset/manifest') return response(manifest);
      if (path === '/v1/dataset/export') {
        exportMethod = init?.method ?? '';
        return response({ ...manifest, export_id: 'export-1', directory_name: 'dataset-export-export-1', files: ['manifest.json', 'images.csv', 'annotations.csv'] });
      }
      return response({ detail: `Unexpected request ${path}` }, 404);
    });

    withProviders(<DatasetsPage />, '/datasets');
    expect(await screen.findByText('April DR Screening')).toBeInTheDocument();
    expect(screen.getByText('ready.png')).toBeInTheDocument();
    expect(screen.getByText('review.png')).toBeInTheDocument();
    expect(screen.queryByText('Datasets (reserved)')).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /DR-ready/ }));
    expect(screen.getByText('ready.png')).toBeInTheDocument();
    expect(screen.queryByText('review.png')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Export manifest' }));
    expect(exportMethod).toBe('POST');
    expect(await screen.findByText('Export created: 2 images and 2 annotations.')).toBeInTheDocument();
  });

  it('shows the no-workspace recovery state and keeps export disabled', async () => {
    const noWorkspace = { ...manifest, workspace_id: null, workspace_name: null, can_export: false };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(noWorkspace));
    withProviders(<DatasetsPage />, '/datasets');

    expect(await screen.findByText('Open an active Workspace to export a dataset manifest.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export manifest' })).toBeDisabled();
  });

  it('keeps backend exception details out of the clinician surface', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      response({ detail: 'MISSING_PROVENANCE: C:\\private\\patient-records' }, 409),
    );
    withProviders(<DatasetsPage />, '/datasets');

    expect(await screen.findByText('The dataset manifest could not be loaded. Try refreshing.')).toBeInTheDocument();
    expect(screen.queryByText(/MISSING_PROVENANCE/)).not.toBeInTheDocument();
  });
});
