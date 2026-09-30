/**
 * `reporteriaSchema.ts` — Zod schemas + types for the operational reports
 * (HU-F17.1).
 *
 * Wire shape mirrors the backend `schemas/operacion.py` exactly:
 *
 *   GET /api/v1/operacion/ingresos  -> IngresoRead[]          (flat list)
 *   GET /api/v1/operacion/salidas   -> SalidaListRead[]       (flat list)
 *   GET /api/v1/operacion/ocupacion -> OcupacionResponse       (object)
 *
 * The flat list shape is the current contract — no `next_cursor` /
 * `items` envelope until PR-C adds cursor pagination on the report
 * aggregation endpoints. The PR-A tenant-scope fix on
 * `list_ingresos` and `list_salidas` is upstream of these reads:
 * every record here is already restricted to the caller's permitted
 * branches (see auth/tenancy.py::require_branch_scope).
 *
 * Why Zod here even though the backend Pydantic gives the same shape:
 * a wrong field name on the client (e.g. `placa` vs `plates`) becomes
 * a parsing error rather than a silent `undefined` in the UI. The cost
 * is small (one z.object per response), the safety is per request.
 */
import { z } from 'zod';

const nullableDate = z
  .string()
  .nullable()
  .transform((v) => (v === null || v === '' ? null : new Date(v)))
  .refine((d) => d === null || !Number.isNaN(d.getTime()), {
    message: 'fecha inválida',
  });

export const ingresoReadSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  placa: z.string().nullable(),
  uuid_tipo_vehiculo: z.string().uuid().nullable(),
  uuid_subscripcion_cliente: z.string().uuid().nullable(),
  fecha_ingreso: nullableDate,
  observaciones: z.string().nullable(),
  consecutivo: z.string().nullable(),
});

export type IngresoRead = z.infer<typeof ingresoReadSchema>;

export const salidaListReadSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_ingreso: z.string().uuid().nullable(),
  fecha_salida: nullableDate,
  placa: z.string().nullable(),
  uuid_tipo_vehiculo: z.string().uuid().nullable(),
  consecutivo: z.string().nullable(),
});

export type SalidaListRead = z.infer<typeof salidaListReadSchema>;

export const ocupacionItemSchema = z.object({
  uuid_tipo_vehiculo: z.string().uuid(),
  tipo: z.string(),
  cupo_maximo: z.number().int(),
  activos: z.number().int(),
  disponible: z.number().int(),
});

export type OcupacionItem = z.infer<typeof ocupacionItemSchema>;

export const ocupacionResponseSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  items: z.array(ocupacionItemSchema),
  generado_en: z.string(),
});

export type OcupacionResponse = z.infer<typeof ocupacionResponseSchema>;

export interface ReporteriaQuery {
  uuid_sucursal: string;
  placa?: string;
  activo?: boolean;
  fecha_desde?: string;
  fecha_hasta?: string;
  limit?: number;
}