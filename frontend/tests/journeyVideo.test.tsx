import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { AuthGate } from '@/components/shell/AuthGate';
import { LanguageProvider } from '@/lib/i18n';

function signedOut() {
  vi.stubGlobal('fetch', vi.fn(async (input: string) => (input === '/v1/auth/me'
    ? { ok: false, status: 401, json: async () => ({ detail: 'Please sign in.' }) }
    : { ok: false, status: 404, json: async () => ({ detail: 'Not Found' }) })));
}

function mount() {
  return render(<ChakraProvider><LanguageProvider><AuthGate><p>App</p></AuthGate></LanguageProvider></ChakraProvider>);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('sign-in page walkthrough video', () => {
  it('opens a dialog with the narrated video and Thai captions, then closes and pauses it', async () => {
    signedOut();
    const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Watch how it works' }));

    const dialog = await screen.findByRole('dialog', { name: 'How the Workbench works' });
    const video = dialog.querySelector('video');
    expect(video).not.toBeNull();
    expect(video?.getAttribute('src')).toBe('/app/media/journey-th.mp4');
    expect(video?.hasAttribute('controls')).toBe(true);
    expect(video?.hasAttribute('autoplay')).toBe(false);
    expect(video?.getAttribute('preload')).toBe('metadata');
    const track = video?.querySelector('track');
    expect(track?.getAttribute('src')).toBe('/app/media/journey-th.vtt');
    expect(track?.getAttribute('kind')).toBe('captions');
    expect(track?.getAttribute('srclang')).toBe('th');
    // Captions are drawn in the picture, so the track would show every line twice if it were on by default.
    expect(track?.hasAttribute('default')).toBe(false);

    fireEvent.click(screen.getAllByRole('button', { name: 'Close' })[0]);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(pause).toHaveBeenCalled();
  });

  it('closes with Escape and shows the Thai label when Thai is chosen', async () => {
    window.localStorage.setItem('dr-support-screening.language.v1', 'th');
    signedOut();
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'ดูวิธีใช้งาน' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});
