/**
 * `auditSchema.ts` — Zod schemas + types for the IT-12 audit-log
 * dashboard.
 *
 * Wire shape mirrors the backend
 * ``schemas/log_transaccional.py`` exactly so a round-trip parse
 * never fails on a fresh payload. The dashboard renders:
 *   - Per-row hash-chain badge (hash_anterior -> hash_actual).
 *   - Diff payload (datos_anteriores / datos_nuevos).
 *   - Cursor-paginated list with the active branch filter.
 */
import { z } from 'zod';

export const auditLogItemSchema = z.object({
  uuid: z.string().uuid(),
  timestamp_evento: z.string(),
  uuid_usuario: z.string().uuid().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_referencia: z.string().uuid().nullable(),
  accion: z.string().nullable(),
  tabla_afectada: z.string().nullable(),
  datos_anteriores: z.record(z.unknown()).nullable(),
  datos_nuevos: z.record(z.unknown()).nullable(),
  hash_anterior: z.string().nullable(),
  hash_actual: z.string().nullable(),
});

export type AuditLogItem = z.infer<typeof auditLogItemSchema>;

export const auditLogListResponseSchema = z.object({
  items: z.array(auditLogItemSchema),
  next_cursor: z.string().nullable(),
});

export type AuditLogListResponse = z.infer<typeof auditLogListResponseSchema>;

export const auditQuerySchema = z.object({
  // HU-F15.2 EmpresaBitacoraTab queries by ``tabla_afectada='empresa'``
  // alone (Empresa is a singleton tenant-global, no uuid_sucursal).
  // The branch-scoped AuditDashboard keeps passing uuid_sucursal.
  // The backend (``schemas/log_transaccional.py``) raises a typed
  // ``missing_selector`` 422 if NEITHER is provided.
  uuid_sucursal: z.string().uuid().optional(),
  tabla_afectada: z.string().min(1).max(64).optional(),
  limit: z.number().int().min(1).max(100).default(20),
  cursor: z.string().nullable().optional(),
});

export type AuditQuery = z.infer<typeof auditQuerySchema>;
