/**
 * `escposBuilder.ts` — pure renderer-side ESC/POS byte composition.
 *
 * HU-F5.2 (Fase 5 — base de impresión) / DEC-SUC-08.
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
 * Purity contract:
 *   - NO DOM, NO `window`, NO `document`, NO `navigator`.
 *   - NO network, NO filesystem, NO USB, NO IPC.
 *   - NO electron / escpos-usb / node:* imports (verified by `grep -E
 *     "from '(electron|escpos-usb|node:)'"` — see `tasks.md` §4.4).
 *   - All timestamps are caller-supplied (no `new Date()`).
 *
 * Error surface (named subclasses for `instanceof` checks):
 *   - `EscposInvalidTipoError` — `tipo` is not in the 4-allowed union.
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
  formatCOP,
  type EntradaPayload,
  type SalidaPayload,
  type SalidaMensualidadPayload,
  type ReimpresionPayload,
  type TiqueteTipo,
} from './escposTemplates';

// ──────────────────────────────────────────────────────────────────────────
// Error classes
// ──────────────────────────────────────────────────────────────────────────

/**
 * Thrown by `build()` when the `tipo` argument is not in the 4-allowed
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

/** RFC 3339 (es-CO short): "dd/MM/yyyy HH:mm". */
function formatFechaCorta(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${dd}/${mm}/${yyyy} ${hh}:${min}`;
}

function buildEntradaBody(payload: EntradaPayload): Buffer {
  const lines: Buffer[] = [
    escCenter(),
    escBoldOn(),
    utf8('PARKINGOS\n'),
    escBoldOff(),
    utf8(`${payload.empresa.nombre}\n`),
    utf8(`NIT ${payload.empresa.nit}\n`),
    utf8(`${payload.empresa.direccion}\n`),
    utf8(`${payload.empresa.regimen}\n`),
    utf8('\n'),
    escText2x(),
    utf8('*** ENTRADA ***\n'),
    escTextReset(),
    utf8('\n'),
    utf8(`Folio: ${payload.folio}\n`),
    utf8(`Placa: ${payload.placa}\n`),
    utf8(`Fecha: ${formatFechaCorta(payload.fechaEntrada)}\n`),
    utf8(`Operario: ${payload.operario}\n`),
    utf8(`Tarifa: ${formatCOP(payload.tarifaAplicada)}/hora\n`),
    utf8(`Horario: ${payload.horarioAtencion}\n`),
  ];
  if (payload.polizaRC) lines.push(utf8(`Poliza RC: ${payload.polizaRC}\n`));
  lines.push(utf8('\n'));
  lines.push(utf8('Conserve este tiquete para la salida.\n'));
  return concat(lines);
}

function buildSalidaBody(payload: SalidaPayload): Buffer {
  const lines: Buffer[] = [
    escCenter(),
    escBoldOn(),
    utf8('PARKINGOS\n'),
    escBoldOff(),
    utf8(`${payload.empresa.nombre}\n`),
    utf8(`NIT ${payload.empresa.nit}\n`),
    utf8(`${payload.empresa.direccion}\n`),
    utf8(`${payload.empresa.regimen}\n`),
    utf8('\n'),
    escText2x(),
    utf8('*** SALIDA ***\n'),
    escTextReset(),
    utf8('\n'),
    utf8(`Folio: ${payload.folio}\n`),
    utf8(`Placa: ${payload.placa}\n`),
    utf8(`Entrada: ${formatFechaCorta(payload.fechaEntrada)}\n`),
    utf8(`Salida:  ${formatFechaCorta(payload.fechaSalida)}\n`),
    utf8(`Tiempo: ${payload.tiempoTotal}\n`),
    utf8('\n'),
    utf8(`Subtotal: ${formatCOP(payload.subtotal)}\n`),
    utf8(`IVA: ${formatCOP(payload.iva)}\n`),
    escBoldOn(),
    utf8(`TOTAL: ${formatCOP(payload.total)}\n`),
    escBoldOff(),
    utf8(`Medio de pago: ${payload.medioPago}\n`),
    utf8(`Resolucion FE: ${payload.resolucionFE}\n`),
  ];
  if (payload.polizaRC) lines.push(utf8(`Poliza RC: ${payload.polizaRC}\n`));
  lines.push(utf8('\n'));
  lines.push(utf8('Gracias por su visita.\n'));
  return concat(lines);
}

function buildSalidaMensualidadBody(payload: SalidaMensualidadPayload): Buffer {
  const lines: Buffer[] = [
    escCenter(),
    escBoldOn(),
    utf8('PARKINGOS\n'),
    escBoldOff(),
    utf8(`${payload.empresa.nombre}\n`),
    utf8(`NIT ${payload.empresa.nit}\n`),
    utf8(`${payload.empresa.direccion}\n`),
    utf8(`${payload.empresa.regimen}\n`),
    utf8('\n'),
    escText2x(),
    utf8('*** PAGO CON MENSUALIDAD ***\n'),
    escTextReset(),
    utf8('\n'),
    utf8(`Folio: ${payload.folio}\n`),
    utf8(`Placa: ${payload.placa}\n`),
    utf8(`Entrada: ${formatFechaCorta(payload.fechaEntrada)}\n`),
    utf8(`Salida:  ${formatFechaCorta(payload.fechaSalida)}\n`),
    utf8(`Operario: ${payload.operario}\n`),
    utf8(`Horario: ${payload.horarioAtencion}\n`),
  ];
  if (payload.polizaRC) lines.push(utf8(`Poliza RC: ${payload.polizaRC}\n`));
  lines.push(utf8('\n'));
  lines.push(utf8('Conserve este tiquete como soporte.\n'));
  return concat(lines);
}

function buildReimpresionBody(payload: ReimpresionPayload): Buffer {
  const header: Buffer[] = [
    escCenter(),
    escBoldOn(),
    utf8('PARKINGOS\n'),
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

// ──────────────────────────────────────────────────────────────────────────
// Top-level dispatcher
// ──────────────────────────────────────────────────────────────────────────

/**
 * Validate `tipo` and `payload`, then dispatch to the matching
 * `build*Buffer()` function. Throws:
 *   - `EscposInvalidTipoError` if `tipo` is not in the 4-allowed union.
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
    default: {
      // Exhaustiveness — should be unreachable because isTiqueteTipo
      // narrows above. Defensive throw to satisfy `noImplicitReturns`.
      throw new EscposInvalidTipoError(String(tipo));
    }
  }
}

/**
 * Narrow a runtime string to the 4-allowed union. Returns true if the
 * input is one of `'entrada' | 'salida' | 'salida-mensualidad' | 'reimpresion'`.
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
    default:
      return null;
  }
}

function runSafeParse(schema: z.ZodType<unknown>, payload: unknown): z.ZodIssue[] | null {
  const result = schema.safeParse(payload);
  if (result.success) return null;
  return result.error.issues;
}