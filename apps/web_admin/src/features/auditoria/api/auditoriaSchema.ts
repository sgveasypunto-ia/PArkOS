/**
 * `auditoriaSchema.ts` — Zod schemas + TS types for the HU-F20.4 admin
 * "bitácora" surface (log_transaccional cross-branch listing, hash-chain
 * verification sweep, and bounded typeahead search).
 *
 * Wire shapes mirror the BE 1:1 (verified against
 * `backend/packages/parkos_core/src/parkos_core/schemas/log_transaccional.py`
 * and `api/v1/auditoria.py`, already merged into this same worktree):
 *
 *   - `AuditLogItem`         matches `schemas/log_transaccional.py::AuditLogItem`.
 *   - `AuditLogListResponse` matches `{items: AuditLogItem[], next_cursor: string|null}`
 *     — same cursor-paginated envelope every other list endpoint in this
 *     repo uses (mirrors `syncSchema.ts` / `arqueosSchema.ts` / `alertasSchema.ts`).
 *   - `datos_anteriores` / `datos_nuevos` are `z.record(z.unknown()).nullable()`,
 *     same as `syncConflictReadSchema.datos_local` / `datos_cloud`.
 *   - `ChainAnomalyItem` / `VerifyChainResponse` match the `/verify-chain`
 *     sweep response — `anomalias` can be empty (`ok: true`) or carry N
 *     entries; the sweep never short-circuits on the first one (BE docblock).
 *   - `BuscarPrefijoItem` / `BuscarPrefijoResponse` match the `/buscar`
 *     typeahead — no cursor, hard-capped at 10 results server-side (`le=10`).
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

/**
 * Query shape for `GET /api/v1/admin/log-transaccional`. All fields
 * optional except `limit` (server default 20, clamped 1..100) — mirrors
 * `arqueosSchema.ts::ArqueosListQuery` / `alertasSchema.ts::AlertasListQuery`.
 * The API layer builds the `URLSearchParams` with only the non-empty
 * fields (see `auditoriaApi.ts::fetchLogTransaccional`).
 */
export interface LogTransaccionalListQuery {
  tabla?: string;
  uuid_registro?: string;
  uuid_sucursal?: string;
  uuid_usuario?: string;
  desde?: string;
  hasta?: string;
  cursor?: string;
  limit?: number;
}

/**
 * Catalog tables the `/verify-chain` sweep can actually verify today
 * (`entry.verify_chain is True` in `SYNC_CATALOG_BY_NAME`, per the BE
 * docblock) — the FE select only offers these two; any other value
 * server-side 422s `tabla_no_verificable`.
 */
export const VERIFY_CHAIN_TABLAS = ['log_transaccional', 'revocacion_factura'] as const;
export type VerifyChainTabla = (typeof VERIFY_CHAIN_TABLAS)[number];

export interface VerifyChainQuery {
  tabla?: string;
  uuid_sucursal?: string;
}

export const chainAnomalyItemSchema = z.object({
  tabla: z.string(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid: z.string().uuid(),
  expected: z.string(),
  actual: z.string().nullable(),
  seq: z.number().int().nullable(),
  reason: z.string(),
});
export type ChainAnomalyItem = z.infer<typeof chainAnomalyItemSchema>;

export const verifyChainResponseSchema = z.object({
  ok: z.boolean(),
  anomalias: z.array(chainAnomalyItemSchema),
});
export type VerifyChainResponse = z.infer<typeof verifyChainResponseSchema>;

export interface BuscarPrefijoQuery {
  prefijo: string;
  limit?: number;
}

export const buscarPrefijoItemSchema = z.object({
  uuid: z.string().uuid(),
  tabla_afectada: z.string().nullable(),
  uuid_registro_afectado: z.string().uuid().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  timestamp_evento: z.string(),
});
export type BuscarPrefijoItem = z.infer<typeof buscarPrefijoItemSchema>;

export const buscarPrefijoResponseSchema = z.object({
  items: z.array(buscarPrefijoItemSchema),
});
export type BuscarPrefijoResponse = z.infer<typeof buscarPrefijoResponseSchema>;
