import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { CaseRecord } from '@/lib/api';
import { renderAppAt } from './testUtils';

const baseCase: CaseRecord = {
  image_id: 'unknown',
  display_name: 'unknown_001',
  filename: 'unknown_001.jpg',
  source_type: 'PUBLIC',
  source: 'WORKSPACE_INPUT',
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
  patient_key: null,
  patient_resolution_state: 'NEEDS_CONFIRMATION',
  patient_resolution_method: 'OCR',
  patient_reason_code: 'OCR_CANDIDATE',
  patient_candidate: 'PAT0001',
  laterality: 'UNKNOWN',
  laterality_resolution_state: 'NEEDS_CONFIRMATION',
  laterality_resolution_method: 'OCR',
  laterality_reason_code: 'OCR_LATERALITY_CANDIDATE',
  laterality_candidate: 'LEFT',
  resolver_state: 'NEEDS_CONFIRMATION',
  resolver_ui: {
    label: 'Please confirm patient',
    note: 'Patient information was found but needs confirmation.',
    tone: 'warning',
    action_required: true,
    patient: {
      label: 'Please confirm patient',
      note: 'Patient information was found but needs confirmation.',
      tone: 'warning',
      action_required: true,
      candidate: 'PAT0001',
    },
    laterality: {
      label: 'Eye side needs confirmation',
      note: 'Choose Left or Right, or leave it as Unknown.',
      tone: 'warning',
      action_required: true,
      value: 'UNKNOWN',
      candidate: 'LEFT',
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

describe('patient and eye resolver UI', () => {
  it('confirms a proposed pseudonymous patient and saves eye side independently', async () => {
    const user = userEvent.setup();
    const saved: CaseRecord = {
      ...baseCase,
      revision: 1,
      patient_key: 'PAT0001',
      patient_resolution_state: 'RESOLVED',
      laterality: 'UNKNOWN',
      laterality_resolution_state: 'NEEDS_CONFIRMATION',
      resolver_state: 'NEEDS_CONFIRMATION',
      resolver_ui: {
        ...baseCase.resolver_ui!,
        label: 'Eye side needs confirmation',
        note: 'Choose Left or Right, or leave it as Unknown.',
        patient: {
          ...baseCase.resolver_ui!.patient,
          label: 'Patient matched',
          note: 'Patient information was matched for this image.',
          tone: 'success',
          action_required: false,
          patient_key: 'PAT0001',
        },
      },
    };
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = requestPath(input);
      if (path === '/v1/cases') return jsonResponse([baseCase]);
      if (path.endsWith('/resolver')) {
        const payload = JSON.parse(String(init?.body));
        expect(payload.patient_action).toBe('CONFIRM');
        expect(payload.patient_key).toBe('PAT0001');
        return jsonResponse(saved);
      }
      return jsonResponse({ detail: `Unexpected test request: ${path}` }, 404);
    });

    renderAppAt('/worklist');
    await user.click(await screen.findByRole('button', { name: 'Link patient and confirm eye' }));
    expect(screen.getByRole('dialog', { name: 'Resolve patient and eye' })).toBeInTheDocument();
    expect(screen.getByLabelText('Pseudonymous patient key')).toHaveValue('PAT0001');
    await user.type(screen.getByPlaceholderText('Reviewer name'), 'Demo clinician');
    await user.click(screen.getByRole('button', { name: 'Save patient / eye' }));
    expect(await screen.findByText('PAT0001')).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalled();
  });
});
