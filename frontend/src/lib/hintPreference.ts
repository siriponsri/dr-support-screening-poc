const HINTS_KEY = 'dr-support-screening.next-action-hints.v1';
const GUIDE_FIRST_FLOW_KEY = 'dr-support-screening.guide-first-flow.v1';
const GUIDE_OFFER_PENDING_KEY = 'dr-support-screening.guide-offer-pending.v1';

export function getGuideModeEnabled(): boolean {
  try {
    return window.localStorage.getItem(HINTS_KEY) !== 'disabled';
  } catch {
    return true;
  }
}

export function setGuideModeEnabled(enabled: boolean): void {
  try {
    if (enabled) window.localStorage.removeItem(HINTS_KEY);
    else window.localStorage.setItem(HINTS_KEY, 'disabled');
  } catch {
    // Restricted browser storage must not block review.
  }
}

export function markGuideFirstFlowCompleted(): void {
  try {
    if (window.localStorage.getItem(GUIDE_FIRST_FLOW_KEY) === 'complete') return;
    window.localStorage.setItem(GUIDE_FIRST_FLOW_KEY, 'complete');
    if (window.localStorage.getItem(HINTS_KEY) !== 'disabled') {
      window.localStorage.setItem(GUIDE_OFFER_PENDING_KEY, 'true');
    }
  } catch {
    // Guidance preferences must never block clinical completion.
  }
}

export function getGuideOfferPending(): boolean {
  try {
    return window.localStorage.getItem(GUIDE_OFFER_PENDING_KEY) === 'true';
  } catch {
    return false;
  }
}

export function clearGuideOfferPending(): void {
  try {
    window.localStorage.removeItem(GUIDE_OFFER_PENDING_KEY);
  } catch {
    // Restricted browser storage must not block review.
  }
}
