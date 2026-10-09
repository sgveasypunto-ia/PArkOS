/**
 * `escposBuilder.ts` — validation + ESC/POS rendering of the operation tickets.
 *
 * HU-F5.2 (Fase 5 — base de impresión) / DEC-SUC-08.
 *
 * Contract (F5.1 `bridge.imprimir` consumer):
 *   `build(tipo, payload, marca?) → Buffer`
 *
 * Every ticket (entrada, salida, salida-mensualidad, reimpresion, recibo_pago,
 * arqueo) is built as a list of `FacturaLinea` (`tiqueteLineas.ts`) and
 * rendered by the SAME renderer as the invoice and the cierre de turno
 * (`facturaPrint.lineasAEscpos`): 80 mm roll, printable area 576 dots, Font A
 * (48 columns), bold with `ESC E n` (always with its parameter), the easypunto
 * logo raster on top and bottom (text fallback without `marca`), partial cut.
 * No double-size text either (it would halve the 48 columns).
 *
 * Purity contract:
 *   - NO DOM, NO `window`, NO `document`, NO `navigator`.
 *   - NO network, NO filesystem, NO USB, NO IPC.
 *   - All timestamps are caller-supplied (no `new Date()`).
 *
 * Error surface (named subclasses for `instanceof` checks):
 *   - `EscposInvalidTipoError` — `tipo` is not one of the allowed tipos.
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
  arqueoPayloadSchema,
  type EntradaPayload,
  type SalidaPayload,
  type SalidaMensualidadPayload,
  type ReimpresionPayload,
  type ReciboPagoPayload,
  type ArqueoPayload,
  type TiqueteTipo,
} from './escposTemplates';
import { lineasAEscpos, type FacturaLinea } from './facturaPrint';
import type { MarcaRaster } from './marcaTicket';
import {
  construirArqueoParcial,
  construirEntrada,
  construirReimpresion,
  construirRecibo,
  construirSalida,
  construirSalidaMensualidad,
} from './tiqueteLineas';
import { cutPartial, escCenter, escInit, escLeft, escNegrita, lf } from './ticketBase';

export type { TiqueteTipo };

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
// ESC/POS opcode helpers (single definitions live in `ticketBase.ts`)
// ──────────────────────────────────────────────────────────────────────────

export { cutPartial, escCenter, escInit, escLeft, lf };

/** `0x1B 0x45 0x01` — ESC `E` 1 — Bold on (single definition: `escNegrita`). */
export function escBoldOn(): Buffer {
  return escNegrita(true);
}

/** `0x1B 0x45 0x00` — ESC `E` 0 — Bold off (single definition: `escNegrita`). */
export function escBoldOff(): Buffer {
  return escNegrita(false);
}

// ──────────────────────────────────────────────────────────────────────────
// Lines + ESC/POS per tipo
// ──────────────────────────────────────────────────────────────────────────

/**
 * Validate `tipo` + `payload` and return the channel-neutral lines of the
 * ticket (shared by the ESC/POS and the HTML channel). Throws:
 *   - `EscposInvalidTipoError` if `tipo` is not allowed.
 *   - `EscposPayloadMissingFieldError` if Zod parse fails.
 */
export function lineasDeTiquete(tipo: TiqueteTipo, payload: unknown): FacturaLinea[] {
  if (!isTiqueteTipo(tipo)) {
    throw new EscposInvalidTipoError(String(tipo));
  }

  const issues = validatePayload(tipo, payload);
  if (issues !== null) {
    throw new EscposPayloadMissingFieldError(issues);
  }

  // Casts are safe: validatePayload returned null (no issues) AND the schema
  // matches the tipo; re-parsing keeps `tsc --strict` happy without `any`.
  switch (tipo) {
    case 'entrada':
      return construirEntrada(entradaPayloadSchema.parse(payload) as EntradaPayload);
    case 'salida':
      return construirSalida(salidaPayloadSchema.parse(payload) as SalidaPayload);
    case 'salida-mensualidad':
      return construirSalidaMensualidad(
        salidaMensualidadPayloadSchema.parse(payload) as SalidaMensualidadPayload,
      );
    case 'reimpresion':
      return construirReimpresion(reimpresionPayloadSchema.parse(payload) as ReimpresionPayload);
    case 'recibo_pago':
      return construirRecibo(reciboPagoPayloadSchema.parse(payload) as ReciboPagoPayload);
    case 'arqueo':
      return construirArqueoParcial(arqueoPayloadSchema.parse(payload) as ArqueoPayload);
    default:
      // Exhaustiveness — unreachable because isTiqueteTipo narrows above.
      throw new EscposInvalidTipoError(String(tipo));
  }
}

/**
 * Validate and render the full ESC/POS byte stream of a ticket on 80 mm paper.
 * `marca` = raster logo from `marcaParaBridge()`; without it the brand prints
 * as text. Throws like `lineasDeTiquete`.
 */
export function build(tipo: TiqueteTipo, payload: unknown, marca: MarcaRaster | null = null): Buffer {
  return lineasAEscpos(lineasDeTiquete(tipo, payload), marca);
}

// Typed per-tipo renderers (exported for tests and callers that already hold a typed payload).

export function buildEntradaBuffer(payload: EntradaPayload, marca: MarcaRaster | null = null): Buffer {
  return lineasAEscpos(construirEntrada(payload), marca);
}

export function buildSalidaBuffer(payload: SalidaPayload, marca: MarcaRaster | null = null): Buffer {
  return lineasAEscpos(construirSalida(payload), marca);
}

export function buildSalidaMensualidadBuffer(
  payload: SalidaMensualidadPayload,
  marca: MarcaRaster | null = null,
): Buffer {
  return lineasAEscpos(construirSalidaMensualidad(payload), marca);
}

export function buildReimpresionBuffer(
  payload: ReimpresionPayload,
  marca: MarcaRaster | null = null,
): Buffer {
  return lineasAEscpos(construirReimpresion(payload), marca);
}

export function buildReciboPagoBuffer(payload: ReciboPagoPayload, marca: MarcaRaster | null = null): Buffer {
  return lineasAEscpos(construirRecibo(payload), marca);
}

export function buildArqueoBuffer(payload: ArqueoPayload, marca: MarcaRaster | null = null): Buffer {
  return lineasAEscpos(construirArqueoParcial(payload), marca);
}

/**
 * Narrow a runtime string to a `TiqueteTipo`.
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
    case 'arqueo':
      return runSafeParse(arqueoPayloadSchema, payload);
    default:
      return null;
  }
}

function runSafeParse(schema: z.ZodType<unknown>, payload: unknown): z.ZodIssue[] | null {
  const result = schema.safeParse(payload);
  if (result.success) return null;
  return result.error.issues;
}