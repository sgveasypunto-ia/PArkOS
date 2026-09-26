/**
 * `facturaApi.ts` — Zod mirror of the enriched F1.9 + F8.4
 * `FacturaRead` wire shape for `POST /api/v1/facturacion/factura`.
 *
 * History: post-PR1 (2026-09-23), the BE response carries 22 fields
 * (was 11). The display projection (`datos_sucursal`, `datos_vehiculo`,
 * `impuestos[]`, `cliente`, `numero_recibo`, `medio_pago`,
 * `factura_electronica`, `pagos[]`) is now part of the same round-trip
 * so `<FacturaDisplayModal />` (HU-F8.4) renders without a second
 * call.
 *
 * Mirrors `features/operacion/api/salidaApi.ts` precedent (F7.2):
 * the renderer-side Zod parser enforces the discriminator + nested
 * invariants so a misbehaving backend (extra fields, wrong types)
 * surfaces as a parse error instead of silently rendering a
 * half-truthy pago confirmation.
 *
 * **BE↔FE contract fix (HU-F8.4, 2026-09-23).** The POST payload
 * required by the BE is `{uuid_salida, items[], subtotal, total,
 * medio_pago, ...}` (per backend ``FacturaCreate`` schema, line 578+
 * of ``backend/packages/parkos_core/src/parkos_core/schemas/
 * facturacion.py``). The previous FE sent
 * `{uuid_ingreso, medio_pago, ...}` which the BE would have rejected
 * with 422 — silent pago. The FE payload now carries
 * `uuid_salida` (PagoSheet propagates it from `pagoContext` via the
 * `hu-f8-1-anular-salida-no-pagada` series; commit `c7c19d2`).
 *
 * Wire contract:
 * - `cliente` is OPTIONAL — NULL for consumidor final (NIT
 *   `222222222222222`, default per DEC-SUC-04).
 * - `datos_vehiculo` is OPTIONAL — NULL for facturacion paths that
 *   don't have a linked ingreso (e.g. suscripcion venta, future paths).
 * - `factura_electronica` is OPTIONAL — NULL until the cloud
 *   dispatcher numbers the FE document.
 * - `monto_recibido_cents` / `vuelto_cents` are efectivo-only
 *   (NULL for datafono). `voucher` is datafono-only (NULL for
 *   efectivo). The BE computes `monto_recibido_cents` from the init
 *   `factura_pagos.valor` for now (FE was sending client-side, MVP).
 */
import { z } from 'zod';

/**
 * Email RFC 5322 lite — pragmatic subset that matches the F1.10
 * Pydantic `EmailStr` validator. The full RFC is impractical to
 * implement in a renderer; this subset catches the operator-facing
 * typos (missing `@`, missing TLD, illegal whitespace) without
 * rejecting legitimate edge cases like `+aliases`.
 */
const emailRfc5322Lite = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Bug 23 (2026-09-24): Pydantic v2 serializes `Decimal` fields to a
 * JSON STRING (e.g. `"81.0000"`), not a number — every money field on
 * `FacturaRead` (`schemas/facturacion.py` — `subtotal`, `descuento`,
 * `total`, `FacturaItemRead.valor_unitario/subtotal`,
 * `FacturaDisplayImpuesto.*`, `FacturaDisplayPago.valor`) is
 * `Decimal`-backed. Plain `z.number()` rejected every one of them,
 * so `FacturaReadSchema.parse(raw)` threw on EVERY successful pago —
 * `<FacturaDisplayModal />` and the post-pago print never ran, even
 * though the BE had already persisted the factura. These helpers
 * accept either shape and normalize to a JS number for display.
 */
const decimalNumber = z.union([z.number(), z.string()]).transform((v) => Number(v));
const decimalNumberNullable = z
  .union([z.number(), z.string()])
  .nullable()
  .transform((v) => (v === null ? null : Number(v)));

const clienteSchema = z.object({
  tipo_identificador: z.enum(['NIT', 'CC', 'CE', 'pasaporte']).nullable(),
  numero_identificacion: z.string().nullable(),
  dv: z.string().nullable().optional(),
  nombre: z.string().nullable(),
  apellido: z.string().nullable().optional(),
  email: z.string().regex(emailRfc5322Lite).nullable().optional(),
  telefono: z.string().nullable().optional(),
});

const datosSucursalSchema = z.object({
  razon_social: z.string().nullable(),
  nit: z.string().nullable(),
  direccion: z.string().nullable(),
  ciudad: z.string().nullable(),
  telefono: z.string().nullable(),
  horario: z.string().nullable(),
  regimen: z.string().nullable(),
});

const datosVehiculoSchema = z.object({
  placa: z.string().nullable(),
  uuid_tipo_vehiculo: z.string().uuid().nullable(),
  fecha_ingreso: z.string().nullable(),
  fecha_salida: z.string().nullable(),
  minutos: z.number().int().nullable(),
});

const impuestoDisplaySchema = z.object({
  uuid: z.string().uuid(),
  uuid_impuesto: z.string().uuid().nullable(),
  nombre_impuesto: z.string().nullable(),
  codigo_impuesto: z.string().nullable(),
  base_calculo: decimalNumberNullable,
  porcentaje_aplicado: decimalNumberNullable,
  valor: decimalNumberNullable,
});

const pagoDisplaySchema = z.object({
  uuid: z.string().uuid(),
  medio_pago: z.string().nullable(),
  valor: decimalNumberNullable,
  referencia: z.string().nullable(),
});

const feDisplaySchema = z.object({
  uuid: z.string().uuid(),
  prefijo: z.string().nullable(),
  consecutivo: z.number().int().nullable(),
  estado_dian: z.enum(['pendiente', 'enviado', 'aceptado', 'rechazado']),
  cufe: z.string().nullable(),
});

const itemSchema = z.object({
  uuid: z.string().uuid(),
  tipo: z.string(),
  concepto: z.string(),
  cantidad: z.number().int(),
  valor_unitario: decimalNumber,
  subtotal: decimalNumber,
});

/**
 * HU-F8.4 enriched FacturaRead. The BE returns 22 fields; the FE
 * consumes all of them for the `<FacturaDisplayModal />`. Some
 * fields are nullable on the wire (e.g. `cliente` for consumidor
 * final, `factura_electronica` until the cloud dispatches, `pagos`
 * array empty in MVP — FE reads `medio_pago` + form values for
 * vueltos/voucher).
 */
export const FacturaReadSchema = z.object({
  // --- Base (HU-F1.9) ---
  uuid: z.string().uuid(),
  created_at: z.string(),
  uuid_sucursal: z.string().uuid(),
  uuid_ingreso: z.string().uuid().nullable(),
  uuid_salida: z.string().uuid().nullable(),
  subtotal: decimalNumber,
  descuento: decimalNumber,
  total: decimalNumber,
  uuid_cliente: z.string().uuid().nullable(),
  items: z.array(itemSchema),
  estado: z.enum(['emitida', 'pagada', 'anulada']),

  // --- HU-F8.4 display enrichment ---
  // 'suscripcion' added 2026-09-24 (salida-mensualidad $0 factura,
  // full breakdown + discount, operator directive).
  medio_pago: z.enum(['efectivo', 'tarjeta', 'transferencia', 'datafono', 'mixto', 'suscripcion']),
  monto_recibido_cents: z.number().int().nullable(),
  vuelto_cents: z.number().int().nullable(),
  voucher: z.string().nullable(),
  numero_recibo: z.string(),
  cliente: clienteSchema.nullable(),
  datos_sucursal: datosSucursalSchema,
  datos_vehiculo: datosVehiculoSchema.nullable(),
  impuestos: z.array(impuestoDisplaySchema),
  pagos: z.array(pagoDisplaySchema),
  factura_electronica: feDisplaySchema.nullable(),
});
export type FacturaRead = z.infer<typeof FacturaReadSchema>;

const POST_PATH = '/api/v1/facturacion/factura';

/**
 * BE↔FE fix (Bug 22, 2026-09-23): the BE's `FacturaCreate`
 * (`schemas/facturacion.py:568`) requires `uuid_salida`, a non-empty
 * `items[]` (server does NOT derive them — `extra='forbid'` also
 * rejects any unknown field), `subtotal` (pre-IVA base, display-only
 * — stored verbatim, never cross-checked), and `total` (validated
 * server-side against `sum(item.cantidad * item.valor_unitario)`
 * within ±0.01 COP — see `repo.factura.compute_total`). There is NO
 * `cliente` field: consumidor final is the default (`fe_con_datos`
 * omitted/false); a named invoice sets `fe_con_datos: true` +
 * `fe_datos_cliente`. `datafono` voucher travels as `referencia`
 * (shared with `medio_pago='datafono'` V7 `voucher_requerido`),
 * NOT `voucher`.
 *
 * The single line item mirrors the cotización's tarifa snapshot:
 * one `tipo: 'servicio'` line whose `valor_unitario` equals `total`
 * (the PL/pgSQL `calcular_cotizacion` base — see `compute_total`
 * docstring), cantidad 1.
 */
export interface FacturaItemPost {
  /**
   * `'descuento'` (2026-09-24, salida-mensualidad factura): `valor_unitario`
   * stays POSITIVE (backend `ge=0` unchanged) — the backend's
   * `compute_total` is what SUBTRACTS it instead of adding it.
   */
  tipo: 'servicio' | 'producto' | 'descuento';
  concepto: string;
  cantidad: number;
  valor_unitario: number;
  uuid_tarifa_sucursal?: string | null;
}

export interface FacturaClienteDatosPost {
  tipo_identificador: 'NIT' | 'CC' | 'CE' | 'pasaporte';
  numero_identificacion: string;
  dv?: string | null;
  nombre: string;
  apellido?: string | null;
  email?: string | null;
  telefono?: string | null;
}

export interface PostFacturaEfectivo {
  uuid_salida: string;
  medio_pago: 'efectivo';
  items: FacturaItemPost[];
  subtotal: number;
  total: number;
  fe_con_datos?: boolean;
  fe_datos_cliente?: FacturaClienteDatosPost;
}

export interface PostFacturaDatafono {
  uuid_salida: string;
  medio_pago: 'datafono';
  items: FacturaItemPost[];
  subtotal: number;
  total: number;
  referencia: string;
  fe_con_datos?: boolean;
  fe_datos_cliente?: FacturaClienteDatosPost;
}

/**
 * `medio_pago='suscripcion'` (2026-09-24, operator directive): the
 * salida-mensualidad factura — `total=0` (net, after the discount
 * line), no voucher, no operator interaction. Mirrors
 * `PostFacturaEfectivo`'s shape (no `referencia` required, same as
 * efectivo) but with its own discriminant so the backend can identify
 * a $0-via-subscription payment distinctly from a $0 cash payment.
 */
export interface PostFacturaSuscripcion {
  uuid_salida: string;
  medio_pago: 'suscripcion';
  items: FacturaItemPost[];
  subtotal: number;
  total: number;
  fe_con_datos?: boolean;
  fe_datos_cliente?: FacturaClienteDatosPost;
}

export type PostFacturaPayload =
  | PostFacturaEfectivo
  | PostFacturaDatafono
  | PostFacturaSuscripcion;

const facturaItemPostSchema = z.object({
  tipo: z.enum(['servicio', 'producto', 'descuento']),
  concepto: z.string().min(1).max(255),
  cantidad: z.number().int().positive(),
  valor_unitario: z.number().nonnegative(),
  uuid_tarifa_sucursal: z.string().uuid().nullable().optional(),
});

const facturaClienteDatosPostSchema = z.object({
  tipo_identificador: z.enum(['NIT', 'CC', 'CE', 'pasaporte']),
  numero_identificacion: z.string().min(5).max(20),
  dv: z.string().min(1).max(2).nullable().optional(),
  nombre: z.string().min(1).max(120),
  apellido: z.string().min(1).max(120).nullable().optional(),
  email: z.string().min(5).max(120).nullable().optional(),
  telefono: z.string().min(7).max(20).nullable().optional(),
});

export const PostFacturaSchema = z.discriminatedUnion('medio_pago', [
  z.object({
    uuid_salida: z.string().uuid(),
    medio_pago: z.literal('efectivo'),
    items: z.array(facturaItemPostSchema).min(1).max(50),
    subtotal: z.number(),
    total: z.number().nonnegative(),
    fe_con_datos: z.boolean().optional(),
    fe_datos_cliente: facturaClienteDatosPostSchema.optional(),
  }),
  z.object({
    uuid_salida: z.string().uuid(),
    medio_pago: z.literal('datafono'),
    items: z.array(facturaItemPostSchema).min(1).max(50),
    subtotal: z.number(),
    total: z.number().nonnegative(),
    referencia: z.string().min(1, 'voucher_requerido'),
    fe_con_datos: z.boolean().optional(),
    fe_datos_cliente: facturaClienteDatosPostSchema.optional(),
  }),
  z.object({
    uuid_salida: z.string().uuid(),
    medio_pago: z.literal('suscripcion'),
    items: z.array(facturaItemPostSchema).min(1).max(50),
    subtotal: z.number(),
    total: z.number().nonnegative(),
    fe_con_datos: z.boolean().optional(),
    fe_datos_cliente: facturaClienteDatosPostSchema.optional(),
  }),
]);

/**
 * `postFactura(payload, idempotencyKey)` — typed wrapper around
 * `parkosFetch` that forwards the supplied `Idempotency-Key` header
 * verbatim. Errors propagate as `ParkosHttpError`.
 */
export async function postFactura(
  payload: PostFacturaPayload,
  idempotencyKey: string,
): Promise<FacturaRead> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  PostFacturaSchema.parse(payload);
  const raw = await parkosFetch<unknown>(POST_PATH, {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  });
  return FacturaReadSchema.parse(raw);
}

export const FACTURA_POST_PATH = POST_PATH;