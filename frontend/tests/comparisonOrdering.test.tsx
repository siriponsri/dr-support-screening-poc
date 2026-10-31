import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, it, vi, expect } from 'vitest';
import { ReviewPage } from '@/pages/ReviewPage';
import { theme } from '@/theme';
import type { CaseRecord } from '@/lib/api';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
function deferred() { let resolve!: (value: Response) => void; const promise = new Promise<Response>((r) => { resolve = r; }); return { promise, resolve }; }
function fixture(id: string): CaseRecord {
  return { image_id: id, display_name: `Fixture ${id}`, filename: `${id}.png`, source_type: 'SYNTHETIC', source: 'fixture', modality: 'CFP', width: 800, height: 600, image_url: null, state: 'PENDING', revision: 0, global: null, lesion: null, lesion_review: null, human_annotations: [], clinician_review: null, patient_key: 'SYNTHETIC', patient_resolution_state: 'RESOLVED', laterality: 'LEFT', laterality_resolution_state: 'RESOLVED', visit_context: { visit_key: null, captured_at: null, device: null, capture_sequence: id === 'A' ? 3 : 1, evidence_state: 'CONFIRMED' } };
}
function pair(other: string) { return { eligible: true, visits: [{ image_id: other, label: 'PREVIOUS EXAM', display_name: `Displayed ${other}`, laterality: 'LEFT', modality: 'CFP' }, { image_id: 'A', label: 'CURRENT EXAM', display_name: 'Displayed current', laterality: 'LEFT', modality: 'CFP' }] }; }
async function setup() {
  const automatic = deferred(); const explicit = deferred(); const latest = deferred();
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url === '/v1/cases/A') return json(fixture('A'));
    if (url === '/v1/cases') return json(['A','B','C'].map(fixture));
    if (url === '/v1/cases/A/comparison') return automatic.promise;
    if (url.endsWith('other_image_id=B')) return explicit.promise;
    if (url.endsWith('other_image_id=C')) return latest.promise;
    return json([]);
  });
  render(<ChakraProvider theme={theme}><MemoryRouter initialEntries={['/review/A']}><Routes><Route path='/review/:imageId' element={<ReviewPage />} /></Routes></MemoryRouter></ChakraProvider>);
  await screen.findByText('Fixture A, image under review');
  fireEvent.click(screen.getByRole('button', { name: 'Show comparison' }));
  await screen.findByRole('option', { name: 'Fixture B' });
  return { automatic, explicit, latest };
}
async function compare(id: string) {
  fireEvent.change(screen.getByLabelText('Comparison visit'), { target: { value: id } });
  const button = screen.getByRole('button', { name: 'Compare', exact: true });
  await waitFor(() => expect(button).not.toBeDisabled());
  fireEvent.click(button);
}

describe('Same-case comparison request ordering', () => {
  it.each([false, true])('keeps an explicit pair after obsolete automatic success/failure=%s', async (failure) => {
    const { automatic, explicit } = await setup();
    await compare('B');
    await act(async () => explicit.resolve(json(pair('B'))));
    expect(await screen.findByText('Displayed B')).toBeInTheDocument();
    await act(async () => automatic.resolve(failure ? json({ detail: 'Obsolete failure' }, 409) : json(pair('C'))));
    expect(screen.getByText('Displayed B')).toBeInTheDocument();
    expect(screen.queryByText('Displayed C')).not.toBeInTheDocument();
    expect(screen.queryByText('Obsolete failure')).not.toBeInTheDocument();
  });
  it('only lets the latest selected pair settle loading and results', async () => {
    const { automatic, explicit, latest } = await setup();
    await compare('B');
    await compare('C');
    await act(async () => { automatic.resolve(json(pair('B'))); explicit.resolve(json({ detail: 'Old B failure' }, 409)); });
    expect(screen.queryByText('Displayed B')).not.toBeInTheDocument();
    expect(screen.queryByText('Old B failure')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare', exact: true })).toBeDisabled();
    await act(async () => latest.resolve(json(pair('C'))));
    expect(await screen.findByText('Displayed C')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare', exact: true })).not.toBeDisabled();
  });
  it('rejects an eligible response containing a different explicit pair', async () => {
    const { explicit } = await setup();
    await compare('B');
    await act(async () => explicit.resolve(json(pair('C'))));
    expect(screen.queryByText('Displayed C')).not.toBeInTheDocument();
    expect(await screen.findByText(/Comparison response does not match/)).toBeInTheDocument();
  });
  it('does not let candidate-list completion clear an active comparison loading state', async () => {
    const { automatic } = await setup();
    expect(screen.getByRole('button', { name: 'Find previous exam' })).toBeDisabled();
    await act(async () => automatic.resolve(json(pair('B'))));
    expect(await screen.findByText('Displayed B')).toBeInTheDocument();
  });
});
