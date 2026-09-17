/**
 * `escposTemplates.ts` — typed payload schemas for the 4 tiquete tipos.
 *
 * HU-F5.2 (Fase 5 — base de impresión) / DEC-SUC-08.
 *
 * Responsibilities:
 *   1. Declare the 4 typed payload interfaces (`EntradaPayload`,
 *      `SalidaPayload`, `SalidaMensualidadPayload`, `ReimpresionPayload`).
 *   2. Ship matching Zod schemas so callers get validation errors at the
 *      build boundary, not as silent garbage bytes.
 *   3. Provide the union `TiqueteTipo` and `TiquetePayload` discriminated
 *      union that `escposBuilder.ts` uses to dispatch.
 *   4. Inline `formatCOP` helper (DEC-SUC-07 — `Intl.NumberFormat('es-CO',
 *      { style: 'currency', currency: 'COP', minimumFractionDigits: 0 })`).
 *
 * SYNCH NOTE — `formatCOP` inline copy:
 *   This is a copy of the rule from `apps/electron-sucursal/src/features/caja/lib/format.ts`
 *   (F3.3 — T1). F2.x is committed to ship `src/lib/format/formatCOP.ts` as
 *   a shared module. When that ships, replace the inline export below with
 *   `export { formatCOP } from '@/lib/format/formatCOP'` (or the agreed path).
 *   Per AGENTS.md rule 6, F5.2 is FORBIDDEN from blocking on F2.x — we
 *   accept the small inline copy + TODO header. See `tasks.md` §2.2.
 *
 * Purity contract:
 *   - This module has NO I/O, NO DOM access, NO `window` reference.
 *   - All timestamps (fechaEntrada, fechaSalida) are caller-supplied ISO
 *     strings (no implicit `new Date()`).
 */

import { z } from 'zod';

// ──────────────────────────────────────────────────────────────────────────
// formatCOP — inline copy pending F2.x
// ──────────────────────────────────────────────────────────────────────────

/**
 * `formatCOP(value)` — Intl.NumberFormat es-CO moneda colombiana sin
 * decimales (DEC-SUC-07). Backend persiste NUMERIC(18,4) per
 * `modelo_datos_er.mmd`; el tiquete kiosko muestra 0 decimales.
 *
 * Ejemplo: `formatCOP(100000)` → `"$ 100.000"`.
 *
 * TODO SYNCH WITH F2.x — when `src/lib/format/formatCOP.ts` ships, switch
 * this export to a re-export from that module and remove the inline copy.
 */
const copFormatter = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export function formatCOP(value: number): string {
  return copFormatter.format(value);
}

// ──────────────────────────────────────────────────────────────────────────
// Empresa / common sub-schemas
// ──────────────────────────────────────────────────────────────────────────

/** Empresa que emite el tiquete (subset of `prod.empresa` per ER). */
const empresaSchema = z.object({
  nombre: z.string().min(1),
  nit: z.string().min(1),
  direccion: z.string().min(1),
  regimen: z.string().min(1),
});

export type Empresa = z.infer<typeof empresaSchema>;

// ──────────────────────────────────────────────────────────────────────────
// Placa regex (DRY with src/lib/validation/placa.ts)
// ──────────────────────────────────────────────────────────────────────────

/** Auto — `ABC123`. */
const REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/;

/** Moto — `ABC12D` (la letra final acepta [A-Z]). */
const REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/;

const placaSchema = z
  .string()
  .trim()
  .transform((s) => s.toUpperCase().replace(/\s+/g, ''))
  .refine((s) => REGEX_AUTO.test(s) || REGEX_MOTO.test(s), {
    message: 'placa_formato_invalido',
  });

// ──────────────────────────────────────────────────────────────────────────
// Tipo literal + payload union
// ──────────────────────────────────────────────────────────────────────────

/** The 4 tiquete tipos supported by F5.2. */
export type TiqueteTipo = 'entrada' | 'salida' | 'salida-mensualidad' | 'reimpresion';

export const TIQUETE_TIPOS: readonly TiqueteTipo[] = [
  'entrada',
  'salida',
  'salida-mensualidad',
  'reimpresion',
] as const;

// ──────────────────────────────────────────────────────────────────────────
// Entrada payload (CU-15E)
// ──────────────────────────────────────────────────────────────────────────

export const entradaPayloadSchema = z.object({
  placa: placaSchema,
  fechaEntrada: z.string().datetime({ offset: true }),
  qrDataUrl: z.string().optional(),
  logoDataUrl: z.string().optional(),
  empresa: empresaSchema,
  operario: z.string().min(1),
  tarifaAplicada: z.number().nonnegative(),
  horarioAtencion: z.string().min(1),
  polizaRC: z.string().optional(),
  folio: z.string().uuid(),
  observaciones: z.string().optional(),
});

export type EntradaPayload = z.infer<typeof entradaPayloadSchema>;

// ──────────────────────────────────────────────────────────────────────────
// Salida payload (CU-15S)
// ──────────────────────────────────────────────────────────────────────────

export const salidaPayloadSchema = entradaPayloadSchema.extend({
  fechaSalida: z.string().datetime({ offset: true }),
  tiempoTotal: z.string().min(1),
  subtotal: z.number().nonnegative(),
  iva: z.number().nonnegative(),
  total: z.number().nonnegative(),
  medioPago: z.string().min(1),
  resolucionFE: z.string().min(1),
});

export type SalidaPayload = z.infer<typeof salidaPayloadSchema>;

// ──────────────────────────────────────────────────────────────────────────
// Salida-mensualidad payload (CU-15SM)
// ──────────────────────────────────────────────────────────────────────────

export const salidaMensualidadPayloadSchema = z.object({
  placa: placaSchema,
  fechaEntrada: z.string().datetime({ offset: true }),
  fechaSalida: z.string().datetime({ offset: true }),
  qrDataUrl: z.string().optional(),
  logoDataUrl: z.string().optional(),
  empresa: empresaSchema,
  operario: z.string().min(1),
  horarioAtencion: z.string().min(1),
  polizaRC: z.string().optional(),
  folio: z.string().uuid(),
  observaciones: z.string().optional(),
  // Discriminator — used by the renderer to swap to "PAGO CON MENSUALIDAD"
  // branding in the sello slot. NOT a money field (DEC-SUC-27 — salida
  // mensualidad NO emite subtotal/iva/total/medioPago).
  esMensualidad: z.literal(true),
});

export type SalidaMensualidadPayload = z.infer<typeof salidaMensualidadPayloadSchema>;

// ──────────────────────────────────────────────────────────────────────────
// Reimpresion payload — discriminated union on `originalTipo`
// ──────────────────────────────────────────────────────────────────────────

const reimpresionBaseSchema = z.object({
  motivo: z.string().min(1),
  qrDataUrl: z.string().optional(),
  logoDataUrl: z.string().optional(),
  empresa: empresaSchema,
  folioOriginal: z.string().uuid(),
});

export const reimpresionEntradaSchema = reimpresionBaseSchema.extend({
  originalTipo: z.literal('entrada'),
  payload: entradaPayloadSchema,
});

export const reimpresionSalidaSchema = reimpresionBaseSchema.extend({
  originalTipo: z.literal('salida'),
  payload: salidaPayloadSchema,
});

export const reimpresionSalidaMensualidadSchema = reimpresionBaseSchema.extend({
  originalTipo: z.literal('salida-mensualidad'),
  payload: salidaMensualidadPayloadSchema,
});

export const reimpresionPayloadSchema = z.discriminatedUnion('originalTipo', [
  reimpresionEntradaSchema,
  reimpresionSalidaSchema,
  reimpresionSalidaMensualidadSchema,
]);

export type ReimpresionPayload = z.infer<typeof reimpresionPayloadSchema>;

// ──────────────────────────────────────────────────────────────────────────
// Per-tipo schema map (consumed by escposBuilder.validatePayload)
// ──────────────────────────────────────────────────────────────────────────

export const payloadSchemaByTipo: {
  readonly [K in TiqueteTipo]: z.ZodType<unknown>;
} = {
  entrada: entradaPayloadSchema,
  salida: salidaPayloadSchema,
  'salida-mensualidad': salidaMensualidadPayloadSchema,
  reimpresion: reimpresionPayloadSchema,
};