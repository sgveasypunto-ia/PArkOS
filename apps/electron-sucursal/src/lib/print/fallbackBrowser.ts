/**
 * `fallbackBrowser.ts` — DOM-target fallback for the thermal printer.
 *
 * HU-F5.2 (Fase 5 — base de impresión) / DEC-SUC-08.
 * HU-F6.2 (Fase 6 — tiquete de entrada CU-15E) / DEC-SUC-26.
 * HU-F7.3 (Fase 7 — tiquetes de salida + salida-mensualidad) / DEC-SUC-28.
 *
 * When the thermal printer does not respond (caller-driven signal — F5.2
 * only owns rendering + invocation, F5.1's bridge decides IF), this
 * module renders the same semantic content as a transient `<div>`,
 * injects a `<style>` declaring `@page { size: 80mm auto; margin: 2mm }`
 * (DEC-SUC-08 verbatim), and calls `window.print()`. The injected
 * `<style>` is removed from the DOM after the print call resolves.
 *
 * F6.2 — `renderEntradaTiqueteHtml(payload)` mirrors the 17-field
 * layout of `escposBuilder.buildEntradaBuffer()` in semantic
 * `<h1>` / `<p>` / `<img>` tags. QR + logo render as inline `<img>`
 * with their data URLs verbatim (the browser print dialog rasterizes
 * them automatically). When `payload.esMensualidad === true`, the
 * renderer emits a `<strong>MENSUALIDAD</strong>` tag under the sello.
 * Empty `logoDataUrl` renders the placeholder glyph `▢` per
 * `design.md` §"Render-time guard for missing `documentos` row".
 *
 * F7.3 (DEC-SUC-28) — all four HTML renderers (`entrada`, `salida`,
 * `salida-mensualidad`, `reimpresion`) read `<h1>` from
 * `payload.sucursal.encabezado` (dynamic branch header), NOT the
 * F5.2 "PARKINGOS" literal. Drift guard:
 * `grep -r 'PARKINGOS' apps/electron-sucursal/src/lib/print` returns
 * 0 matches after this commit lands.
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
  type ReciboPagoPayload,
  type TiqueteTipo,
  entradaPayloadSchema,
  salidaPayloadSchema,
  salidaMensualidadPayloadSchema,
  reimpresionPayloadSchema,
  reciboPagoPayloadSchema,
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

/**
 * `renderEntradaTiqueteHtml(payload)` — F6.2 17-field HTML layout.
 *
 * Mirrors the `escposBuilder.buildEntradaBuffer()` body in semantic
 * `<h1>` / `<p>` / `<img>` tags. The 17 conceptual fields live in
 * `escposTemplates.ts::TiqueteEntradaCampos` (Spanish ordinals).
 *
 *   primero        → Encabezado           → `<h1>{sucursal.encabezado}</h1>` (DEC-SUC-28)
 *   segundo        → Nombre de la empresa → `<p>{empresa.nombre}</p>`
 *   tercero        → Dirección            → `<p>{empresa.direccion}</p>`
 *   cuarto         → NIT                  → `<p>NIT {empresa.nit}</p>`
 *   quinto         → Régimen              → `<p>{empresa.regimen}</p>`
 *   sexto          → Operario             → `<p>Operario: {operario}</p>`
 *   septimo        → Sello                → `<h2>*** TIQUETE DE ENTRADA ***</h2>`
 *   octavo         → Folio                → `<p>Folio: {folio}</p>`
 *   noveno         → Tarifa aplicada      → `<p>Tarifa: {formatCOP}/hora</p>`
 *   decimo         → Fecha operación      → `<p>Fecha: dd/MM/yyyy</p>`
 *   onceavo        → Hora entrada         → `<p>Hora: HH:mm</p>`
 *   doceavo        → Placa                → `<p>Placa: {placa}</p>`
 *   treceavo       → Horario atención     → `<p>Horario: {horario}</p>`
 *   catorceavo     → Póliza RC            → `<p>Poliza RC: {poliza}</p>` (optional)
 *   quinceavo      → Observaciones        → `<p>Observaciones: ...</p>` (optional)
 *   qrDataUrl      → QR                   → `<img src="{qrDataUrl}" />`
 *   logoDataUrl    → Logo                 → `<img src="{logoDataUrl}" />` or `▢`
 *
 * Mensualidad tag (DEC-SUC-21): `<strong>MENSUALIDAD</strong>` emitted
 * under the sello when `payload.esMensualidad === true`.
 *
 * Logo placeholder (DEC-SUC-08): when `payload.logoDataUrl === ''`,
 * the renderer emits the glyph `▢` instead of an `<img>` so the
 * operator sees the tiquete is OK to print.
 */
export function renderEntradaTiqueteHtml(payload: EntradaPayload): string {
  const poliza = payload.polizaRC
    ? `<p>Poliza RC: ${escapeHtml(payload.polizaRC)}</p>`
    : '';
  const observaciones = payload.observaciones
    ? `<p>Observaciones: ${escapeHtml(payload.observaciones)}</p>`
    : '';
  const mensualidadTag = payload.esMensualidad === true
    ? '<p><strong>MENSUALIDAD</strong></p>'
    : '';
  const logoHtml = payload.logoDataUrl === ''
    ? '<p>Logo: \u25A2</p>'
    : `<p><img src="${escapeHtml(payload.logoDataUrl)}" alt="Logo" /></p>`;
  const fechaParts = fechaCorta(payload.fechaEntrada).split(' ');
  const fechaStr = fechaParts[0] ?? '';
  const horaStr = fechaParts[1] ?? '';
  // REQ-OPS-197 — doceavo (12th conceptual field) branches on variant.
  // TypeScript narrows `payload.placa` / `payload.consecutivo` per
  // the discriminated union; the runtime check is the discriminator
  // value.
  const identificacionLine = payload.variant === 'con-placa'
    ? `<p>Placa: ${escapeHtml(payload.placa)}</p>`
    : `<p>Identificación: ${escapeHtml(payload.consecutivo)}</p>`;
  return `
    <h1>${escapeHtml(payload.sucursal.encabezado)}</h1>
    ${logoHtml}
    <p>${escapeHtml(payload.empresa.nombre)}</p>
    <p>${escapeHtml(payload.empresa.direccion)}</p>
    <p>NIT ${escapeHtml(payload.empresa.nit)}</p>
    <p>${escapeHtml(payload.empresa.regimen)}</p>
    <p>Operario: ${escapeHtml(payload.operario)}</p>
    <h2>*** TIQUETE DE ENTRADA ***</h2>
    ${mensualidadTag}
    <p>Folio: ${escapeHtml(payload.folio)}</p>
    <p>Tarifa: ${formatCOP(payload.tarifaAplicada)}/hora</p>
    <p>Fecha: ${fechaStr}</p>
    <p>Hora: ${horaStr}</p>
    ${identificacionLine}
    <p>Horario: ${escapeHtml(payload.horarioAtencion)}</p>
    ${poliza}
    ${observaciones}
    <p><img src="${escapeHtml(payload.qrDataUrl)}" alt="QR ingreso" /></p>
    <p>Conserve este tiquete para la salida.</p>
  `;
}

/**
 * Backward-compatible alias for the F5.2 reimpresion dispatcher.
 * `renderReimpresionHtml` calls `renderEntradaHtml(payload.payload)`
 * when `originalTipo === 'entrada'`; F6.2 renamed the public entry
 * to `renderEntradaTiqueteHtml`. This alias preserves the call site
 * without modifying `renderReimpresionHtml`.
 */
const renderEntradaHtml = renderEntradaTiqueteHtml;

function renderSalidaHtml(payload: SalidaPayload): string {
  const poliza = payload.polizaRC
    ? `<p>Poliza RC: ${escapeHtml(payload.polizaRC)}</p>`
    : '';
  return `
    <h1>${escapeHtml(payload.sucursal.encabezado)}</h1>
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
    <h1>${escapeHtml(payload.sucursal.encabezado)}</h1>
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
  // F7.3 (DEC-SUC-28) — the reimpresion envelope uses the inner
  // payload's `sucursal.encabezado` (the inner payload already carries
  // the dynamic header post-F7.3). The discriminated union narrows
  // `payload.payload` to one of the three subtypes — all three carry
  // `sucursal.encabezado` after F7.3.
  const innerSucursalEncabezado = payload.payload.sucursal.encabezado;
  const header = `
    <h1>${escapeHtml(innerSucursalEncabezado)}</h1>
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

function renderReciboPagoHtml(payload: ReciboPagoPayload): string {
  // F8.1 (HU-F8.1) — HTML fallback for the recibo de pago. Mirrors
  // `renderSalidaHtml` with two swaps:
  //   - Sello slot uses `*** RECIBO DE PAGO ***` (NOT `*** SALIDA ***`).
  //   - `Medio de pago:` line uses the typed `payload.medio_pago`.
  // Plus a leading `Numero de recibo:` line per DEC-SUC-28.
  const poliza = payload.polizaRC
    ? `<p>Poliza RC: ${escapeHtml(payload.polizaRC)}</p>`
    : '';
  return `
    <h1>${escapeHtml(payload.sucursal.encabezado)}</h1>
    <p>${escapeHtml(payload.empresa.nombre)}</p>
    <p>NIT ${escapeHtml(payload.empresa.nit)}</p>
    <p>${escapeHtml(payload.empresa.direccion)}</p>
    <p>${escapeHtml(payload.empresa.regimen)}</p>
    <h2>*** RECIBO DE PAGO ***</h2>
    <p>Numero de recibo: ${escapeHtml(payload.numero_recibo)}</p>
    <p>Folio: ${escapeHtml(payload.folio)}</p>
    <p>Placa: ${escapeHtml(payload.placa)}</p>
    <p>Entrada: ${fechaCorta(payload.fechaEntrada)}</p>
    <p>Salida:  ${fechaCorta(payload.fechaSalida)}</p>
    <p>Tiempo: ${escapeHtml(payload.tiempoTotal)}</p>
    <p>Subtotal: ${formatCOP(payload.subtotal)}</p>
    <p>IVA: ${formatCOP(payload.iva)}</p>
    <p><strong>TOTAL: ${formatCOP(payload.total)}</strong></p>
    <p>Medio de pago: ${escapeHtml(payload.medio_pago)}</p>
    <p>Resolucion FE: ${escapeHtml(payload.resolucionFE)}</p>
    ${poliza}
    <p>Gracias por su pago.</p>
  `;
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
 *   - `EscposInvalidTipoError` if `tipo` is not in the 5-allowed union.
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
      // F6.2 — dispatcher calls the renamed 17-field renderer.
      html = renderEntradaTiqueteHtml(p);
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
    case 'recibo_pago': {
      const p = reciboPagoPayloadSchema.parse(payload) as ReciboPagoPayload;
      html = renderReciboPagoHtml(p);
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