const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Cycle Tab/Shift+Tab focus within a modal container. Attach from the dialog's
 * onKeyDown so keyboard focus cannot escape the dialog while it is open.
 * (Escape handling stays with each dialog; only Tab is managed here.)
 */
export function trapModalFocus(
  container: HTMLElement | null,
  event: { key: string; shiftKey: boolean; preventDefault: () => void },
): void {
  if (event.key !== "Tab") {
    return;
  }
  const focusable = container?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
  if (!focusable || focusable.length === 0) {
    event.preventDefault();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
