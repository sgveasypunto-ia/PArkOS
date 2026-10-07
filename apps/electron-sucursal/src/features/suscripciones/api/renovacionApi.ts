/**
 * `renovacionApi.ts` — Zod mirror of the PT-3 renewal contract
 * (`backend/.../schemas/renovacion.py`, `api/v1/clientes_renovacion.py`):
 *
 *   - `POST /clientes/subscripciones/{uuid}/renovar`  (201, Idempotency-Key required)
 *   - `GET  /clientes/subscripciones/renovables`      (<= 10 days left, expired included)
 *   - `GET  /clientes/subscripciones/proximas-vencer` (banner feed)
 *
 * The UI NEVER recalculates dates: `puede_renovar` / `dias_restantes` come
 * from the backend (Bogota's calendar).
 */
import { z } from 'zod';

import { FacturaReadSchema } from '../../facturacion/api/facturaApi';

export const MEDIOS_PAGO_RENOVACION = [
  'efectivo',
  'tarjeta',
  'datafono',
  'transferencia',
] as const;
export type MedioPagoRenovacion = (typeof MEDIOS_PAGO_RENOVACION)[number];

/** Request body. `datafono` requires the voucher in `referencia`. */
export const RenovarSuscripcionRequestSchema = z
  .object({
    medio_pago: z.enum(MEDIOS_PAGO_RENOVACION),
    referencia: z.string().trim().min(1).max(255).nullable(),
  })
  .superRefine((v, ctx) => {
    if (v.medio_pago === 'datafono' && !v.referencia) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['referencia'],
        message: 'voucher_requerido',
      });
    }
  });
export type RenovarSuscripcionRequest = z.infer<typeof RenovarSuscripcionRequestSchema>;

export const RenovarSuscripcionResponseSchema = z.object({
  uuid_subscripcion_anterior: z.string().uuid(),
  uuid_subscripcion: z.string().uuid(),
  uuid_cliente: z.string().uuid().nullable(),
  uuid_sucursal: z.string().uuid(),
  uuid_tipo_subscripcion: z.string().uuid(),
  uuid_vehiculos: z.array(z.string().uuid()),
  placas: z.array(z.string()),
  fecha_inicio_cobertura: z.string(),
  fecha_vencimiento: z.string(),
  dias_restantes: z.number(),
  renovacion_anticipada: z.boolean(),
  ventana_renovacion_dias: z.number(),
  // Pydantic serializes Decimal as a JSON string.
  valor_total_plan: z.coerce.number(),
  total_con_iva: z.coerce.number(),
  uuid_factura: z.string().uuid(),
  uuid_factura_electronica: z.string().uuid().nullable().optional(),
  factura_electronica_error: z.string().nullable().optional(),
  factura_electronica_pendiente: z.boolean().optional(),
  factura: FacturaReadSchema.nullable(),
});
export type RenovarSuscripcionResponse = z.infer<typeof RenovarSuscripcionResponseSchema>;

/** Row of `/renovables` and `/proximas-vencer`. */
export const SuscripcionVencimientoItemSchema = z.object({
  uuid: z.string().uuid(),
  cliente_nombre: z.string(),
  plan_nombre: z.string(),
  placas: z.array(z.string()),
  fecha_vencimiento: z.string(),
  dias_restantes: z.number(),
  dias_alerta_pre_vencimiento: z.number().nullable().optional(),
  puede_renovar: z.boolean(),
});
export type SuscripcionVencimientoItem = z.infer<typeof SuscripcionVencimientoItemSchema>;

export const SuscripcionVencimientoListSchema = z.array(SuscripcionVencimientoItemSchema);

export const GET_RENOVABLES_PATH = '/api/v1/clientes/subscripciones/renovables';
export const GET_PROXIMAS_VENCER_PATH = '/api/v1/clientes/subscripciones/proximas-vencer';

export function postRenovarPath(uuidSubscripcion: string): string {
  return `/api/v1/clientes/subscripciones/${uuidSubscripcion}/renovar`;
}
