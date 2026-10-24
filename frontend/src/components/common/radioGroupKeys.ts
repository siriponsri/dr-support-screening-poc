import type { KeyboardEvent } from 'react';

/**
 * Arrow-key handling for button-based radio groups (roving tabindex).
 * Moves selection to the previous/next option and focuses it.
 */
export function handleRadioArrowKeys(
  event: KeyboardEvent<HTMLElement>,
  values: string[],
  current: string,
  select: (value: string) => void,
): void {
  const step = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1
    : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0;
  if (!step) return;
  event.preventDefault();
  const index = values.indexOf(current);
  const next = values[(index < 0 ? (step > 0 ? 0 : values.length - 1) : (index + step + values.length) % values.length)];
  select(next);
  const radios = event.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]');
  radios[values.indexOf(next)]?.focus();
}

/** Only the selected option (or the first, when none is selected) is a tab stop. */
export function radioTabIndex(values: string[], current: string, value: string): number {
  return value === current || (!values.includes(current) && value === values[0]) ? 0 : -1;
}
