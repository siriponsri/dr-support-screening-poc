import '@testing-library/jest-dom/vitest';
import { afterEach, beforeAll, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

beforeAll(() => {
  // jsdom doesn't ship window.matchMedia. Chakra's `useMediaQuery` reads
  // it during passive commit effects, so a missing implementation throws
  // and tears down the tree. Install a permissive stub before any test
  // mounts the shell.
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });

  // Default behaviour: every network call fails. Tests can override via
  // vi.spyOn(globalThis, 'fetch').mockImplementation(...) when they need
  // a successful round-trip.
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline'));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
