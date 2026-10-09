/**
 * `printHtml.ts` — the ONE browser-mode print: render an HTML ticket into a
 * transient container and call `window.print()`.
 *
 * DOM-bound (the byte builders are not). Every ticket (invoice, cierre,
 * entrada, salida, recibo, reimpresion) arrives here as the HTML of
 * `lineasAHtml`, which already declares `@page { size: 80mm auto; margin: 0 }`
 * and a 72 mm printable column; the page rule injected here is the same one, so
 * no browser default margin (2 mm used to be added) narrows the 48 columns.
 */

/** Thermal-paper width 80 mm, free height, NO margin (the ticket column is 72 mm centred). */
export const PAGE_RULE = '@page { size: 80mm auto; margin: 0 }';

/** Marker used to find the injected style node for cleanup. */
const STYLE_ID = 'parkos-escpos-fallback-style';

function injectPageStyle(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STYLE_ID) !== null) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = PAGE_RULE;
  document.head.appendChild(style);
}

const LAYOUT_STYLE_ID = 'parkos-escpos-print-layout';
const PRINT_LAYOUT_RULE =
  '@media print { body > *:not(#parkos-escpos-fallback-container) { display: none !important } #parkos-escpos-fallback-container { position: static !important; left: auto !important } }';

function injectPrintLayout(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(LAYOUT_STYLE_ID) !== null) return;
  const style = document.createElement('style');
  style.id = LAYOUT_STYLE_ID;
  style.textContent = PRINT_LAYOUT_RULE;
  document.head.appendChild(style);
}

function cleanupPageStyle(): void {
  if (typeof document === 'undefined') return;
  for (const id of [STYLE_ID, LAYOUT_STYLE_ID]) {
    const node = document.getElementById(id);
    if (node !== null) node.parentNode?.removeChild(node);
  }
}

/**
 * Render `html` into the transient off-screen container and call
 * `window.print()` once. A second `<style>` (`@media print`) un-hides the
 * container: it lives at `left:-10000px` on screen, which would print a blank
 * page. The container is aria-hidden while present and removed once the print
 * finishes (`afterprint`, with a timeout fallback for engines that never fire it).
 */
const CONTAINER_CLEANUP_TIMEOUT_MS = 30_000;
let cancelPendingCleanup: (() => void) | null = null;

export function printHtml(html: string): void {
  injectPageStyle();
  injectPrintLayout();
  try {
    const containerId = 'parkos-escpos-fallback-container';
    let container = document.getElementById(containerId);
    if (container === null) {
      container = document.createElement('div');
      container.id = containerId;
      // Style it offscreen so it does not flash; the print dialog renders
      // its own copy.
      container.style.position = 'fixed';
      container.style.left = '-10000px';
      container.style.top = '0';
      document.body.appendChild(container);
    }
    container.setAttribute('aria-hidden', 'true');
    container.innerHTML = html;
    // A previous print's pending cleanup must not remove this print's content.
    cancelPendingCleanup?.();
    const target = container;
    const remove = (): void => {
      cancelPendingCleanup?.();
      target.remove();
    };
    const timer = setTimeout(remove, CONTAINER_CLEANUP_TIMEOUT_MS);
    window.addEventListener('afterprint', remove, { once: true });
    cancelPendingCleanup = (): void => {
      clearTimeout(timer);
      window.removeEventListener('afterprint', remove);
      cancelPendingCleanup = null;
    };
    window.print();
  } finally {
    cleanupPageStyle();
  }
}
