import { fireEvent, render, screen } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { describe, expect, it } from 'vitest';
import { LanguageProvider, LanguageSwitch, useT } from '@/lib/i18n';

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
