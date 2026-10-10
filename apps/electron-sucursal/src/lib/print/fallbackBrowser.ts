/**
 * `fallbackBrowser.ts` — browser-mode (`window.print`) rendering of the
 * operation tickets.
 *
 * HU-F5.2 (Fase 5 — base de impresión) / DEC-SUC-08.
 *
 * The HTML of every ticket (entrada, salida, salida-mensualidad, reimpresion,
 * recibo_pago, arqueo) is rendered from the SAME channel-neutral lines as its
 * ESC/POS bytes (`escposBuilder.lineasDeTiquete`) by the SAME renderer as the
 * invoice and the cierre de turno (`facturaPrint.lineasAHtml`): a fixed 72 mm
 * column on an 80 mm roll, monospace sized for 48 columns, easypunto logo on
 * top and bottom, `@page { size: 80mm auto; margin: 0 }`. The two
 * channels therefore cannot drift apart.
 *
 * The DOM work (transient container + `window.print()`) lives in `printHtml.ts`
 * and is re-exported here for the callers that import it from this module.
 *
 * Coupling: this module is DOM-free apart from the re-exported `printHtml`.
 * The caller controls when to print (DEC-SUC-27 — orden impresión).
 */

import type { EntradaPayload, TiqueteTipo } from './escposTemplates';
import { EscposInvalidTipoError, EscposPayloadMissingFieldError, lineasDeTiquete } from './escposBuilder';
import { construirEntrada } from './tiqueteLineas';
import { lineasAHtml } from './facturaPrint';
import { PAGE_RULE, printHtml } from './printHtml';

export { PAGE_RULE, printHtml };

/** HTML `data-testid` of a ticket: `tiquete-<tipo>-print` (browser verification hook). */
export function testidTiquete(tipo: TiqueteTipo): string {
  return `tiquete-${tipo.replace(/_/g, '-')}-print`;
}

/**
 * Validate `tipo` + `payload` and render the ticket HTML (no printing).
 * Throws:
 *   - `EscposInvalidTipoError` if `tipo` is not allowed.
 *   - `EscposPayloadMissingFieldError` if Zod parse fails.
 * Shared with `tiquetePrint.ts` (browser channel).
 */
export function renderTiqueteHtml(tipo: TiqueteTipo, payload: unknown): string {
  return lineasAHtml(lineasDeTiquete(tipo, payload), testidTiquete(tipo));
}

/** HTML of an already-typed entrada payload (no validation, no printing). */
export function renderEntradaTiqueteHtml(payload: EntradaPayload): string {
  return lineasAHtml(construirEntrada(payload), testidTiquete('entrada'));
}

/** Render the ticket and trigger `window.print()` once. Same throws as `renderTiqueteHtml`. */
export function print(tipo: TiqueteTipo, payload: unknown): void {
  printHtml(renderTiqueteHtml(tipo, payload));
}

// Re-export the error classes so callers have a single import surface.
export { EscposInvalidTipoError, EscposPayloadMissingFieldError };
