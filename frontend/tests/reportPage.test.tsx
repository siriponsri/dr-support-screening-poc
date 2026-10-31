import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReportPage } from '@/pages/ReportPage';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

function mount() {
  return render(<ChakraProvider><MemoryRouter initialEntries={['/report/IMG1']}>
    <Routes><Route path="/report/:imageId" element={<ReportPage />} /></Routes></MemoryRouter></ChakraProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe('screening report page', () => {
  it('lets the grader choose Refer with destination and urgency, and saves exactly that choice', async () => {
    const sent: Record<string, unknown>[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (init?.method === 'PUT') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        sent.push(body);
        return json({ revision: 2, screening_report: { form: body.report, status: 'DRAFT' } });
      }
      return json({ revision: 1, screening_report: null });
    });
    mount();
    await screen.findByText('Report status: Not started');
    expect(screen.queryByText('Urgency')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Refer' }));
    fireEvent.click(await screen.findByRole('radio', { name: 'Within 3 months' }));
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Synthetic reviewer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(sent).toHaveLength(1));
    const report = sent[0].report as Record<string, unknown>;
    expect(report.decision).toBe('REFER');
    expect(report.urgency).toBe('WITHIN_3_MONTHS');
    expect(sent[0].sign).toBe(false);
    expect(await screen.findByText('Report saved.')).toBeInTheDocument();
  });

  it('keeps Sign disabled until a result is chosen and links to the printable page', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({ revision: 1, screening_report: null }));
    mount();
    await screen.findByText('Report status: Not started');
    expect(screen.getByRole('button', { name: 'Sign report' })).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Print / Save as PDF' })).toHaveAttribute('href', '/v1/cases/IMG1/screening-report/print');
  });
});
