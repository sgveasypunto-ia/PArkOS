/**
 * `escposBuilder.ts` — pure renderer-side ESC/POS byte composition.
 *
 * HU-F5.2 (Fase 5 — base de impresión) / DEC-SUC-08.
 * HU-F6.2 (Fase 6 — tiquete de entrada CU-15E) / DEC-SUC-26.
 *
 * Contract (F5.1 `bridge.imprimir` consumer):
 *   `build(tipo, payload) → Buffer`
 *
 * The returned `Buffer` MUST contain, in order:
 *   1. `0x1B 0x40` — ESC `@` (init)
 *   2. ...document body (UTF-8)...
 *   3. `0x1B 0x61 0x01` — ESC `a` 1 (centered, for header)
 *   4. `0x1B 0x21 0x30` — ESC `!` 0x30 (text 2x height for sellos)
 *   5. `0x1B 0x45` / `0x1B 0x46` — bold on / off
 *   6. ...document body (UTF-8)...
 *   7. `0x1D 0x56 0x00` — GS `V` 0 (partial cut)
 *   8. `0x0A` — LF (line feed)
 *
 * F6.2 — `buildEntradaBuffer()` (and its underlying `buildEntradaBody`)
 * emits the **17 conceptual fields** in the order specified by
 * `plan.md` lines 1616-1634 plus the 2 DEC-SUC-26 additions (QR + logo)
 * — see `escposTemplates.ts::TiqueteEntradaCampos` for the canonical
 * 17-key shape. The QR + logo data URLs are emitted as text markers
 * (the actual rasterization is the CALLER's responsibility per F5.2
 * R4 purity + the F6.2 design decision "QR encoding is the caller's
 * responsibility"). When `payload.esMensualidad === true`, the
 * builder emits a `MENSUALIDAD` tag line under the sello.
 *
 * Purity contract:
 *   - NO DOM, NO `window`, NO `document`, NO `navigator`.
 *   - NO network, NO filesystem, NO USB, NO IPC.
 *   - NO electron / escpos-usb / node:* imports (verified by `grep -E
 *     "from '(electron|escpos-usb|node:)'"` — see `tasks.md` §4.4).
 *   - All timestamps are caller-supplied (no `new Date()`).
 *
 * Error surface (named subclasses for `instanceof` checks):
 *   - `EscposInvalidTipoError` — `tipo` is not in the 5-allowed union.
 *   - `EscposPayloadMissingFieldError` — Zod parse failed; `err.issues`
 *     carries the underlying Zod issues.
 */

import type { z } from 'zod';

import {
  TIQUETE_TIPOS,
  entradaPayloadSchema,
  salidaPayloadSchema,
  salidaMensualidadPayloadSchema,
  reimpresionPayloadSchema,
  reciboPagoPayloadSchema,
  formatCOP,
  formatFecha,
  formatHora,
  type EntradaPayload,
  type SalidaPayload,
  type SalidaMensualidadPayload,
  type ReimpresionPayload,
  type ReciboPagoPayload,
  type TiqueteTipo,
} from './escposTemplates';

// ──────────────────────────────────────────────────────────────────────────
// Error classes
// ──────────────────────────────────────────────────────────────────────────

/**
 * Thrown by `build()` when the `tipo` argument is not in the 5-allowed
 * union. Carries the offending `given` string and a stable `code` for
 * callers to discriminate on (instead of `instanceof` chains).
 */
export class EscposInvalidTipoError extends Error {
  readonly code = 'escpos_invalid_tipo' as const;
  readonly given: string;

  constructor(given: string) {
    super(`Invalid tiquete tipo: '${given}'`);
    this.name = 'EscposInvalidTipoError';
    this.given = given;
  }
}

/**
 * Thrown by `build()` when the `payload` argument fails Zod validation.
 * `issues` is the array of Zod issues (mirroring `z.ZodError['issues']`)
 * so callers can surface specific field-level errors.
 */
export class EscposPayloadMissingFieldError extends Error {
  readonly code = 'escpos_payload_missing_field' as const;
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super('Payload failed Zod validation');
    this.name = 'EscposPayloadMissingFieldError';
    this.issues = issues;
  }
}

// ──────────────────────────────────────────────────────────────────────────
// ESC/POS opcode helpers
// ──────────────────────────────────────────────────────────────────────────

/** `0x1B 0x40` — ESC `@` — Initialize printer (reset state). */
export function escInit(): Buffer {
  return Buffer.from([0x1b, 0x40]);
}

/** `0x1B 0x61 0x01` — ESC `a` 1 — Center alignment on. */
export function escCenter(): Buffer {
  return Buffer.from([0x1b, 0x61, 0x01]);
}

/** `0x1B 0x61 0x00` — ESC `a` 0 — Left alignment (reset). */
export function escLeft(): Buffer {
  return Buffer.from([0x1b, 0x61, 0x00]);
}

/** `0x1B 0x45` — ESC `E` — Bold on. */
export function escBoldOn(): Buffer {
  return Buffer.from([0x1b, 0x45]);
}

/** `0x1B 0x46` — ESC `F` — Bold off. */
export function escBoldOff(): Buffer {
  return Buffer.from([0x1b, 0x46]);
}

/** `0x1B 0x21 0x30` — ESC `!` 0x30 — Text 2x height (DEC-SUC-04 sellos). */
export function escText2x(): Buffer {
  return Buffer.from([0x1b, 0x21, 0x30]);
}

/** `0x1B 0x21 0x00` — ESC `!` 0x00 — Text size reset (1x1). */
export function escTextReset(): Buffer {
  return Buffer.from([0x1b, 0x21, 0x00]);
}

/** `0x1D 0x56 0x00` — GS `V` 0 — Partial cut (DEC-SUC-08 close). */
export function cutPartial(): Buffer {
  return Buffer.from([0x1d, 0x56, 0x00]);
}

/** `0x0A` — LF — line feed (after cut, recommended for the print buffer). */
export function lf(): Buffer {
  return Buffer.from([0x0a]);
}

// ──────────────────────────────────────────────────────────────────────────
// UTF-8 string helper
// ──────────────────────────────────────────────────────────────────────────

function utf8(text: string): Buffer {
  return Buffer.from(text, 'utf8');
}

// ──────────────────────────────────────────────────────────────────────────
// Body builders per tipo
// ──────────────────────────────────────────────────────────────────────────

/** Concatenate an array of Buffers into one. */
function concat(parts: readonly Buffer[]): Buffer {
  return Buffer.concat(parts);
}

/** F6.2 — placeholder glyph for missing logo (DEC-SUC-08). */
const LOGO_PLACEHOLDER_GLYPH = '\u25A2'; // ▢ WHITE SQUARE WITH ROUNDED CORNERS

function buildEntradaBody(payload: EntradaPayload): Buffer {
  // F6.2 — 17-field layout per `plan.md` lines 1616-1634 + DEC-SUC-26.
  // The conceptual field names live in
  // `escposTemplates.ts::TiqueteEntradaCampos` (Spanish ordinals).
  //
  // F7.3 (DEC-SUC-28) — the header is `payload.sucursal.encabezado`
  // (dynamic branch header). NOT the F5.2 "PARKINGOS" constant.
  const lines: Buffer[] = [
    escCenter(),
    escBoldOn(),
    utf8(`${payload.sucursal.encabezado}\n`),           // primero (Encabezado)
    escBoldOff(),
    utf8(`${payload.empresa.nombre}\n`),                // segundo
    utf8(`${payload.empresa.direccion}\n`),             // tercero
    utf8(`NIT ${payload.empresa.nit}\n`),               // cuarto
    utf8(`${payload.empresa.regimen}\n`),               // quinto
    utf8(`Operario: ${payload.operario}\n`),            // sexto
    utf8('\n'),
    escText2x(),
    utf8('*** TIQUETE DE ENTRADA ***\n'),               // septimo (sello)
    escTextReset(),
  ];
  // F6.2 — Mensualidad tag conditional (DEC-SUC-21 — derived from
  // `ingreso.uuid_subscripcion_cliente IS NOT NULL`).
  if (payload.esMensualidad === true) {
    lines.push(escBoldOn());
    lines.push(utf8('MENSUALIDAD\n'));
    lines.push(escBoldOff());
  }
  lines.push(utf8('\n'));
  lines.push(utf8(`Folio: ${payload.folio}\n`));        // octavo
  lines.push(utf8(`Tarifa: ${formatCOP(payload.tarifaAplicada)}/hora\n`)); // noveno
  lines.push(utf8(`Fecha: ${formatFecha(payload.fechaEntrada)}\n`)); // decimo
  lines.push(utf8(`Hora: ${formatHora(payload.fechaEntrada)}\n`));    // onceavo
  lines.push(utf8(`Placa: ${payload.placa}\n`));        // doceavo
  lines.push(utf8(`Horario: ${payload.horarioAtencion}\n`)); // treceavo
  if (payload.polizaRC) {
    lines.push(utf8(`Poliza RC: ${payload.polizaRC}\n`)); // catorceavo
  }
  if (payload.observaciones) {
    lines.push(utf8(`Observaciones: ${payload.observaciones}\n`)); // quinceavo
  }
  // F6.2 — DEC-SUC-26: QR + logo. The data URLs are emitted as text
  // markers — the printer firmware ignores lines starting with `;`
  // (comment), and the `bridge.imprimir` layer in F5.1 can intercept
  // these for actual rasterization in a future enhancement. Empty
  // `logoDataUrl` renders the placeholder glyph (design §"Render-time
  // guard for missing `documentos` row").
  const logoText = payload.logoDataUrl === ''
    ? LOGO_PLACEHOLDER_GLYPH
    : 'OK';
  lines.push(utf8(`;QR:${payload.qrDataUrl}\n`));       // qrDataUrl
  lines.push(utf8(`;LOGO:${logoText}\n`));              // logoDataUrl
  lines.push(utf8('\n'));
  lines.push(utf8('Conserve este tiquete para la salida.\n'));
  return concat(lines);
}

function buildSalidaBody(payload: SalidaPayload): Buffer {
  // F7.3 (HU-F7.3 / REQ-OPS-158) — 19-field CU-15S layout per
  // `plan.md:1789-1807` + 2 DEC-SUC-26 additions (QR + logo markers).
  //
  // The header is `payload.sucursal.encabezado` (DEC-SUC-28 dynamic),
  // NOT the F5.2 "PARKINGOS" constant. The `;QR:` + `;LOGO:` text
  // markers mirror F6.2 — the actual rasterization is the CALLER's
  // responsibility per F5.2 R4 purity (see
  // `escposBuilder.ts:223-234` precedent on the entrada body).
  const lines: Buffer[] = [
    escCenter(),
    escBoldOn(),
    utf8(`${payload.sucursal.encabezado}\n`),                 // 1: Encabezado
    escBoldOff(),
    utf8(`${payload.empresa.nombre}\n`),                      // 2: Empresa
    utf8(`${payload.empresa.direccion}\n`),                   // 3: Dirección
    utf8(`NIT ${payload.empresa.nit}\n`),                     // 4: NIT
    utf8(`${payload.empresa.regimen}\n`),                     // 5: Régimen
    utf8(`Operario: ${payload.operario}\n`),                  // 6: Operario
    utf8('\n'),
    escText2x(),
    utf8('*** SALIDA ***\n'),                                 // 7: Sello
    escTextReset(),
    utf8('\n'),
    utf8(`Folio: ${payload.folio}\n`),                        // 8: Folio
    utf8(`Tarifa: ${formatCOP(payload.tarifaAplicada)}/hora\n`), // 9: Tarifa
    utf8(`Fecha: ${formatFecha(payload.fechaEntrada)}\n`),    // 10: Fecha (date-only)
    utf8(`Hora entrada: ${formatHora(payload.fechaEntrada)}\n`), // 11: Hora entrada
    utf8(`Hora salida: ${formatHora(payload.fechaSalida)}\n`),  // 12: Hora salida
    utf8(`Tiempo: ${payload.tiempoTotal}\n`),                 // 13: Tiempo total
    utf8('\n'),
    utf8(`Subtotal: ${formatCOP(payload.subtotal)}\n`),       // 14: Subtotal
    utf8(`IVA: ${formatCOP(payload.iva)}\n`),                 // 15: IVA
    escBoldOn(),
    utf8(`TOTAL: ${formatCOP(payload.total)}\n`),             // 16: TOTAL
    escBoldOff(),
    utf8(`Medio de pago: ${payload.medioPago}\n`),            // 17: Medio de pago
    utf8(`Placa: ${payload.placa}\n`),                        // 18: Placa
    utf8(`Horario: ${payload.horarioAtencion}\n`),            // 19a: Horario atención
  ];
  if (payload.polizaRC) {
    lines.push(utf8(`Poliza RC: ${payload.polizaRC}\n`));     // 19b: Póliza RC
  }
  lines.push(utf8(`Resolucion FE: ${payload.resolucionFE}\n`));// 19c: Resolución FE
  if (payload.observaciones) {
    lines.push(utf8(`Observaciones: ${payload.observaciones}\n`)); // 19d: Observaciones
  }
  // F7.3 — DEC-SUC-26 QR + logo markers (mirror F6.2 entrada precedent).
  // The caller is responsible for the actual rasterization; the buffer
  // emits the `;`-prefixed text markers only so the printer firmware
  // ignores them and the F5.1 bridge can intercept for future
  // rasterization.
  const logoText = payload.logoDataUrl === ''
    ? LOGO_PLACEHOLDER_GLYPH
    : 'OK';
  lines.push(utf8(`;QR:${payload.qrDataUrl}\n`));
  lines.push(utf8(`;LOGO:${logoText}\n`));
  lines.push(utf8('\n'));
  lines.push(utf8('Gracias por su visita.\n'));
  return concat(lines);
}

function buildSalidaMensualidadBody(payload: SalidaMensualidadPayload): Buffer {
  // F7.3 (HU-F7.3 / REQ-OPS-159) — 15-field CU-15SM layout per
  // `plan.md:1810` + 2 DEC-SUC-26 additions (QR + logo markers).
  //
  // DEC-SUC-27 invariant: the sello `*** PAGO CON MENSUALIDAD ***` is
  // wrapped by `escText2x()` (text 2x height) before and
  // `escTextReset()` (1x1 reset) after — visual distinguisher that
  // prevents the cajero from confusing a tiquete sin cobro with one
  // cobrado (CU-15S uses `*** SALIDA ***` instead).
  //
  // NO monetary fields (DEC-SUC-23): the mensualidad fee is settled
  // by the subscription, NOT the exit. The buffer MUST NOT contain
  // `Subtotal:`, `IVA:`, `TOTAL:`, or `Medio de pago:`.
  //
  // The header is `payload.sucursal.encabezado` (DEC-SUC-28 dynamic),
  // NOT the F5.2 "PARKINGOS" constant.
  const lines: Buffer[] = [
    escCenter(),
    escBoldOn(),
    utf8(`${payload.sucursal.encabezado}\n`),               // 1: Encabezado
    escBoldOff(),
    utf8(`${payload.empresa.nombre}\n`),                    // 2: Empresa
    utf8(`NIT ${payload.empresa.nit}\n`),                   // 4: NIT
    utf8(`${payload.empresa.direccion}\n`),                 // 3: Dirección
    utf8(`${payload.empresa.regimen}\n`),                   // 5: Régimen
    utf8(`Operario: ${payload.operario}\n`),                // 6: Operario
    utf8('\n'),
    escText2x(),
    utf8('*** PAGO CON MENSUALIDAD ***\n'),                 // 7: Sello (DEC-SUC-27)
    escTextReset(),
    utf8('\n'),
    utf8(`Folio: ${payload.folio}\n`),                      // 8: Folio
    utf8(`Fecha: ${formatFecha(payload.fechaEntrada)}\n`),  // 9: Fecha (date-only)
    utf8(`Hora entrada: ${formatHora(payload.fechaEntrada)}\n`), // 10: Hora entrada
    utf8(`Hora salida: ${formatHora(payload.fechaSalida)}\n`),   // 11: Hora salida
    utf8(`Tiempo: ${payload.tiempoTotal}\n`),               // 12: Tiempo total
    utf8(`Placa: ${payload.placa}\n`),                      // 13: Placa
    utf8(`Horario: ${payload.horarioAtencion}\n`),          // 14: Horario atención
  ];
  if (payload.polizaRC) {
    lines.push(utf8(`Poliza RC: ${payload.polizaRC}\n`));   // 15a: Póliza RC
  }
  if (payload.observaciones) {
    lines.push(utf8(`Observaciones: ${payload.observaciones}\n`)); // 15b: Observaciones
  }
  // F7.3 — DEC-SUC-26 QR + logo markers (mirror F6.2 entrada precedent).
  const logoText = payload.logoDataUrl === ''
    ? LOGO_PLACEHOLDER_GLYPH
    : 'OK';
  lines.push(utf8(`;QR:${payload.qrDataUrl}\n`));
  lines.push(utf8(`;LOGO:${logoText}\n`));
  lines.push(utf8('\n'));
  lines.push(utf8('Conserve este tiquete como soporte.\n'));
  return concat(lines);
}

function buildReimpresionBody(payload: ReimpresionPayload): Buffer {
  // F7.3 (DEC-SUC-28) — reimpresion envelopes its inner body (entrada /
  // salida / salida-mensualidad) which already carry the dynamic
  // header. The reimpresion-specific header uses
  // `payload.empresa.nombre` only as a fallback; for dynamic header
  // parity, we extract `sucursal.encabezado` from the inner payload.
  // The discriminated union narrows `payload.payload` to one of the
  // three subtypes — all three carry `sucursal.encabezado` after F7.3.
  const innerSucursalEncabezado = payload.payload.sucursal.encabezado;
  const header: Buffer[] = [
    escCenter(),
    escBoldOn(),
    utf8(`${innerSucursalEncabezado}\n`),               // DEC-SUC-28 dynamic
    escBoldOff(),
    utf8(`${payload.empresa.nombre}\n`),
    utf8(`NIT ${payload.empresa.nit}\n`),
    utf8(`${payload.empresa.direccion}\n`),
    utf8(`${payload.empresa.regimen}\n`),
    utf8('\n'),
    escText2x(),
    utf8('*** REIMPRESION ***\n'),
    escTextReset(),
    utf8('\n'),
    utf8(`Motivo: ${payload.motivo}\n`),
    utf8(`Folio original: ${payload.folioOriginal}\n`),
    utf8('\n'),
  ];
  let body: Buffer;
  switch (payload.originalTipo) {
    case 'entrada':
      body = buildEntradaBody(payload.payload);
      break;
    case 'salida':
      body = buildSalidaBody(payload.payload);
      break;
    case 'salida-mensualidad':
      body = buildSalidaMensualidadBody(payload.payload);
      break;
  }
  return concat([...header, body]);
}

function buildReciboPagoBody(payload: ReciboPagoPayload): Buffer {
  // F8.1 (HU-F8.1 — PagoModal) — Recibo de pago. Carries the SAME 19
  // CU-15S conceptual fields PLUS two additions:
  //   - `numero_recibo` — backend F1.10 assigns
  //     `sucursal-YYYYMMDD-NNNNNN` (DEC-SUC-28).
  //   - `medio_pago` — typed literal `efectivo` | `datafono`.
  //
  // Layout (mirrors `buildSalidaBody` field-by-field with two swaps):
  //   - Sello slot shows `*** RECIBO DE PAGO ***` (NOT `*** SALIDA ***`).
  //   - Header still uses `payload.sucursal.encabezado` (DEC-SUC-28).
  //   - The `Medio de pago:` line uses the typed `payload.medio_pago`.
  //
  // DEC-SUC-27 verbatim: "CU-15S print fires AFTER pago, then recibo de
  // pago." Caller order is `<SalidaPanel>::handleOpenPago` →
  // `useRegistrarPago.trigger` → `bridge.imprimir('salida', ...)` →
  // `bridge.imprimir('recibo_pago', ...)`. The recibo MUST never fire
  // before the CU-15S tiquete.
  const lines: Buffer[] = [
    escCenter(),
    escBoldOn(),
    utf8(`${payload.sucursal.encabezado}\n`),                 // 1: Encabezado
    escBoldOff(),
    utf8(`${payload.empresa.nombre}\n`),                      // 2: Empresa
    utf8(`${payload.empresa.direccion}\n`),                   // 3: Dirección
    utf8(`NIT ${payload.empresa.nit}\n`),                     // 4: NIT
    utf8(`${payload.empresa.regimen}\n`),                     // 5: Régimen
    utf8(`Operario: ${payload.operario}\n`),                  // 6: Operario
    utf8('\n'),
    escText2x(),
    utf8('*** RECIBO DE PAGO ***\n'),                         // 7: Sello (recibo)
    escTextReset(),
    utf8('\n'),
    utf8(`Numero de recibo: ${payload.numero_recibo}\n`),     // F8.1 addition
    utf8(`Folio: ${payload.folio}\n`),                        // 8: Folio
    utf8(`Tarifa: ${formatCOP(payload.tarifaAplicada)}/hora\n`), // 9: Tarifa
    utf8(`Fecha: ${formatFecha(payload.fechaEntrada)}\n`),    // 10: Fecha
    utf8(`Hora entrada: ${formatHora(payload.fechaEntrada)}\n`), // 11: Hora entrada
    utf8(`Hora salida: ${formatHora(payload.fechaSalida)}\n`),  // 12: Hora salida
    utf8(`Tiempo: ${payload.tiempoTotal}\n`),                 // 13: Tiempo total
    utf8('\n'),
    utf8(`Subtotal: ${formatCOP(payload.subtotal)}\n`),       // 14: Subtotal
    utf8(`IVA: ${formatCOP(payload.iva)}\n`),                 // 15: IVA
    escBoldOn(),
    utf8(`TOTAL: ${formatCOP(payload.total)}\n`),             // 16: TOTAL
    escBoldOff(),
    utf8(`Medio de pago: ${payload.medio_pago}\n`),           // 17: Medio (typed)
    utf8(`Placa: ${payload.placa}\n`),                        // 18: Placa
    utf8(`Horario: ${payload.horarioAtencion}\n`),            // 19a: Horario atención
  ];
  if (payload.polizaRC) {
    lines.push(utf8(`Poliza RC: ${payload.polizaRC}\n`));     // 19b: Póliza RC
  }
  lines.push(utf8(`Resolucion FE: ${payload.resolucionFE}\n`));// 19c: Resolución FE
  if (payload.observaciones) {
    lines.push(utf8(`Observaciones: ${payload.observaciones}\n`)); // 19d: Observaciones
  }
  // F7.3 — DEC-SUC-26 QR + logo markers (mirror CU-15S precedent).
  const logoText = payload.logoDataUrl === ''
    ? LOGO_PLACEHOLDER_GLYPH
    : 'OK';
  lines.push(utf8(`;QR:${payload.qrDataUrl}\n`));
  lines.push(utf8(`;LOGO:${logoText}\n`));
  lines.push(utf8('\n'));
  lines.push(utf8('Gracias por su pago.\n'));
  return concat(lines);
}

// ──────────────────────────────────────────────────────────────────────────
// Public per-tipo builders (exported for tests)
// ──────────────────────────────────────────────────────────────────────────

export function buildEntradaBuffer(payload: EntradaPayload): Buffer {
  return concat([
    escInit(),
    buildEntradaBody(payload),
    cutPartial(),
    lf(),
  ]);
}

export function buildSalidaBuffer(payload: SalidaPayload): Buffer {
  return concat([
    escInit(),
    buildSalidaBody(payload),
    cutPartial(),
    lf(),
  ]);
}

export function buildSalidaMensualidadBuffer(payload: SalidaMensualidadPayload): Buffer {
  return concat([
    escInit(),
    buildSalidaMensualidadBody(payload),
    cutPartial(),
    lf(),
  ]);
}

export function buildReimpresionBuffer(payload: ReimpresionPayload): Buffer {
  return concat([
    escInit(),
    buildReimpresionBody(payload),
    cutPartial(),
    lf(),
  ]);
}

export function buildReciboPagoBuffer(payload: ReciboPagoPayload): Buffer {
  return concat([
    escInit(),
    buildReciboPagoBody(payload),
    cutPartial(),
    lf(),
  ]);
}

// ──────────────────────────────────────────────────────────────────────────
// Top-level dispatcher
// ──────────────────────────────────────────────────────────────────────────

/**
 * Validate `tipo` and `payload`, then dispatch to the matching
 * `build*Buffer()` function. Throws:
 *   - `EscposInvalidTipoError` if `tipo` is not in the 5-allowed union.
 *   - `EscposPayloadMissingFieldError` if Zod parse fails.
 *
 * @param tipo One of `TiqueteTipo`.
 * @param payload Unknown — validated against the matching Zod schema.
 * @returns A `Buffer` containing the full ESC/POS byte stream.
 */
export function build(tipo: TiqueteTipo, payload: unknown): Buffer {
  if (!isTiqueteTipo(tipo)) {
    throw new EscposInvalidTipoError(String(tipo));
  }

  const issues = validatePayload(tipo, payload);
  if (issues !== null) {
    throw new EscposPayloadMissingFieldError(issues);
  }

  // Cast is safe: validatePayload returned null (no issues) AND the schema
  // type matches the tipo. We re-narrow explicitly to keep `tsc --strict`
  // happy without `any`.
  switch (tipo) {
    case 'entrada': {
      const p = entradaPayloadSchema.parse(payload) as EntradaPayload;
      return buildEntradaBuffer(p);
    }
    case 'salida': {
      const p = salidaPayloadSchema.parse(payload) as SalidaPayload;
      return buildSalidaBuffer(p);
    }
    case 'salida-mensualidad': {
      const p = salidaMensualidadPayloadSchema.parse(payload) as SalidaMensualidadPayload;
      return buildSalidaMensualidadBuffer(p);
    }
    case 'reimpresion': {
      const p = reimpresionPayloadSchema.parse(payload) as ReimpresionPayload;
      return buildReimpresionBuffer(p);
    }
    case 'recibo_pago': {
      const p = reciboPagoPayloadSchema.parse(payload) as ReciboPagoPayload;
      return buildReciboPagoBuffer(p);
    }
    default: {
      // Exhaustiveness — should be unreachable because isTiqueteTipo
      // narrows above. Defensive throw to satisfy `noImplicitReturns`.
      throw new EscposInvalidTipoError(String(tipo));
    }
  }
}

/**
 * Narrow a runtime string to the 5-allowed union. Returns true if the
 * input is one of `'entrada' | 'salida' | 'salida-mensualidad' | 'reimpresion' | 'recibo_pago'`.
 */
export function isTiqueteTipo(value: unknown): value is TiqueteTipo {
  return (
    typeof value === 'string' &&
    (TIQUETE_TIPOS as readonly string[]).includes(value)
  );
}

/**
 * Run the matching Zod schema against `payload` for `tipo`. Returns
 * `null` if validation passes, otherwise the array of Zod issues.
 *
 * Exposed for unit testing and for callers that want to surface
 * field-level errors before calling `build()`.
 */
export function validatePayload(
  tipo: TiqueteTipo,
  payload: unknown,
): z.ZodIssue[] | null {
  switch (tipo) {
    case 'entrada':
      return runSafeParse(entradaPayloadSchema, payload);
    case 'salida':
      return runSafeParse(salidaPayloadSchema, payload);
    case 'salida-mensualidad':
      return runSafeParse(salidaMensualidadPayloadSchema, payload);
    case 'reimpresion':
      return runSafeParse(reimpresionPayloadSchema, payload);
    case 'recibo_pago':
      return runSafeParse(reciboPagoPayloadSchema, payload);
    default:
      return null;
  }
}

function runSafeParse(schema: z.ZodType<unknown>, payload: unknown): z.ZodIssue[] | null {
  const result = schema.safeParse(payload);
  if (result.success) return null;
  return result.error.issues;
}