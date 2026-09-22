const HINTS_KEY = 'dr-support-screening.next-action-hints.v1';

export function getHintsEnabled(): boolean {
  try {
    return window.localStorage.getItem(HINTS_KEY) !== 'disabled';
  } catch {
    return true;
  }
}

export function setHintsEnabled(enabled: boolean): void {
  try {
    if (enabled) window.localStorage.removeItem(HINTS_KEY);
    else window.localStorage.setItem(HINTS_KEY, 'disabled');
  } catch {
    // Restricted browser storage must not block review.
  }
}
