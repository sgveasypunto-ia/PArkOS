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

const clienteSchema = z.object({
  nit: z.string().nullable(),
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
  base_calculo: z.number().nullable(),
  porcentaje_aplicado: z.number().nullable(),
  valor: z.number().nullable(),
});

const pagoDisplaySchema = z.object({
  uuid: z.string().uuid(),
  medio_pago: z.string().nullable(),
  valor: z.number().nullable(),
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
  valor_unitario: z.number(),
  subtotal: z.number(),
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
  subtotal: z.number(),
  descuento: z.number(),
  total: z.number(),
  uuid_cliente: z.string().uuid().nullable(),
  items: z.array(itemSchema),
  estado: z.enum(['emitida', 'pagada', 'anulada']),

  // --- HU-F8.4 display enrichment ---
  medio_pago: z.enum(['efectivo', 'tarjeta', 'transferencia', 'datafono', 'mixto']),
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
 * BE↔FE fix (HU-F8.4, 2026-09-23): the BE's `FacturaCreate` requires
 * `uuid_salida` (the salida created by `POST /operacion/salidas`
 * before the pago) and `items[]` (server-side computed from the
 * tarifa structure). The FE previously sent `uuid_ingreso` only;
 * the BE would have rejected with 422 (silent pago). The new
 * payload carries `uuid_salida` so the BE matches its contract.
 *
 * Items are NOT sent from the FE because the BE derives them from
 * the tarifa structure (DEC-FACT-03: server-side IVA recompute).
 * The FE only sends the discriminator + monetary totals + cliente.
 * The BE returns the per-item breakdown in `FacturaRead.items[]`.
 */
export interface PostFacturaEfectivo {
  uuid_salida: string;
  medio_pago: 'efectivo';
  total_cents: number;
  cliente: { nit: string; nombre: string; email?: string | null };
}

export interface PostFacturaDatafono {
  uuid_salida: string;
  medio_pago: 'datafono';
  total_cents: number;
  voucher: string;
  cliente: { nit: string; nombre: string; email?: string | null };
}

export type PostFacturaPayload = PostFacturaEfectivo | PostFacturaDatafono;

export const PostFacturaSchema = z.discriminatedUnion('medio_pago', [
  z.object({
    uuid_salida: z.string().uuid(),
    medio_pago: z.literal('efectivo'),
    total_cents: z.number().int().nonnegative(),
    cliente: clienteSchema,
  }),
  z.object({
    uuid_salida: z.string().uuid(),
    medio_pago: z.literal('datafono'),
    total_cents: z.number().int().nonnegative(),
    voucher: z.string().min(1, 'voucher_requerido'),
    cliente: clienteSchema,
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