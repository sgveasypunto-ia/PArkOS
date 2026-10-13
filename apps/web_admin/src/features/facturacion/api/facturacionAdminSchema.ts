/**
 * `facturacionAdminSchema.ts` — Zod mirrors for the HU-X web-admin
 * drill-down surface (REQ-X-02..07 of `facturacion-admin/spec.md`).
 *
 * Five endpoints covered:
 *
 *   GET /api/v1/facturacion/facturas/{uuid}                    -> FacturaDetailRead
 *   GET /api/v1/facturacion/factura-detalle?uuid_factura=...    -> FacturaDetalleList
 *   GET /api/v1/facturacion/factura-impuestos?uuid_factura=...  -> FacturaImpuestoList
 *   GET /api/v1/facturacion/factura-pagos?uuid_factura=...      -> FacturaPagoList
 *   GET /api/v1/facturacion/factura-electronica/{uuid}          -> FacturaElectronicaRead
 *
 * Wire shapes verified against `parkos-api-admin:8000` in
 * `openspec/changes/hu-x-facturacion-admin/exploration.md` §"Verificación
 * de visibilidad vía API" (commit 2026-10-13). Money fields arrive as
 * Pydantic-v2-serialized `Decimal` strings ("5000.0000"), not numbers
 * (F1.9 precedent in `apps/electron-sucursal/src/features/facturacion/
 * api/facturaApi.ts:53-67`); the same `decimalNumber` / `decimalNumberNullable`
 * transform pattern is reused.
 *
 * Why Zod: a wire-shape drift on the client surfaces as a parse error
 * instead of `undefined` in the UI. Cost: one `z.object` per endpoint.
 */
import { z } from 'zod';

/**
 * Money field: BE serializes Pydantic-v2 `Decimal` as a string. Accept
 * both shapes (number AND string) and coerce to JS number for display.
 * The contract in `electron-sucursal/src/features/facturacion/api/
 * facturaApi.ts:63-67` documents this drift as Bug 23 (2026-09-24).
 */
const decimalNumber = z
  .union([z.number(), z.string()])
  .transform((v) => Number(v));

const decimalNumberNullable = z
  .union([z.number(), z.string()])
  .nullable()
  .transform((v) => (v === null ? null : Number(v)));

const nullableString = z
  .union([z.string(), z.null()])
  .nullable()
  .transform((v) => v ?? null);

const nullableUuid = z
  .union([z.string().uuid(), z.null()])
  .nullable()
  .transform((v) => v ?? null);

/**
 * `FacturaDetailRead` — header row from
 * `GET /api/v1/facturacion/facturas/{uuid}` (BE factory, plural).
 *
 * Source wire shape (verified 2026-10-13):
 * ```json
 * {uuid, created_at, created_by, sync_status, sync_timestamp, sync_attempts,
 *  fecha_retencion_hasta, uuid_sucursal, subtotal, descuento, total,
 *  uuid_ingreso, uuid_salida}
 * ```
 *
 * The X.1a endpoint returns the RAW row — no `estado`, no `cliente`, no
 * `numero_completo`. The display page derives:
 *   - `estado` from `V_FACTURA_ESTADO` (or `lib/estadoFactura.ts` shim for
 *     MVP — see REQ-X-02).
 *   - `numero_completo` from `GET /factura-electronica/{uuid}` (separate
 *     call, REQ-X-07).
 */
export const facturaDetailReadSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: nullableString,
  sync_timestamp: nullableString,
  sync_attempts: z.number().int().nullable(),
  fecha_retencion_hasta: z.string(),
  uuid_sucursal: z.string().uuid(),
  uuid_ingreso: nullableUuid,
  uuid_salida: nullableUuid,
  subtotal: decimalNumber,
  descuento: decimalNumber,
  total: decimalNumber,
});

export type FacturaDetailRead = z.infer<typeof facturaDetailReadSchema>;

/**
 * `FacturaDetalleItem` — one row of `GET /facturacion/factura-detalle`.
 *
 * Source wire shape:
 * ```json
 * {uuid, created_at, created_by, sync_status, sync_timestamp, sync_attempts,
 *  fecha_retencion_hasta, uuid_sucursal, uuid_factura, concepto, cantidad,
 *  valor_unitario, subtotal}
 * ```
 */
export const facturaDetalleItemSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: nullableString,
  sync_timestamp: nullableString,
  sync_attempts: z.number().int().nullable(),
  fecha_retencion_hasta: z.string(),
  uuid_sucursal: nullableString,
  uuid_factura: z.string().uuid(),
  concepto: z.string(),
  cantidad: z.number().int(),
  valor_unitario: decimalNumber,
  subtotal: decimalNumber,
});

export type FacturaDetalleItem = z.infer<typeof facturaDetalleItemSchema>;

/**
 * Cursor-paginated list envelope. Used by `factura-detalle`,
 * `factura-impuestos`, and `factura-pagos` (X.1a fix).
 */
export const paginatedListSchema = <T extends z.ZodTypeAny>(item: T) =>
  z.object({
    items: z.array(item),
    next_cursor: z.string().nullable(),
  });

export const facturaDetalleListSchema = paginatedListSchema(facturaDetalleItemSchema);
export type FacturaDetalleList = z.infer<typeof facturaDetalleListSchema>;

/**
 * `FacturaImpuestoItem` — one row of `GET /facturacion/factura-impuestos`.
 */
export const facturaImpuestoItemSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: nullableString,
  sync_timestamp: nullableString,
  sync_attempts: z.number().int().nullable(),
  fecha_retencion_hasta: z.string(),
  uuid_sucursal: nullableString,
  uuid_factura: z.string().uuid(),
  uuid_impuesto: z.string().uuid().nullable(),
  base_calculo: decimalNumber,
  porcentaje_aplicado: decimalNumberNullable,
  valor: decimalNumberNullable,
});

export type FacturaImpuestoItem = z.infer<typeof facturaImpuestoItemSchema>;
export const facturaImpuestoListSchema = paginatedListSchema(
  facturaImpuestoItemSchema,
);
export type FacturaImpuestoList = z.infer<typeof facturaImpuestoListSchema>;

/**
 * `FacturaPagoItem` — one row of `GET /facturacion/factura-pagos` (X.1a fix).
 *
 * `uuid_pago_revertido` and `uuid_sesion` are nullable (reversos and
 * pre-F8.4 pagos respectively). `tipo_movimiento` is
 * `'pago' | 'reverso' | 'ajuste'`.
 */
export const facturaPagoItemSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: nullableString,
  sync_timestamp: nullableString,
  sync_attempts: z.number().int().nullable(),
  fecha_retencion_hasta: z.string(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_factura: z.string().uuid(),
  uuid_sesion: nullableUuid,
  medio_pago: z.string().nullable(),
  valor: decimalNumber,
  referencia: nullableString,
  tipo_movimiento: z.string().nullable(),
  uuid_pago_revertido: nullableUuid,
  timestamp_evento: z.string().nullable(),
});

export type FacturaPagoItem = z.infer<typeof facturaPagoItemSchema>;
export const facturaPagoListSchema = paginatedListSchema(facturaPagoItemSchema);
export type FacturaPagoList = z.infer<typeof facturaPagoListSchema>;

/**
 * `FacturaElectronicaRead` — `GET /facturacion/factura-electronica/{uuid}`.
 *
 * May return 404 (`factura_electronica_no_encontrada`) when the factura
 * has no FE row yet (post-creation pending FE numbering, or
 * `factura_electronica_pendiente=true` from the POST response).
 *
 * The schema does NOT model `envio_actual` (chain tip) — that comes
 * from a separate `v_factura_electronica_acuse` view JOIN that the BE
 * applies internally. We only consume the card-level fields.
 */
export const facturaElectronicaReadSchema = z.object({
  uuid: z.string().uuid(),
  prefijo: nullableString,
  consecutivo: z.number().int().nullable(),
  estado_dian: z.enum(['pendiente', 'enviado', 'aceptado', 'rechazado']),
  cufe: nullableString,
});

export type FacturaElectronicaRead = z.infer<typeof facturaElectronicaReadSchema>;

/**
 * Cursor-paginated list for `GET /admin/log-transaccional?uuid_referencia=...`.
 * Only the top-level `items` (first one) is used by the drill-down page
 * to read the `hash_actual` for the header card.
 */
export const logTransaccionalItemSchema = z.object({
  uuid: z.string().uuid(),
  timestamp_evento: z.string(),
  uuid_usuario: z.string().uuid().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_referencia: nullableUuid,
  accion: z.string(),
  tabla_afectada: z.string(),
  hash_anterior: nullableString,
  hash_actual: z.string(),
});

export type LogTransaccionalItem = z.infer<typeof logTransaccionalItemSchema>;

export const logTransaccionalListSchema = z.object({
  items: z.array(logTransaccionalItemSchema),
  next_cursor: z.string().nullable(),
});
export type LogTransaccionalList = z.infer<typeof logTransaccionalListSchema>;
