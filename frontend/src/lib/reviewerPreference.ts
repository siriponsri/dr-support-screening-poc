const DEFAULT_REVIEWER_KEY = 'dr-support-screening.default-reviewer.v1';

export function getDefaultReviewer(): string {
  try {
    return window.localStorage.getItem(DEFAULT_REVIEWER_KEY) ?? '';
  } catch {
    return '';
  }
}
export function setDefaultReviewer(value: string): void {
  try {
    const reviewer = value.trim();
    if (reviewer) {
      window.localStorage.setItem(DEFAULT_REVIEWER_KEY, reviewer);
    } else {
      window.localStorage.removeItem(DEFAULT_REVIEWER_KEY);
    }
  } catch {
    // A restricted browser storage policy should not block clinical review.
  }
}
