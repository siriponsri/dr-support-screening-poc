import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GoldPage } from '@/pages/GoldPage';

const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });

afterEach(() => vi.restoreAllMocks());

describe('Gold-100 labelling', () => {
  it('keeps the AI suggestion hidden until the expert saves a grade, and sends no AI value with it', async () => {
    const calls: { url: string; method: string; body?: Record<string, unknown> }[] = [];
    let saved = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? 'GET';
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : undefined });
      if (url === '/v1/cases/IMG1') return json({ image_id: 'IMG1', image_url: '/img.png', modality: 'UWF' });
      if (url.endsWith('/gold-label/blind')) { saved = true; return json({ revision: 2, gold_label: { blind: { grade: 2, gradable: true } } }); }
      return json({ revision: saved ? 2 : 1, gold_label: saved ? { blind: { grade: 2, gradable: true } } : null });
    });
    render(<ChakraProvider><MemoryRouter initialEntries={['/gold/IMG1']}>
      <Routes><Route path="/gold/:imageId" element={<GoldPage />} /></Routes></MemoryRouter></ChakraProvider>);
    const show = await screen.findByRole('button', { name: 'Show AI suggestion' });
    expect(show).toBeDisabled();
    expect(screen.getByText('Your grade is the reference. Only the grade and gradability are needed.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Gradable' }));
    fireEvent.click(screen.getByRole('radio', { name: '2 Moderate NPDR' }));
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Synthetic expert' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save my grade' }));
    expect(await screen.findByText('Your grade is saved.')).toBeInTheDocument();
    const blind = calls.find((call) => call.url.endsWith('/gold-label/blind'));
    expect((blind?.body?.label as Record<string, unknown>).grade).toBe(2);
    expect(JSON.stringify(blind?.body)).not.toMatch(/ai_/);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Show AI suggestion' })).toBeEnabled());
  });
});
