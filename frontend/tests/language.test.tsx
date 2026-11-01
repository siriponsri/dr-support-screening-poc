import { fireEvent, render, screen } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider, LanguageSwitch, useT } from '@/lib/i18n';
import { theme } from '@/theme';
import { WorklistPage } from '@/pages/WorklistPage';
import { DatasetsPage } from '@/pages/DatasetsPage';
import { ReferralsPage } from '@/pages/ReferralsPage';

function Sample() {
  const t = useT();
  return (
    <>
      <h1>Sign in</h1>
      <p>{t('Use the account your administrator gave you.')}</p>
      <p>{t('A sentence nobody translated.')}</p>
    </>
  );
}

const mount = () => render(<ChakraProvider><LanguageProvider><LanguageSwitch /><Sample /></LanguageProvider></ChakraProvider>);

describe('EN/TH switch', () => {
  it('starts in English, switches body text to Thai, keeps headings and untranslated text in English', () => {
    window.localStorage.clear();
    mount();
    expect(screen.getByText('Use the account your administrator gave you.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'TH' }));
    expect(screen.getByText('ใช้บัญชีที่ผู้ดูแลระบบให้ไว้')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByText('A sentence nobody translated.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'TH' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('remembers the choice for this browser', () => {
    window.localStorage.setItem('dr-support-screening.language.v1', 'th');
    mount();
    expect(screen.getByText('ใช้บัญชีที่ผู้ดูแลระบบให้ไว้')).toBeInTheDocument();
    window.localStorage.clear();
  });
});

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

/** Mounts a page with Thai already chosen; unknown routes answer 404. */
function mountPageInThai(node: ReactNode, pathname: string, routes: Record<string, unknown>) {
  window.localStorage.setItem('dr-support-screening.language.v1', 'th');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = new URL(typeof input === 'string' ? input : (input as Request).url, window.location.origin).pathname;
    return path in routes ? json(routes[path]) : json({ detail: 'Not found' }, 404);
  });
  return render(
    <ChakraProvider theme={theme}>
      <MemoryRouter initialEntries={[pathname]}>
        <LanguageProvider>{node}</LanguageProvider>
      </MemoryRouter>
    </ChakraProvider>,
  );
}

describe('Thai body text on pages', () => {
  afterEach(() => { window.localStorage.clear(); });

  it('shows the Worklist empty state and actions in Thai, with the section title in English', async () => {
    mountPageInThai(<WorklistPage />, '/worklist', { '/v1/cases': [], '/v1/models': [] });
    expect(await screen.findByText('ยังไม่มีภาพใน Workspace นี้')).toBeInTheDocument();
    expect(screen.getByText('ใส่ภาพในโฟลเดอร์นำเข้า แล้วกดสแกนโฟลเดอร์')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'สแกนโฟลเดอร์นำเข้า' })).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { name: 'Worklist' }).length).toBeGreaterThan(0);
  });

  it('shows Datasets messages in Thai when the manifest cannot be loaded', async () => {
    mountPageInThai(<DatasetsPage />, '/datasets', {});
    expect(await screen.findByText('โหลด dataset manifest ไม่สำเร็จ ลองรีเฟรชอีกครั้ง')).toBeInTheDocument();
    expect(screen.getByText('เปิด Workspace ก่อน จึงจะ Export dataset manifest ได้')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'รีเฟรช' }).length).toBeGreaterThan(0);
  });

  it('shows the Referrals description and empty state in Thai', async () => {
    mountPageInThai(<ReferralsPage />, '/referrals', { '/v1/referrals': { items: [] } });
    expect(await screen.findByText('ยังไม่มีรายการส่งต่อที่ลงนามแล้ว')).toBeInTheDocument();
    expect(screen.getByText('แสดงเฉพาะรายงานคัดกรองที่ลงนามแล้วและผู้ให้เกรดเลือก Refer ระบบไม่เคยตัดสินการส่งต่อเอง')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { name: 'Referrals' }).length).toBeGreaterThan(0);
  });
});
