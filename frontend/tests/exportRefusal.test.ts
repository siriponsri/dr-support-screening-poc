import { describe, expect, it } from 'vitest';
import { plainExportRefusal } from '@/lib/api';

describe('plainExportRefusal', () => {
  it('shows only the clinician-written local-folder refusal', () => {
    const refusal = 'Hospital records can be exported only to a local folder on this computer. In Settings, choose a Workspace output folder that is not on a network share or synced to a cloud service.';
    expect(plainExportRefusal(new Error(refusal))).toBe(refusal);
    expect(plainExportRefusal(new Error('psycopg.OperationalError: connection refused'))).toBeNull();
    expect(plainExportRefusal('not an error')).toBeNull();
  });
});
