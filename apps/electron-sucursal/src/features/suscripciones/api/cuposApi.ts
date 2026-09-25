/**
 * `cuposApi.ts` — Zod mirror of the HU-F9.2 realineada backend response
 * shapes for the 4 dedicated cupos-management endpoints
 * (`backend/.../api/v1/clientes_cupos.py`):
 *
 *   - `GET /clientes/subscripciones-activas`
 *   - `GET /clientes/subscripciones-activas/buscar?numero_identificacion=X`
 *   - `POST /clientes/subscripcion-vehiculos/agregar`
 *   - `PUT /clientes/subscripcion-vehiculos/{uuid}/quitar`
 *
 * Mirrors `ventaSuscripcionApi.ts` precedent: the renderer-side Zod
 * parser enforces the nested shape so a misbehaving backend surfaces
 * as a parse error instead of a silently wrong cupo count.
 */
import { z } from 'zod';

export const ClienteResumenSchema = z.object({
  uuid: z.string().uuid(),
  nombre: z.string().nullable(),
  apellido: z.string().nullable(),
  numero_identificacion: z.string().nullable(),
});
export type ClienteResumen = z.infer<typeof ClienteResumenSchema>;

export const PlanResumenSchema = z.object({
  uuid: z.string().uuid(),
  tipo: z.string().nullable(),
  valor: z.union([z.string(), z.number()]).nullable(),
  cantidad_maxima_vehiculos: z.number().nullable(),
  mismo_tipo_vehiculo: z.boolean().nullable(),
});
export type PlanResumen = z.infer<typeof PlanResumenSchema>;

export const VehiculoInscritoSchema = z.object({
  uuid: z.string().uuid(),
  uuid_vehiculo: z.string().uuid(),
  placa: z.string().nullable(),
});
export type VehiculoInscrito = z.infer<typeof VehiculoInscritoSchema>;

export const SubscripcionActivaItemSchema = z.object({
  uuid: z.string().uuid(),
  cliente: ClienteResumenSchema,
  plan: PlanResumenSchema,
  fecha_inicio_cobertura: z.string().nullable(),
  fecha_vencimiento: z.string().nullable(),
  cupo_maximo: z.number().nullable(),
  vehiculos_inscritos: z.number(),
});
export type SubscripcionActivaItem = z.infer<typeof SubscripcionActivaItemSchema>;

export const SubscripcionesActivasResponseSchema = z.object({
  items: z.array(SubscripcionActivaItemSchema),
});

export const SubscripcionCupoDetalleSchema = z.object({
  uuid: z.string().uuid(),
  cliente: ClienteResumenSchema,
  plan: PlanResumenSchema,
  fecha_inicio_cobertura: z.string().nullable(),
  fecha_vencimiento: z.string().nullable(),
  cupo_maximo: z.number().nullable(),
  cupo_disponible: z.number().nullable(),
  vehiculos: z.array(VehiculoInscritoSchema),
});
export type SubscripcionCupoDetalle = z.infer<typeof SubscripcionCupoDetalleSchema>;

/** `GET .../buscar` returns `null` (200) when no active subscription matches. */
export const SubscripcionCupoDetalleOrNullSchema = SubscripcionCupoDetalleSchema.nullable();

export const AgregarVehiculoCupoRequestSchema = z.object({
  uuid_subscripcion_cliente: z.string().uuid(),
  placa: z
    .string()
    .trim()
    .min(1, 'placa_requerida')
    .max(16, 'placa_max_16')
    .transform((v) => v.toUpperCase()),
});
export type AgregarVehiculoCupoRequest = z.infer<typeof AgregarVehiculoCupoRequestSchema>;

export const GET_SUBSCRIPCIONES_ACTIVAS_PATH = '/api/v1/clientes/subscripciones-activas';
export const GET_BUSCAR_SUBSCRIPCION_PATH =
  '/api/v1/clientes/subscripciones-activas/buscar';
export const POST_AGREGAR_VEHICULO_PATH =
  '/api/v1/clientes/subscripcion-vehiculos/agregar';

export function putQuitarVehiculoPath(uuidSubscripcionVehiculo: string): string {
  return `/api/v1/clientes/subscripcion-vehiculos/${uuidSubscripcionVehiculo}/quitar`;
}
