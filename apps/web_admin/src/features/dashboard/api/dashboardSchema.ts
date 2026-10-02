/**
 * `dashboardSchema.ts` — Zod schemas + types for the executive dashboard
 * (HU-F17.1).
 *
 * Wire shape mirrors `backend/.../api/v1/admin_views.py` exactly:
 *
 *   GET /api/v1/admin/sucursales/{uuid}/dashboard -> SucursalDashboard
 *   GET /api/v1/admin/dashboard/resumen           -> DashboardResumen
 *
 * Same rationale as `features/reporteria/api/reporteriaSchema.ts`: a
 * backend field-name drift becomes a parsing error here instead of a
 * silent `undefined` on a KPI card.
 */
import { z } from 'zod';

export const sucursalDashboardSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  fecha: z.string(),
  ingresos_count: z.number().int(),
  ingresos_monto_total: z.number(),
  facturas_emitidas_count: z.number().int(),
  facturas_electronicas_count: z.number().int(),
  open_alertas_count: z.number().int(),
  sync_health: z.object({
    last_sync_at: z.string().nullable(),
    lag_seconds: z.number().int().nullable(),
    queue_depth: z.number().int(),
  }),
});
export type SucursalDashboard = z.infer<typeof sucursalDashboardSchema>;

export const dashboardOcupacionAgregadaSchema = z.object({
  ocupados: z.number().int(),
  capacidad: z.number().int(),
  porcentaje: z.number().nullable(),
});

export const dashboardSuscripcionesActivasSchema = z.object({
  count: z.number().int(),
});

export const dashboardMedioPagoItemSchema = z.object({
  medio_pago: z.string(),
  monto_total: z.number(),
});

export const dashboardTopSucursalItemSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  nombre: z.string().nullable(),
  monto_total: z.number(),
});

export const dashboardSyncAgregadoSchema = z.object({
  sucursales_ok: z.number().int(),
  sucursales_degradadas: z.number().int(),
  queue_depth_total: z.number().int(),
  max_lag_seconds: z.number().int().nullable(),
});

export const dashboardAlertaSeveridadItemSchema = z.object({
  severity: z.string(),
  count: z.number().int(),
});

export const dashboardEstadoFEItemSchema = z.object({
  estado: z.string(),
  count: z.number().int(),
});

export const dashboardOcupacionHorariaItemSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  hora: z.number().int(),
  ingresos_count: z.number().int(),
});

export const dashboardResumenErrorSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  motivo: z.string(),
});

export const dashboardResumenSchema = z.object({
  sucursales: z.array(z.string().uuid()),
  ocupacion: dashboardOcupacionAgregadaSchema,
  suscripciones_activas: dashboardSuscripcionesActivasSchema,
  medios_pago_dia: z.array(dashboardMedioPagoItemSchema),
  top_sucursales: z.array(dashboardTopSucursalItemSchema),
  sync_agregado: dashboardSyncAgregadoSchema,
  alertas_por_severidad: z.array(dashboardAlertaSeveridadItemSchema),
  estado_envio_fe_24h: z.array(dashboardEstadoFEItemSchema),
  ocupacion_horaria: z.array(dashboardOcupacionHorariaItemSchema),
  errores: z.array(dashboardResumenErrorSchema),
  generado_en: z.string(),
});
export type DashboardResumen = z.infer<typeof dashboardResumenSchema>;
export type DashboardTopSucursalItem = z.infer<typeof dashboardTopSucursalItemSchema>;
export type DashboardOcupacionHorariaItem = z.infer<typeof dashboardOcupacionHorariaItemSchema>;
