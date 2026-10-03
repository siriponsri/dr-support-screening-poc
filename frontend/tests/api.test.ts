import { describe, expect, it, vi } from 'vitest';
import {
  annotationCompletenessApi,
  apiJson,
  normalizeApiDetail,
  type AnnotationCompletenessUpdateRequest,
} from '@/lib/api';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('API error and mutation contracts', () => {
  it('normalizes structured FastAPI validation details', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      detail: [
        { loc: ['body', 'reviewer'], msg: 'Reviewer name required', type: 'value_error' },
        { loc: ['body', 'group'], msg: 'Invalid group', type: 'value_error' },
      ],
    }, 422));

    await expect(apiJson('/v1/cases/CASE-001')).rejects.toThrow('Reviewer name required Invalid group');
    expect(normalizeApiDetail({ message: 'Readable failure' })).toBe('Readable failure');
  });

  it('keeps string conflict details and falls back for non-JSON server errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(jsonResponse({ detail: 'Case changed; reload before reviewing' }, 409));
    await expect(apiJson('/v1/cases/CASE-001')).rejects.toThrow('Case changed; reload before reviewing');

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('upstream failure', { status: 500 }));
    await expect(apiJson('/v1/cases/CASE-001')).rejects.toThrow('Request failed with HTTP 500');
  });

  it('sends annotation completeness mutations as JSON', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}));
    const request: AnnotationCompletenessUpdateRequest = {
      revision: 4,
      reviewer: 'Clinician',
      group: 'CORE',
      state: 'REVIEWED_NONE_FOUND',
      taxonomy_version: 'core-lesions-v1',
    };

    await annotationCompletenessApi.update('CASE-001', request);

    const [, init] = fetchMock.mock.calls[0];
    expect(init).toMatchObject({
      method: 'PUT',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
  });
});
