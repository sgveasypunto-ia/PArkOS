/**
 * `escposTemplates.ts` — typed payload schemas for the 4 tiquete tipos.
 *
 * HU-F5.2 (Fase 5 — base de impresión) / DEC-SUC-08.
 * HU-F6.2 (Fase 6 — tiquete de entrada CU-15E) / DEC-SUC-26.
 *
 * Responsibilities:
 *   1. Declare the 5 typed payload interfaces (`EntradaPayload`,
 *      `SalidaPayload`, `SalidaMensualidadPayload`, `ReimpresionPayload`,
 *      `ReciboPagoPayload`).
 *   2. Ship matching Zod schemas so callers get validation errors at the
 *      build boundary, not as silent garbage bytes.
 *   3. Provide the union `TiqueteTipo` and `TiquetePayload` discriminated
 *      union that `escposBuilder.ts` uses to dispatch.
 *   4. Inline `formatCOP` helper (DEC-SUC-07 — `Intl.NumberFormat('es-CO',
 *      { style: 'currency', currency: 'COP', minimumFractionDigits: 0 })`).
 *   5. F6.2 — declare the 17-key `TiqueteEntradaCampos` interface
 *      (Spanish ordinals, tsc-exhaustive) plus the
 *      `TiqueteEntradaPayload` mapped type used to enforce 17-key
 *      exhaustiveness at compile time. Ship `buildEntradaPayload()`
 *      factory that assembles an `EntradaPayload` from the 8 caller
 *      inputs and sets `esMensualidad` based on
 *      `ingreso.uuid_subscripcion_cliente IS NOT NULL`.
 *   6. F8.1 (HU-F8.1) — `ReciboPagoPayload` extends `SalidaPayload` with
 *      the typed `medio_pago` discriminator + `numero_recibo` line for
 *      the post-pago print emitted AFTER the CU-15S tiquete de salida
 *      (DEC-SUC-27 + DEC-SUC-28).
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
 *   - F6.2 factory `buildEntradaPayload()` accepts a typed
 *     `IngresoForPayload` view of the ingreso row — it does NOT query
 *     the ER. Caller is responsible for fetching the row (F6.1 wiring).
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

/**
 * F6.2 — date only (es-CO short): "dd/MM/yyyy" (for the decimo
 * conceptual field — CU-15E field 10, CU-15S field 10, CU-15SM field 9).
 *
 * Pure helper — caller must pass an ISO 8601 string (no implicit
 * `new Date()` inside the helper; we go through `new Date(iso)`
 * once here and split). Exported so byte-level tests can compose
 * the expected payload deterministically.
 */
export function formatFecha(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}/${mm}/${d.getFullYear()}`;
}

/**
 * F6.2 — time only: "HH:mm" (es-CO short, for the onceavo conceptual
 * field — CU-15E field 11, CU-15S field 11/12, CU-15SM field 10/11).
 *
 * Pure helper — same caveat as `formatFecha`.
 */
export function formatHora(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${min}`;
}

/**
 * F6.2 + F7.3 — combined date+time (es-CO short): "dd/MM/yyyy HH:mm".
 * Used for CU-15E campo vacio (legacy) when no separate date/time split
 * is desired. CU-15S + CU-15SM use `formatFecha` + `formatHora`
 * separately so the spec's field-by-field split is preserved.
 */
export function formatFechaCorta(iso: string): string {
  return `${formatFecha(iso)} ${formatHora(iso)}`;
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

/**
 * F7.3 (DEC-SUC-28) — `sucursal` payload shape. The `encabezado` field
 * is the dynamic branch header that REPLACES the F5.2 "PARKINGOS"
 * constant across ALL THREE bodies (`entrada`, `salida`,
 * `salida-mensualidad`) plus the `reimpresion` envelope. Required on
 * all payloads — Zod rejects with `EscposPayloadMissingFieldError`
 * when missing, matching the `plan.md` invariant that each tiquete
 * prints the sucursal of issue.
 */
const sucursalSchema = z.object({
  encabezado: z.string().min(1),
});

export type Sucursal = z.infer<typeof sucursalSchema>;

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

/**
 * The 5 tiquete tipos supported by the print dispatcher. F8.1 (HU-F8.1
 * — PagoModal) adds `recibo_pago` — the post-pago print emitted AFTER
 * the CU-15S tiquete de salida per DEC-SUC-27 verbatim ("CU-15S print
 * fires AFTER pago, then recibo de pago").
 *
 * F10.1 (HU-F10.1 — Arqueo Parcial / REQ-OPS-155 / DA-5) adds the 6th
 * literal `'arqueo'`. The F8.3 REQ-OPS-175 drift anchor precedent
 * forbids alternate spellings — only `'arqueo'` is allowed; NOT
 * `'arqueo_parcial'`, NOT `'ticket_arqueo'`.
 */
export type TiqueteTipo =
  | 'entrada'
  | 'salida'
  | 'salida-mensualidad'
  | 'reimpresion'
  | 'recibo_pago'
  | 'arqueo';

export const TIQUETE_TIPOS: readonly TiqueteTipo[] = [
  'entrada',
  'salida',
  'salida-mensualidad',
  'reimpresion',
  'recibo_pago',
  'arqueo',
] as const;

// ──────────────────────────────────────────────────────────────────────────
// Entrada payload (CU-15E) — F6.2 tightens qr/logo to required
// ──────────────────────────────────────────────────────────────────────────

/**
 * F6.2 (DEC-SUC-26) tightens `qrDataUrl` and `logoDataUrl` to REQUIRED
 * strings. F5.2 shipped them as `.optional()` — that allowed callers
 * to omit QR + logo entirely. F6.2 makes both keys mandatory because
 * the 17-field strict `TiqueteEntradaCampos` shape requires their
 * presence (empty string is the legitimate "logo missing" value —
 * the builder renders a placeholder glyph `▢` when `logoDataUrl === ''`
 * per `design.md` §"Decision: Render-time guard for missing
 * `documentos` row").
 *
 * F7.3 (DEC-SUC-28) tightens `sucursal.encabezado` to REQUIRED across
 * ALL THREE tiquete payloads (`entrada`, `salida`,
 * `salida-mensualidad`) — see the spec drift reconciliation table at
 * `openspec/changes/fase-7-3-tiquetes-salida/specs/operacion.md`. The
 * F5.2 "PARKINGOS" header constant is replaced by the dynamic branch
 * header.
 *
 * The QR rasterizer is the caller's responsibility (F5.2 R4 purity).
 * The builder accepts the resulting `data:image/png;base64,...`
 * string verbatim. ABIERTO-01 default content:
 * `parkos://ingreso/<ingreso.uuid>?placa=<ingreso.placa>`.
 *
 * `esMensualidad` is an OPTIONAL control flag surfaced by
 * `buildEntradaPayload()` when `ingreso.uuid_subscripcion_cliente
 * IS NOT NULL`. It is NOT one of the 17 conceptual fields; it is a
 * side-channel so the builder can emit the `MENSUALIDAD` tag under
 * the sello without exposing a third party column on the conceptual
 * 17-key shape (DEC-SUC-21 — `tipo_entrada` MUST NOT be persisted).
 */
export const entradaPayloadSchema = z.object({
  placa: placaSchema,
  fechaEntrada: z.string().datetime({ offset: true }),
  qrDataUrl: z.string(),
  logoDataUrl: z.string(),
  empresa: empresaSchema,
  operario: z.string().min(1),
  tarifaAplicada: z.number().nonnegative(),
  horarioAtencion: z.string().min(1),
  polizaRC: z.string().optional(),
  folio: z.string().uuid(),
  observaciones: z.string().optional(),
  esMensualidad: z.boolean().optional(),
  // F7.3 (DEC-SUC-28) — branch header replaces "PARKINGOS" constant
  sucursal: sucursalSchema,
});

export type EntradaPayload = z.infer<typeof entradaPayloadSchema>;

// ──────────────────────────────────────────────────────────────────────────
// F6.2 — TiqueteEntradaCampos (17-key exhaustive shape)
// ──────────────────────────────────────────────────────────────────────────

/**
 * `TiqueteEntradaCampos` — the 17 conceptual fields emitted on the
 * tiquete de entrada per `plan.md` lines 1606-1653 (HU-F6.2 contract).
 *
 * Spanish ordinal names (`primero`..`quinceavo`) keep tsc error messages
 * unambiguous on removal — e.g., `Property 'tercero' is missing in
 * type 'TiqueteEntradaPayload'`. Names are stable and never drift; the
 * literal CU-15E field LABELS live in `plan.md` (canonical).
 *
 * Conceptual mapping (NOT all data fields — some are derived constants
 * emitted by the builder):
 *   primero        → Encabezado (payload.sucursal.encabezado)
 *   segundo        → Nombre de la empresa    → payload.empresa.nombre
 *   tercero        → Dirección                → payload.empresa.direccion
 *   cuarto         → NIT                      → payload.empresa.nit
 *   quinto         → Régimen                  → payload.empresa.regimen
 *   sexto          → Operario                 → payload.operario
 *   septimo        → "TIQUETE DE ENTRADA" sello (constant)
 *   octavo         → Folio                    → payload.folio
 *   noveno         → Tarifa aplicada          → payload.tarifaAplicada
 *   decimo         → Fecha operación          → payload.fechaEntrada (date)
 *   onceavo        → Hora entrada             → payload.fechaEntrada (time)
 *   doceavo        → Placa                    → payload.placa
 *   treceavo       → Horario atención         → payload.horarioAtencion
 *   catorceavo     → Póliza RC                → payload.polizaRC (optional)
 *   quinceavo      → Observaciones            → payload.observaciones (optional)
 *   qrDataUrl      → QR (DEC-SUC-26)          → payload.qrDataUrl
 *   logoDataUrl    → Logo (DEC-SUC-26)        → payload.logoDataUrl
 *
 * The mapped type `TiqueteEntradaPayload` derives the 17-key
 * exhaustiveness check at compile time so removing or renaming any
 * key fails `tsc --noEmit` (per spec scenario "Removing a key breaks
 * the build"). It is the source of truth for the 17-key COUNT — no
 * other file in the codebase may declare a competing key set.
 */
export interface TiqueteEntradaCampos {
  readonly primero: string;
  readonly segundo: string;
  readonly tercero: string;
  readonly cuarto: string;
  readonly quinto: string;
  readonly sexto: string;
  readonly septimo: string;
  readonly octavo: string;
  readonly noveno: string;
  readonly decimo: string;
  readonly onceavo: string;
  readonly doceavo: string;
  readonly treceavo: string;
  readonly catorceavo: string;
  readonly quinceavo: string;
  readonly qrDataUrl: string;
  readonly logoDataUrl: string;
}

/**
 * `TiqueteEntradaPayload` — readonly mapped type over the 17-key
 * `TiqueteEntradaCampos`. The mapped type form makes the 17-key count
 * the canonical source: if you remove a key from
 * `TiqueteEntradaCampos`, this type narrows automatically and any
 * function declaring it as a return type fails to compile.
 *
 * Distinct from the underlying data type `EntradaPayload` (F5.2)
 * which carries the 11+1 data fields. The 17-key shape is the
 * conceptual layout view; the data type is the storage view.
 */
export type TiqueteEntradaPayload = {
  readonly [K in keyof TiqueteEntradaCampos]: TiqueteEntradaCampos[K];
};

// ──────────────────────────────────────────────────────────────────────────
// F6.2 — Inputs for buildEntradaPayload factory
// ──────────────────────────────────────────────────────────────────────────

/**
 * Minimal view of `prod.ingreso` row needed by `buildEntradaPayload()`.
 * Caller (F6.1) hydrates this from the backend response. The factory
 * does NOT touch the ER.
 */
export interface IngresoForPayload {
  readonly uuid: string;
  readonly placa: string;
  readonly fecha_ingreso: string;
  /** DEC-SUC-21 — `tipo_entrada` is DERIVED, NOT persisted. */
  readonly uuid_subscripcion_cliente: string | null;
}

/** Minimal view of `prod.sucursal` row. */
export interface SucursalForPayload {
  readonly horario_atencion: string;
  /**
   * F7.3 (DEC-SUC-28) — branch header that REPLACES the F5.2
   * "PARKINGOS" constant. Required on every payload that flows
   * through the printer pipeline.
   */
  readonly encabezado: string;
}

/** Minimal view of `prod.tarifas_sucursal` row. */
export interface TarifaForPayload {
  readonly valor_hora_cents: number;
}

/** Document row from `GET /documentos?uuid_sucursal=X&tipo=...`. */
export interface DocumentoForPayload {
  readonly tipo: 'logo' | 'certificado';
  readonly documento_b64: string;
}

/** Inputs for `buildEntradaPayload()`. */
export interface BuildEntradaPayloadInputs {
  readonly ingreso: IngresoForPayload;
  readonly sucursal: SucursalForPayload;
  readonly empresa: Empresa;
  readonly operario: string;
  readonly tipoVehiculo: 'auto' | 'moto';
  readonly tarifa: TarifaForPayload;
  readonly documentos: readonly DocumentoForPayload[];
  /** ISO 8601 datetime — passed through verbatim per F5.2 R4. */
  readonly fechaHora: string;
}

// ──────────────────────────────────────────────────────────────────────────
// F6.2 — buildEntradaPayload factory
// ──────────────────────────────────────────────────────────────────────────

/**
 * `buildEntradaPayload(inputs)` — assemble an `EntradaPayload` (F5.2
 * data type) from the 8 caller-supplied inputs. The factory:
 *
 *   1. Pulls the logo from `documentos` (tolerates absent — empty
 *      string is the documented `documentos` cold-cache sentinel;
 *      the builder renders `▢` when the value is empty per
 *      `design.md` §"Decision: Render-time guard for missing
 *      `documentos` row").
 *   2. Pulls the póliza RC from `documentos` (also tolerates absent —
 *      `polizaRC` remains undefined).
 *   3. Sets `esMensualidad: true` when `ingreso.uuid_subscripcion_cliente
 *      IS NOT NULL` (DEC-SUC-21 — derived, NEVER persisted as a
 *      column on the `ingreso` row).
 *   4. Forwards `fechaHora` as `fechaEntrada` verbatim (ISO 8601 —
 *      the builder formats it to es-CO short via
 *      `Intl.DateTimeFormat('es-CO', {dateStyle: 'short', timeStyle:
 *      'short'})` per F5.2 R4 — no implicit `new Date()`).
 *
 * Purity: the factory is referentially transparent. Same inputs →
 * same payload. No I/O, no `Date.now()`, no `Math.random()`.
 *
 * Throws:
 *   - The function itself does NOT throw — `entradaPayloadSchema.parse`
 *     at the build boundary (`escposBuilder.build`) surfaces any
 *     structural defect with `EscposPayloadMissingFieldError`. This
 *     factory's contract is "produce a structurally valid payload
 *     when given well-typed inputs".
 */
export function buildEntradaPayload(
  inputs: BuildEntradaPayloadInputs,
): EntradaPayload {
  const {
    ingreso,
    sucursal,
    empresa,
    operario,
    tarifa,
    documentos,
    fechaHora,
  } = inputs;

  const logoDoc = documentos.find((d) => d.tipo === 'logo');
  const certDoc = documentos.find((d) => d.tipo === 'certificado');

  return {
    placa: ingreso.placa,
    fechaEntrada: fechaHora,
    qrDataUrl: `data:image/png;base64,${generateQrSentinel(ingreso)}`,
    logoDataUrl: logoDoc?.documento_b64 ?? '',
    empresa,
    operario,
    tarifaAplicada: tarifa.valor_hora_cents,
    horarioAtencion: sucursal.horario_atencion,
    polizaRC: certDoc?.documento_b64,
    folio: ingreso.uuid,
    observaciones: undefined,
    esMensualidad: ingreso.uuid_subscripcion_cliente !== null
      && ingreso.uuid_subscripcion_cliente !== undefined,
    // F7.3 (DEC-SUC-28) — branch header replaces F5.2 "PARKINGOS" constant
    sucursal: { encabezado: sucursal.encabezado },
  };
}

/**
 * Generate the ABIERTO-01 default QR content sentinel
 * (`parkos://ingreso/<uuid>?placa=<placa>`). The actual rasterization
 * is the CALLER's responsibility (F5.2 R4 purity). This helper
 * produces the deterministic string content the rasterizer would
 * encode; the builder embeds the data URL verbatim.
 *
 * The data URL prefix `data:image/png;base64,` is what callers
 * conventionally produce via `qrcode.toDataURL()`; the suffix after
 * the comma is the rasterized PNG base64. F6.2 ships a deterministic
 * sentinel so unit tests can assert byte presence; production callers
 * overwrite this with the real rasterizer output.
 */
function generateQrSentinel(ingreso: IngresoForPayload): string {
  const content = `parkos://ingreso/${ingreso.uuid}?placa=${ingreso.placa}`;
  // Lightweight deterministic stub so byte-level tests can locate
  // the content via `Buffer.indexOf(content)` without importing a
  // QR library. The actual rasterization is out of F6.2 scope
  // (F5.2 R4 purity — caller responsibility).
  return Buffer.from(content, 'utf8').toString('base64');
}

// ──────────────────────────────────────────────────────────────────────────
// Salida payload (CU-15S)
// ──────────────────────────────────────────────────────────────────────────

/**
 * F7.3 (DEC-SUC-28) tightens the F5.2 `salidaPayloadSchema` to require
 * `sucursal.encabezado` (dynamic branch header — replaces the
 * "PARKINGOS" constant). The other 19-field requirements were
 * inherited from `entradaPayloadSchema` (F6.2 — `tarifaAplicada`,
 * `horarioAtencion`, `observaciones`, `qrDataUrl`, `logoDataUrl`,
 * `polizaRC`).
 *
 * Why the spread and not a re-declare: the CU-15S payload is a strict
 * superset of the CU-15E payload — `.extend()` keeps the
 * `TiqueteEntradaCampos` (17-key) shape convergent across both
 * builders and makes the field drift visible at review time
 * (rename a key on `entradaPayloadSchema` and the same key on
 * `salidaPayloadSchema` follows automatically).
 */
export const salidaPayloadSchema = entradaPayloadSchema.extend({
  sucursal: sucursalSchema,
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

/**
 * F7.3 (DEC-SUC-28 + DEC-SUC-26) tightens the F5.2
 * `salidaMensualidadPayloadSchema`:
 *   - `sucursal.encabezado` is REQUIRED (DEC-SUC-28 — dynamic branch
 *     header replaces the F5.2 "PARKINGOS" constant).
 *   - `qrDataUrl` and `logoDataUrl` are REQUIRED (DEC-SUC-26 — same as
 *     F6.2 tightened CU-15E). Empty `logoDataUrl` is the legitimate
 *     "documentos cold-cache" sentinel (renders placeholder `▢`).
 *   - `tiempoTotal` is REQUIRED (was implicit in the F5.2 stub via
 *     combined `Entrada:` + `Salida:` lines; F7.3 splits into
 *     `Fecha:` / `Hora entrada:` / `Hora salida:` / `Tiempo:` per
 *     the 15-field canonical layout in `plan.md:1810`).
 *
 * NO monetary fields (DEC-SUC-23 verbatim — `salidas` has NO `valor`
 * column; the mensualidad fee is settled by the subscription, NOT
 * the exit).
 */
export const salidaMensualidadPayloadSchema = z.object({
  placa: placaSchema,
  fechaEntrada: z.string().datetime({ offset: true }),
  fechaSalida: z.string().datetime({ offset: true }),
  qrDataUrl: z.string(),
  logoDataUrl: z.string(),
  empresa: empresaSchema,
  operario: z.string().min(1),
  horarioAtencion: z.string().min(1),
  polizaRC: z.string().optional(),
  folio: z.string().uuid(),
  observaciones: z.string().optional(),
  // DEC-SUC-28 — dynamic branch header.
  sucursal: sucursalSchema,
  // F7.3 — split duration into explicit field (Fecha + Hora entrada +
  // Hora salida + Tiempo) per the 15-field layout.
  tiempoTotal: z.string().min(1),
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
// Recibo de pago payload (post-pago print) — F8.1 (HU-F8.1)
// ──────────────────────────────────────────────────────────────────────────

/**
 * F8.1 (HU-F8.1 — PagoModal / DEC-SUC-27 + DEC-SUC-28):
 *   - The recibo de pago prints AFTER the CU-15S tiquete de salida
 *     (DEC-SUC-27 verbatim: "CU-15S print fires AFTER pago, then
 *     recibo de pago"). It carries the SAME 19 CU-15S conceptual
 *     fields PLUS two additions:
 *       - `numero_recibo` — backend F1.10 assigns
 *         `sucursal-YYYYMMDD-NNNNNN` (DEC-SUC-28 verbatim).
 *       - `medio_pago` — typed literal `efectivo` | `datafono` that
 *         REPLACES the CU-15S `medioPago: z.string().min(1)`. The
 *         discriminator enforces the strict medio enum at the build
 *         boundary (a `transferencia` medio would be rejected).
 *   - `sucursal.encabezado` is REQUIRED (DEC-SUC-28 — same as CU-15S).
 *   - `qrDataUrl` and `logoDataUrl` are REQUIRED (DEC-SUC-26 — same
 *     as CU-15S tightened by F6.2).
 *
 * The schema extends `salidaPayloadSchema` so the 19-CU-15S field set
 * stays convergent across both builders; the two additions override
 * `medioPago` with the strict literal.
 */
export const reciboPagoPayloadSchema = salidaPayloadSchema.extend({
  numero_recibo: z.string().regex(/^sucursal-\d{8}-\d{6}$/, 'numero_recipo_formato'),
  medio_pago: z.enum(['efectivo', 'datafono']),
});

export type ReciboPagoPayload = z.infer<typeof reciboPagoPayloadSchema>;

// ──────────────────────────────────────────────────────────────────────────
// Arqueo payload (CU-10 arqueo parcial / F10.1) — REQ-OPS-155
// ──────────────────────────────────────────────────────────────────────────

/**
 * F10.1 (HU-F10.1 — Arqueo Parcial / REQ-OPS-155) — `'arqueo'`
 * dispatcher payload. The body emits 12 conceptual lines (see
 * `escposBuilder.buildArqueoBody`). The schema is the wire-shape
 * contract for `bridge.imprimir('arqueo', payload)`.
 *
 * Field semantics:
 *   - `sucursal.encabezado` — dynamic branch header (DEC-SUC-28).
 *   - `uuid_sesion` — full UUID; `uuid_sesion_short` is the
 *     caller-computed last-8-chars shorthand for the printable
 *     buffer (the backend `arqueo` row captures the full UUID in
 *     `log_transaccional` for the audit chain).
 *   - `base_efectivo_cop` — initial cash float per
 *     `sesion.valor_inicial_efectivo` at the moment of the GET
 *     resumen (REQ-OPS-097 §3919 formula).
 *   - `valor_esperado_*` — server-computed expected = base + Σ
 *     `factura_pagos.valor` per medio de pago.
 *   - `diferencia_*` — REPORTADO − ESPERADO, signed.
 *   - `tolerancia_*` — `configuracion_tolerancias.tolerancia_efectivo`
 *     (absolute, never percentage — drift anchor from session
 *     preflight).
 *   - `justificacion` — optional; emitted ONLY when length > 0
 *     (silent omission per spec scenario 3).
 *   - `auditoria_codigo` — either server-assigned `^AUD-\d{8}-\d{6}$`
 *     (F10.1 arqueo parcial canonical format) OR one of the typed
 *     discriminators `'auditoria' | 'cierre_turno' | 'cierre_dia'`
 *     (HU-F10.2 / F10.3 forward hook — DA-F10.2-5 RESOLVED). The
 *     builder emits `Codigo: ${payload.auditoria_codigo}\n` for both
 *     formats; the regex accepts both.
 *   - `fecha` — ISO 8601 datetime; the builder formats it via
 *     `formatFechaCorta` (es-CO short per F6.2).
 */
export const arqueoPayloadSchema = z.object({
  sucursal: sucursalSchema,
  uuid_sesion: z.string().uuid(),
  base_efectivo_cop: z.number().int().nonnegative(),
  valor_esperado_efectivo: z.number().int().nonnegative(),
  valor_esperado_datafono: z.number().int().nonnegative(),
  valor_reportado_efectivo: z.number().int().nonnegative(),
  valor_reportado_datafono: z.number().int().nonnegative(),
  diferencia_efectivo: z.number().int(),
  diferencia_datafono: z.number().int(),
  tolerancia_efectivo: z.number().int().nonnegative(),
  tolerancia_datafono: z.number().int().nonnegative(),
  justificacion: z.string().optional(),
  auditoria_codigo: z.string().regex(
    /^(?:AUD-\d{8}-\d{6}|auditoria|cierre_turno|cierre_dia)$/,
    'auditoria_codigo_formato',
  ),
  fecha: z.string().datetime({ offset: true }),
  uuid_sesion_short: z.string().min(1),
});

export type ArqueoPayload = z.infer<typeof arqueoPayloadSchema>;

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
  recibo_pago: reciboPagoPayloadSchema,
  arqueo: arqueoPayloadSchema,
};