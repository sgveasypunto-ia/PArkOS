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

export const reporteOperacionalItemSchema = z.object({
  fecha: z.string().nullable(),
  ingresos_count: z.number().int(),
  ingresos_activos_count: z.number().int(),
  salidas_count: z.number().int(),
  facturas_emitidas_count: z.number().int(),
  monto_facturado_total: z.number(),
  monto_cobrado_total: z.number(),
});

export type ReporteOperacionalItem = z.infer<typeof reporteOperacionalItemSchema>;

// HU-F17.2 additions -- ingresos filtrados (sucursal/fecha/tipo) con
// paginacion cursor estandar, y tiempos de estancia (BR1). Additive on
// the wire (backend keeps `items`/`totales` unchanged for the existing
// "Totales del periodo" panel + the dashboard's `ChartsSection`).
export const reporteOperacionalIngresoItemSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_tipo_vehiculo: z.string().uuid().nullable(),
  placa: z.string().nullable(),
  consecutivo: z.string().nullable(),
  fecha_ingreso: z.string().nullable(),
  fecha_salida: z.string().nullable(),
  tiempo_estancia_segundos: z.number().nullable(),
});

export type ReporteOperacionalIngresoItem = z.infer<
  typeof reporteOperacionalIngresoItemSchema
>;

export const reporteEstanciaItemSchema = z.object({
  fecha: z.string(),
  muestras: z.number().int(),
  promedio_segundos: z.number(),
  maximo_segundos: z.number(),
  minimo_segundos: z.number(),
});

export type ReporteEstanciaItem = z.infer<typeof reporteEstanciaItemSchema>;

export const reporteOperacionalResponseSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  fecha_desde: z.string(),
  fecha_hasta: z.string(),
  items: z.array(reporteOperacionalItemSchema),
  totales: reporteOperacionalItemSchema,
  generado_en: z.string(),
  ingresos: z.array(reporteOperacionalIngresoItemSchema).default([]),
  ingresos_next_cursor: z.string().nullable().default(null),
  tiempos_estancia: z.array(reporteEstanciaItemSchema).default([]),
});

export type ReporteOperacionalResponse = z.infer<typeof reporteOperacionalResponseSchema>;

// HU-F17.2 -- cross-branch occupancy heatmap (`/admin/reporteria/ocupacion`).
// Named distinctly from `ocupacionResponseSchema` above (the per-tipo
// cupo/activos snapshot from `/operacion/ocupacion`) -- same word,
// different endpoint and shape.
export const reporteOcupacionSucursalItemSchema = z.object({
  uuid: z.string().uuid(),
  nombre: z.string().nullable(),
});

export type ReporteOcupacionSucursalItem = z.infer<
  typeof reporteOcupacionSucursalItemSchema
>;

export const reporteOcupacionHeatmapCellSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  hora: z.number().int(),
  ingresos_count: z.number().int(),
});

export type ReporteOcupacionHeatmapCell = z.infer<
  typeof reporteOcupacionHeatmapCellSchema
>;

export const reporteOcupacionAgregadaSchema = z.object({
  ocupados: z.number().int(),
  capacidad: z.number().int(),
  porcentaje: z.number().nullable(),
});

export type ReporteOcupacionAgregada = z.infer<typeof reporteOcupacionAgregadaSchema>;

export const reporteOcupacionHeatmapResponseSchema = z.object({
  sucursales: z.array(reporteOcupacionSucursalItemSchema),
  data: z.array(reporteOcupacionHeatmapCellSchema),
  ocupacion_agregada: reporteOcupacionAgregadaSchema,
  desde: z.string(),
  hasta: z.string(),
  generado_en: z.string(),
});

export type ReporteOcupacionHeatmapResponse = z.infer<
  typeof reporteOcupacionHeatmapResponseSchema
>;