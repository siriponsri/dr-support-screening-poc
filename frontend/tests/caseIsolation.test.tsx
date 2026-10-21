import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { describe, it, vi, expect } from 'vitest';
import { ReviewPage } from '@/pages/ReviewPage';
import { ClinicianReviewPage } from '@/pages/ClinicianReviewPage';
import { AnnotationEditorPage } from '@/pages/AnnotationEditorPage';
import { theme } from '@/theme';
import type { CaseRecord } from '@/lib/api';

function fixture(id: string): CaseRecord {
  return { image_id: id, display_name: `Fixture ${id}`, filename: `${id}.png`, source_type: 'SYNTHETIC', source: 'fixture', modality: 'CFP', width: 800, height: 600, image_url: `/${id}.png`, state: 'PENDING', revision: 0, global: null, lesion: null, lesion_review: null, human_annotations: [], clinician_review: null };
}
function Switch() { const go = useNavigate(); const { pathname } = useLocation(); return <button onClick={() => go(pathname.replace(/\/[^/]+$/, '/B'))}>Test switch</button>; }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((r) => { resolve = r; }); return { promise, resolve }; }
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200 });

for (const [route, Page] of [['review', ReviewPage], ['clinician-review', ClinicianReviewPage], ['edit', AnnotationEditorPage]] as const) {
  describe(`${route} case isolation`, () => {
    it('ignores the obsolete initial request after StrictMode effect replay', async () => {
      const obsolete = deferred<Response>();
      let reads = 0;
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
        if (String(input) === '/v1/cases/A') {
          reads += 1;
          return reads === 1 ? obsolete.promise : json({ ...fixture('A'), display_name: 'Fixture latest' });
        }
        return json([]);
      });
      render(<StrictMode><ChakraProvider theme={theme}><MemoryRouter initialEntries={[`/${route}/A`]}><Routes><Route path={`/${route}/:imageId`} element={<Page />} /></Routes></MemoryRouter></ChakraProvider></StrictMode>);
      await screen.findByText(/Fixture latest -/);
      await act(async () => obsolete.resolve(json({ ...fixture('A'), display_name: 'Fixture obsolete' })));
      expect(screen.getByText(/Fixture latest -/)).toBeInTheDocument();
      expect(screen.queryByText(/Fixture obsolete -/)).not.toBeInTheDocument();
    });

    it('removes the previous case while the next image loads and when it fails', async () => {
      const b = deferred<Response>();
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
        if (String(input) === '/v1/cases/A') return json(fixture('A'));
        if (String(input) === '/v1/cases/B') return b.promise;
        return json([]);
      });
      render(<ChakraProvider theme={theme}><MemoryRouter initialEntries={[`/${route}/A`]}><Routes><Route path={`/${route}/:imageId`} element={<><Switch /><Page /></>} /></Routes></MemoryRouter></ChakraProvider>);
      await screen.findByText(/Fixture A -/);
      fireEvent.click(screen.getByText('Test switch'));
      expect(screen.queryByText(/Fixture A -/)).not.toBeInTheDocument();
      await act(async () => b.resolve(new Response(JSON.stringify({ detail: 'Fixture unavailable' }), { status: 404 })));
      expect(await screen.findByText('Fixture unavailable')).toBeInTheDocument();
      expect(screen.queryByLabelText('Final DR grade')).not.toBeInTheDocument();
    });
    it('ignores a late result from the previous image', async () => {
      const a = deferred<Response>();
      vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => String(input) === '/v1/cases/A' ? a.promise : json(String(input) === '/v1/cases/B' ? fixture('B') : []));
      render(<ChakraProvider theme={theme}><MemoryRouter initialEntries={[`/${route}/A`]}><Routes><Route path={`/${route}/:imageId`} element={<><Switch /><Page /></>} /></Routes></MemoryRouter></ChakraProvider>);
      fireEvent.click(screen.getByText('Test switch'));
      await screen.findByText(/Fixture B -/);
      await act(async () => a.resolve(json(fixture('A'))));
      expect(screen.getByText(/Fixture B -/)).toBeInTheDocument();
      expect(screen.queryByText(/Fixture A -/)).not.toBeInTheDocument();
    });
  });
}


describe('Grade mutation lifetime and refresh', () => {
  function gradeCase(id: string) { return fixture(id); }
  it('does not navigate back to an old image when its grade request completes after switching', async () => {
    window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'Fixture reviewer');
    const pending = deferred<Response>();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (String(input) === '/v1/cases/A/review' && init?.method === 'POST') return pending.promise;
      if (String(input) === '/v1/cases/A') return json(gradeCase('A'));
      if (String(input) === '/v1/cases/B') return json(gradeCase('B'));
      return json([]);
    });
    render(<ChakraProvider theme={theme}><MemoryRouter initialEntries={['/clinician-review/A']}><Routes><Route path='/clinician-review/:imageId' element={<><Switch /><ClinicianReviewPage /></>} /><Route path='/edit/:imageId' element={<div>Unexpected old navigation</div>} /></Routes></MemoryRouter></ChakraProvider>);
    await screen.findByLabelText('Final DR grade');
    fireEvent.change(screen.getByLabelText('Final DR grade'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm DR grade' }));
    fireEvent.click(screen.getByText('Test switch'));
    await screen.findByText(/Fixture B -/);
    await act(async () => pending.resolve(json(gradeCase('A'))));
    expect(screen.getByText(/Fixture B -/)).toBeInTheDocument();
    expect(screen.queryByText('Unexpected old navigation')).not.toBeInTheDocument();
  });

  it('warns before refresh with an unsaved grade and remark, and on an in-flight confirmation', async () => {
    window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'Fixture reviewer');
    const pending = deferred<Response>();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => init?.method === 'POST' ? pending.promise : json(String(input) === '/v1/cases/A' ? gradeCase('A') : []));
    render(<ChakraProvider theme={theme}><MemoryRouter initialEntries={['/clinician-review/A']}><Routes><Route path='/clinician-review/:imageId' element={<ClinicianReviewPage />} /></Routes></MemoryRouter></ChakraProvider>);
    await screen.findByLabelText('Final DR grade');
    const clean = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(clean); expect(clean.defaultPrevented).toBe(false);
    fireEvent.change(screen.getByLabelText('Final DR grade'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Remark (optional)'), { target: { value: 'Synthetic draft' } });
    const dirty = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(dirty); expect(dirty.defaultPrevented).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm DR grade' }));
    const saving = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(saving); expect(saving.defaultPrevented).toBe(true);
  });

  it('sends only one grade mutation when clicks arrive in one event batch', async () => {
    window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'Fixture reviewer');
    const pending = deferred<Response>(); let writes = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (init?.method === 'POST') { writes += 1; return pending.promise; }
      return json(String(input) === '/v1/cases/A' ? gradeCase('A') : []);
    });
    render(<ChakraProvider theme={theme}><MemoryRouter initialEntries={['/clinician-review/A']}><Routes><Route path='/clinician-review/:imageId' element={<ClinicianReviewPage />} /></Routes></MemoryRouter></ChakraProvider>);
    await screen.findByLabelText('Final DR grade');
    fireEvent.change(screen.getByLabelText('Final DR grade'), { target: { value: '2' } });
    const button = screen.getByRole('button', { name: 'Confirm DR grade' });
    act(() => { fireEvent.click(button); fireEvent.click(button); });
    await waitFor(() => expect(writes).toBe(1));
  });
});


it('serializes ROI confirmation, locks editing while pending, and retires follow-up derivation on switching', async () => {
  window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'Synthetic reviewer');
  const pending = deferred<Response>();
  const proposal = { detection_id: 'ai-fixture', source_label: 'HE', canonical_label: 'HEMORRHAGE', rectangle: [10, 20, 40, 60] as [number, number, number, number], score: 0.9, state: 'AI_SUGGESTION' };
  const a: CaseRecord = { ...fixture('A'), grade_status: 'CONFIRMED', clinician_review: { final_grade: 2, reviewer: 'Synthetic reviewer', timestamp: '2026-10-21T00:00:00Z', revision: 1, review_action: 'CORRECT_GRADE', remark: '' }, lesion: { model_id: 'prism-dr-5fold', model_version: 'fixture', modality: 'CFP', state: 'AI_SUGGESTION', width: 800, height: 600, lesions: [proposal], warnings: [] }, lesion_review: { raw_count: 1, suggestion_count: 1, filtered_count: 0, lesions: [proposal], policy: { thresholds: {}, max_per_class: 25, max_total: 80 } } };
  let decisions = 0; let derivations = 0;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith('/lesion-review')) { decisions += 1; return pending.promise; }
    if (path.endsWith('/annotations/from-ai')) { derivations += 1; return json(a); }
    if (path === '/v1/cases/A') return json(a);
    return json(path === '/v1/cases/B' ? fixture('B') : []);
  });
  render(<ChakraProvider theme={theme}><MemoryRouter initialEntries={['/edit/A']}><Routes><Route path='/edit/:imageId' element={<><Switch /><AnnotationEditorPage /></>} /></Routes></MemoryRouter></ChakraProvider>);
  const stage = await screen.findByLabelText('Retinal image viewer stage');
  fireEvent.click(stage.querySelector('[data-ai-detection-id="ai-fixture"] rect')!);
  const confirm = await screen.findByRole('button', { name: 'Confirm', exact: true });
  act(() => { fireEvent.click(confirm); fireEvent.click(confirm); });
  await waitFor(() => expect(decisions).toBe(1));
  expect(screen.getByRole('button', { name: 'Box', exact: true })).toBeDisabled();
  fireEvent.click(screen.getByText('Test switch'));
  await screen.findByText(/Fixture B -/);
  await act(async () => pending.resolve(json({ ...a, revision: 2 })));
  expect(derivations).toBe(0);
  expect(screen.getByText(/Fixture B -/)).toBeInTheDocument();
});
