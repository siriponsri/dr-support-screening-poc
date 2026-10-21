import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { NavigationGuardProvider } from '@/components/shell/NavigationGuard';
import { WorkspaceProvider, useWorkspace } from '@/components/shell/workspace';
import { AnnotationEditorPage } from '@/pages/AnnotationEditorPage';
import { ChakraProvider } from '@chakra-ui/react';
import { HashRouter } from 'react-router-dom';
import { render, act } from '@testing-library/react';
import { AppCore } from '@/App';
import { theme } from '@/theme';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, vi, expect } from 'vitest';
import { renderAppAt } from './testUtils';
import type { CaseRecord } from '@/lib/api';

function fixture(): CaseRecord {
  return { image_id: 'draft-fixture', filename: 'synthetic.png', display_name: 'Synthetic draft fixture', source_type: 'SYNTHETIC', source_origin: 'SYNTHETIC', source: 'fixture', modality: 'CFP', width: 800, height: 600, image_url: '/synthetic.png', state: 'REVIEWED', revision: 1, global: null, lesion: null, lesion_review: null, human_annotations: [{ shape_id: 'human-fixture', type: 'rectangle', label: 'HEMORRHAGE', geometry: { x: 10, y: 20, width: 30, height: 40 }, locked: false, source: 'HUMAN', reviewer: 'Synthetic reviewer', created_at: '' }], clinician_review: { final_grade: 2, reviewer: 'Synthetic reviewer', timestamp: '2026-10-21T00:00:00Z', revision: 1, review_action: 'CORRECT_GRADE', remark: '' }, grade_status: 'CONFIRMED', queue_state: 'INCLUDED' };
}
function fake(failSave = false) {
  let item = fixture(); const writes: Array<{ path: string; body: unknown }> = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://fixture.invalid').pathname;
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
    if (init?.method === 'PUT') {
      const body = JSON.parse(String(init.body)); writes.push({ path, body });
      if (failSave) return json({ detail: 'Synthetic save failed' }, 503);
      item = { ...item, revision: item.revision + 1, human_annotations: body.annotations }; return json(item);
    }
    if (path === '/v1/cases/draft-fixture') return json(item);
    if (path === '/v1/cases') return json([item]);
    if (path === '/v1/workspaces') return json({ workspaces: [], active_workspace: null, warnings: [] });
    if (path === '/v1/workspaces/active') return json({ workspace: null, database: { status: 'postgres' }, warnings: [] });
    if (path === '/health') return json({ status: 'PASS' });
    return json([]);
  });
  window.localStorage.setItem('dr-support-screening.default-reviewer.v1', 'Synthetic reviewer');
  return { writes, item: () => item };
}
async function editAnnotation() {
  const stage = await screen.findByLabelText('Retinal image viewer stage');
  fireEvent.click(stage.querySelector('[data-human-shape-id="human-fixture"] rect')!);
  fireEvent.change(screen.getByLabelText('Selected annotation class'), { target: { value: 'SOFT_EXUDATE' } });
}

describe('Clinical drafts and shell navigation', () => {
  it('keeps an unsaved grade and remark when shell navigation is cancelled', async () => {
    fake(); renderAppAt('/clinician-review/draft-fixture');
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Edit confirmed grade' }));
    await userEvent.setup().click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Continue editing' }));
    fireEvent.change(screen.getByLabelText('Final DR grade'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Remark (optional)'), { target: { value: 'Synthetic local draft' } });
    fireEvent.click(screen.getByRole('link', { name: 'Worklist', exact: true }));
    const dialog = await screen.findByRole('alertdialog');
    await userEvent.setup().click(within(dialog).getByRole('button', { name: 'Stay on this image' }));
    expect(screen.getByLabelText('Final DR grade')).toHaveValue('3');
    expect(screen.getByLabelText('Remark (optional)')).toHaveValue('Synthetic local draft');
  });

  for (const failure of [false, true]) {
    it(`flushes a rapid annotation edit before leaving; save failure=${failure}`, async () => {
      const backend = fake(failure); renderAppAt('/edit/draft-fixture'); await editAnnotation();
      fireEvent.click(screen.getByRole('link', { name: 'Worklist', exact: true }));
      const dialog = await screen.findByRole('alertdialog');
      await userEvent.setup().click(within(dialog).getByRole('button', { name: 'Save draft and leave' }));
      await waitFor(() => expect(backend.writes).toHaveLength(1));
      if (failure) {
        expect(await screen.findByText('Synthetic save failed')).toBeInTheDocument();
        expect(screen.getByLabelText('Selected annotation class')).toHaveValue('SOFT_EXUDATE');
      } else {
        expect((await screen.findAllByRole('heading', { name: 'Worklist', exact: true })).length).toBeGreaterThan(0);
        expect(backend.item().human_annotations[0].label).toBe('SOFT_EXUDATE');
      }
      expect(backend.writes.every((write) => write.path.endsWith('/annotations'))).toBe(true);
    });
  }
});


it('keeps the annotation draft when native browser Back is cancelled', async () => {
  fake();
  window.history.replaceState({ idx: 0, key: 'back-worklist' }, '', '/#/worklist');
  window.history.pushState({ idx: 1, key: 'back-editor' }, '', '/#/edit/draft-fixture');
  const view = render(<ChakraProvider theme={theme}><HashRouter><AppCore forceTier='desktop' /></HashRouter></ChakraProvider>);
  await editAnnotation();
  act(() => window.history.back());
  const dialog = await screen.findByRole('alertdialog');
  await userEvent.setup().click(within(dialog).getByRole('button', { name: 'Stay on this image' }));
  await waitFor(() => expect(window.location.hash).toBe('#/edit/draft-fixture'));
  expect(screen.getByLabelText('Selected annotation class')).toHaveValue('SOFT_EXUDATE');
  view.unmount();
  window.history.replaceState(null, '', '/');
});


function WorkspaceSwitch() {
  const workspace = useWorkspace();
  return <button onClick={() => void workspace.openWorkspace('synthetic-other').catch(() => {})}>Test workspace switch</button>;
}

it('guards workspace transitions before sending any workspace mutation', async () => {
  fake();
  const view = render(<ChakraProvider theme={theme}><MemoryRouter initialEntries={['/edit/draft-fixture']}><NavigationGuardProvider><WorkspaceProvider><WorkspaceSwitch /><Routes><Route path='/edit/:imageId' element={<AnnotationEditorPage />} /></Routes></WorkspaceProvider></NavigationGuardProvider></MemoryRouter></ChakraProvider>);
  await editAnnotation();
  fireEvent.click(screen.getByText('Test workspace switch'));
  const dialog = await screen.findByRole('alertdialog');
  await userEvent.setup().click(within(dialog).getByRole('button', { name: 'Stay on this image' }));
  expect(screen.getByLabelText('Selected annotation class')).toHaveValue('SOFT_EXUDATE');
  expect(vi.mocked(globalThis.fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  view.unmount();
});

for (const failure of [false, true]) {
  it(`flushes before accepting native Back and restores the route on failure=${failure}`, async () => {
    const backend = fake(failure);
    window.history.replaceState({ idx: 0, key: 'native-worklist' }, '', '/#/worklist');
    window.history.pushState({ idx: 1, key: 'native-editor' }, '', '/#/edit/draft-fixture');
    const view = render(<ChakraProvider theme={theme}><HashRouter><AppCore forceTier='desktop' /></HashRouter></ChakraProvider>);
    await editAnnotation();
    act(() => window.history.back());
    const dialog = await screen.findByRole('alertdialog');
    await userEvent.setup().click(within(dialog).getByRole('button', { name: 'Save draft and leave' }));
    if (failure) {
      await waitFor(() => expect(window.location.hash).toBe('#/edit/draft-fixture'));
      expect(screen.getByLabelText('Selected annotation class')).toHaveValue('SOFT_EXUDATE');
      expect(await screen.findByText('Synthetic save failed')).toBeInTheDocument();
    } else {
      expect((await screen.findAllByRole('heading', { name: 'Worklist', exact: true })).length).toBeGreaterThan(0);
      expect(backend.item().human_annotations[0].label).toBe('SOFT_EXUDATE');
    }
    expect(backend.writes.every((write) => write.path.endsWith('/annotations'))).toBe(true);
    view.unmount(); window.history.replaceState(null, '', '/');
  });
}
