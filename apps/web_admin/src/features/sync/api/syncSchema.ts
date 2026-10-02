/**
 * `syncSchema.ts` — Zod schemas for the HU-F19.2 sync dashboard
 * (web_admin), mirroring the HU-F19.1 backend response models verbatim
 * (`backend/packages/parkos_core/src/parkos_core/api/v1/admin_views.py`,
 * `SyncLogListResponse` / `SyncConflictListResponse` /
 * `SyncEstadoAgregadoResponse`).
 *
 * `estado` on `SyncEstadoSucursalItem` is the server's own verde/
 * amarillo/rojo classification (BR1, computed from the 60s/300s
 * thresholds in `_clasificar_sync_estado`) -- it is parsed and rendered
 * as-is. This client NEVER recomputes those thresholds (see
 * `hooks/useSync.ts`'s heatmap-bucketing docstring for the one place
 * this repo derives its OWN, clearly-labeled lag numbers, which stay
 * sequential/numeric and never reclassify into a color).
 */
import { z } from 'zod';

export const syncLogReadSchema = z.object({
  uuid: z.string().uuid(),
  fecha_retencion_hasta: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  timestamp_evento: z.string().nullable(),
  operaciones_enviadas: z.number().int().nullable(),
  operaciones_exitosas: z.number().int().nullable(),
  operaciones_fallidas: z.number().int().nullable(),
  conflictos: z.number().int().nullable(),
  duracion_ms: z.number().int().nullable(),
});
export type SyncLogRead = z.infer<typeof syncLogReadSchema>;

export const syncLogListResponseSchema = z.object({
  items: z.array(syncLogReadSchema),
  next_cursor: z.string().nullable(),
});
export type SyncLogListResponse = z.infer<typeof syncLogListResponseSchema>;

export const syncConflictReadSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  fecha_retencion_hasta: z.string().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  tabla: z.string().nullable(),
  uuid_registro: z.string().uuid().nullable(),
  datos_local: z.record(z.unknown()).nullable(),
  datos_cloud: z.record(z.unknown()).nullable(),
  politica: z.string().nullable(),
  resolucion: z.string().nullable(),
  timestamp_evento: z.string().nullable(),
});
export type SyncConflictRead = z.infer<typeof syncConflictReadSchema>;

export const syncConflictListResponseSchema = z.object({
  items: z.array(syncConflictReadSchema),
  next_cursor: z.string().nullable(),
});
export type SyncConflictListResponse = z.infer<typeof syncConflictListResponseSchema>;

export const SYNC_ESTADOS = ['verde', 'amarillo', 'rojo'] as const;
export type SyncEstadoColor = (typeof SYNC_ESTADOS)[number];

export const syncEstadoSucursalItemSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  nombre: z.string().nullable(),
  estado: z.enum(SYNC_ESTADOS),
  last_sync_at: z.string().nullable(),
  lag_seconds: z.number().int().nullable(),
  queue_depth: z.number().int(),
});
export type SyncEstadoSucursalItem = z.infer<typeof syncEstadoSucursalItemSchema>;

export const syncEstadoAgregadoResponseSchema = z.object({
  items: z.array(syncEstadoSucursalItemSchema),
  generado_en: z.string(),
});
export type SyncEstadoAgregadoResponse = z.infer<typeof syncEstadoAgregadoResponseSchema>;

export interface SyncLogQuery {
  uuid_sucursal?: string;
  desde?: string;
  hasta?: string;
  cursor?: string;
  limit?: number;
}

export interface SyncConflictQuery {
  uuid_sucursal?: string;
  cursor?: string;
  limit?: number;
}
