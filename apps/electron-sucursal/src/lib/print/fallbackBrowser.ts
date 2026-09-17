/**
 * `fallbackBrowser.ts` — DOM-target fallback for the thermal printer.
 *
 * HU-F5.2 (Fase 5 — base de impresión) / DEC-SUC-08.
 *
 * When the thermal printer does not respond (caller-driven signal — F5.2
 * only owns rendering + invocation, F5.1's bridge decides IF), this
 * module renders the same semantic content as a transient `<div>`,
 * injects a `<style>` declaring `@page { size: 80mm auto; margin: 2mm }`
 * (DEC-SUC-08 verbatim), and calls `window.print()`. The injected
 * `<style>` is removed from the DOM after the print call resolves.
 *
 * Coupling:
 *   - This module is DOM-bound — it is the ONLY file in `src/lib/print/`
 *     that touches `window`, `document`, or `Element`. The byte builder
 *     (`escposBuilder.ts`) is DOM-free.
 *   - Caller controls when to invoke (`print` is not exported as a side
 *     effect; it MUST be called explicitly). See DEC-SUC-27 (orden
 *     impresión) — caller decides CUÁNDO.
 */

import {
  type EntradaPayload,
  type SalidaPayload,
  type SalidaMensualidadPayload,
  type ReimpresionPayload,
  type TiqueteTipo,
  entradaPayloadSchema,
  salidaPayloadSchema,
  salidaMensualidadPayloadSchema,
  reimpresionPayloadSchema,
  formatCOP,
} from './escposTemplates';
import {
  EscposInvalidTipoError,
  EscposPayloadMissingFieldError,
  isTiqueteTipo,
  validatePayload,
} from './escposBuilder';

// ──────────────────────────────────────────────────────────────────────────
// Page-style injection
// ──────────────────────────────────────────────────────────────────────────

/**
 * The `<style>` rule — DEC-SUC-08 verbatim. Thermal-paper width 80mm,
 * auto height, 2mm margin on every side.
 */
export const PAGE_RULE = '@page { size: 80mm auto; margin: 2mm }';

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

function cleanupPageStyle(): void {
  if (typeof document === 'undefined') return;
  const node = document.getElementById(STYLE_ID);
  if (node !== null) node.parentNode?.removeChild(node);
}

// ──────────────────────────────────────────────────────────────────────────
// HTML renderers — mirror escposBuilder body in semantic tags
// ──────────────────────────────────────────────────────────────────────────

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fechaCorta(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${dd}/${mm}/${yyyy} ${hh}:${min}`;
}

function renderEntradaHtml(payload: EntradaPayload): string {
  const poliza = payload.polizaRC
    ? `<p>Poliza RC: ${escapeHtml(payload.polizaRC)}</p>`
    : '';
  return `
    <h1>PARKINGOS</h1>
    <p>${escapeHtml(payload.empresa.nombre)}</p>
    <p>NIT ${escapeHtml(payload.empresa.nit)}</p>
    <p>${escapeHtml(payload.empresa.direccion)}</p>
    <p>${escapeHtml(payload.empresa.regimen)}</p>
    <h2>*** ENTRADA ***</h2>
    <p>Folio: ${escapeHtml(payload.folio)}</p>
    <p>Placa: ${escapeHtml(payload.placa)}</p>
    <p>Fecha: ${fechaCorta(payload.fechaEntrada)}</p>
    <p>Operario: ${escapeHtml(payload.operario)}</p>
    <p>Tarifa: ${formatCOP(payload.tarifaAplicada)}/hora</p>
    <p>Horario: ${escapeHtml(payload.horarioAtencion)}</p>
    ${poliza}
    <p>Conserve este tiquete para la salida.</p>
  `;
}

function renderSalidaHtml(payload: SalidaPayload): string {
  const poliza = payload.polizaRC
    ? `<p>Poliza RC: ${escapeHtml(payload.polizaRC)}</p>`
    : '';
  return `
    <h1>PARKINGOS</h1>
    <p>${escapeHtml(payload.empresa.nombre)}</p>
    <p>NIT ${escapeHtml(payload.empresa.nit)}</p>
    <p>${escapeHtml(payload.empresa.direccion)}</p>
    <p>${escapeHtml(payload.empresa.regimen)}</p>
    <h2>*** SALIDA ***</h2>
    <p>Folio: ${escapeHtml(payload.folio)}</p>
    <p>Placa: ${escapeHtml(payload.placa)}</p>
    <p>Entrada: ${fechaCorta(payload.fechaEntrada)}</p>
    <p>Salida:  ${fechaCorta(payload.fechaSalida)}</p>
    <p>Tiempo: ${escapeHtml(payload.tiempoTotal)}</p>
    <p>Subtotal: ${formatCOP(payload.subtotal)}</p>
    <p>IVA: ${formatCOP(payload.iva)}</p>
    <p><strong>TOTAL: ${formatCOP(payload.total)}</strong></p>
    <p>Medio de pago: ${escapeHtml(payload.medioPago)}</p>
    <p>Resolucion FE: ${escapeHtml(payload.resolucionFE)}</p>
    ${poliza}
    <p>Gracias por su visita.</p>
  `;
}

function renderSalidaMensualidadHtml(payload: SalidaMensualidadPayload): string {
  const poliza = payload.polizaRC
    ? `<p>Poliza RC: ${escapeHtml(payload.polizaRC)}</p>`
    : '';
  return `
    <h1>PARKINGOS</h1>
    <p>${escapeHtml(payload.empresa.nombre)}</p>
    <p>NIT ${escapeHtml(payload.empresa.nit)}</p>
    <p>${escapeHtml(payload.empresa.direccion)}</p>
    <p>${escapeHtml(payload.empresa.regimen)}</p>
    <h2>*** PAGO CON MENSUALIDAD ***</h2>
    <p>Folio: ${escapeHtml(payload.folio)}</p>
    <p>Placa: ${escapeHtml(payload.placa)}</p>
    <p>Entrada: ${fechaCorta(payload.fechaEntrada)}</p>
    <p>Salida:  ${fechaCorta(payload.fechaSalida)}</p>
    <p>Operario: ${escapeHtml(payload.operario)}</p>
    <p>Horario: ${escapeHtml(payload.horarioAtencion)}</p>
    ${poliza}
    <p>Conserve este tiquete como soporte.</p>
  `;
}

function renderReimpresionHtml(payload: ReimpresionPayload): string {
  const header = `
    <h1>PARKINGOS</h1>
    <p>${escapeHtml(payload.empresa.nombre)}</p>
    <p>NIT ${escapeHtml(payload.empresa.nit)}</p>
    <p>${escapeHtml(payload.empresa.direccion)}</p>
    <p>${escapeHtml(payload.empresa.regimen)}</p>
    <h2>*** REIMPRESION ***</h2>
    <p>Motivo: ${escapeHtml(payload.motivo)}</p>
    <p>Folio original: ${escapeHtml(payload.folioOriginal)}</p>
  `;
  let body: string;
  switch (payload.originalTipo) {
    case 'entrada':
      body = renderEntradaHtml(payload.payload);
      break;
    case 'salida':
      body = renderSalidaHtml(payload.payload);
      break;
    case 'salida-mensualidad':
      body = renderSalidaMensualidadHtml(payload.payload);
      break;
  }
  return `${header}\n${body}`;
}

// ──────────────────────────────────────────────────────────────────────────
// Top-level dispatcher
// ──────────────────────────────────────────────────────────────────────────

/**
 * Render the tiquete and trigger `window.print()`. Injects the
 * DEC-SUC-08 `@page` rule, calls `window.print()` exactly once, and
 * cleans up the injected `<style>` afterward.
 *
 * Throws:
 *   - `EscposInvalidTipoError` if `tipo` is not in the 4-allowed union.
 *   - `EscposPayloadMissingFieldError` if Zod parse fails.
 */
export function print(tipo: TiqueteTipo, payload: unknown): void {
  if (!isTiqueteTipo(tipo)) {
    throw new EscposInvalidTipoError(String(tipo));
  }
  const issues = validatePayload(tipo, payload);
  if (issues !== null) {
    throw new EscposPayloadMissingFieldError(issues);
  }

  let html: string;
  switch (tipo) {
    case 'entrada': {
      const p = entradaPayloadSchema.parse(payload) as EntradaPayload;
      html = renderEntradaHtml(p);
      break;
    }
    case 'salida': {
      const p = salidaPayloadSchema.parse(payload) as SalidaPayload;
      html = renderSalidaHtml(p);
      break;
    }
    case 'salida-mensualidad': {
      const p = salidaMensualidadPayloadSchema.parse(payload) as SalidaMensualidadPayload;
      html = renderSalidaMensualidadHtml(p);
      break;
    }
    case 'reimpresion': {
      const p = reimpresionPayloadSchema.parse(payload) as ReimpresionPayload;
      html = renderReimpresionHtml(p);
      break;
    }
    default:
      throw new EscposInvalidTipoError(String(tipo));
  }

  injectPageStyle();
  try {
    // Render the HTML into a transient container so the print preview
    // shows the same content as the ESC/POS body. The container is left
    // in the DOM (off-screen) so the print dialog renders it; the caller
    // is responsible for removing it after the dialog closes
    // (out of F5.2 scope — caller wires F5.1 + F5.2 lifecycle).
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
    container.innerHTML = html;
    window.print();
  } finally {
    cleanupPageStyle();
  }
}

// Re-export the error classes so callers have a single import surface.
export { EscposInvalidTipoError, EscposPayloadMissingFieldError };