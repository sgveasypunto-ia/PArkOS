/**
 * `anulacionesSchema.ts` — Zod schemas + TS types for the HU-F20.3 admin
 * "anulaciones" surface (`[L-W]` workflow chain over `prod.anulacion`).
 *
 * Wire shapes verified against the real backend ORM model + the
 * HU-F20.3 contract handed down with this task (NOT `plan.md`'s prose,
 * which uses stale state names — see the `ANULACION_ESTADOS` comment
 * below).
 *
 *   - `AnulacionRead` matches `GET /api/v1/workflows/anulaciones`'s list
 *     items AND `GET /api/v1/workflows/anulaciones/{uuid}`'s single-item
 *     read — both are the SAME generic factory `AnulacionesRead` shape
 *     (unlike alerta, there's no separate "list carries severity, detail
 *     doesn't" split here).
 *   - `AnulacionesListResponse` matches `{items: AnulacionRead[],
 *     next_cursor: string|null}` — same cursor-paginated envelope every
 *     other list endpoint in this repo uses.
 *   - The list endpoint ONLY supports `cursor`/`limit` query params (no
 *     server-side filter by `estado`/`uuid_sucursal`/etc., unlike
 *     alerta's hand-built list) — see `AnulacionesListQuery`.
 */
import { z } from 'zod';

/**
 * Real `STATE_MACHINES['anulacion']` vocabulary
 * (`backend/packages/parkos_core/src/parkos_core/repo/workflow.py`).
 *
 * DRIFT WARNING: `plan.md`'s prose describes
 * `solicitada -> aprobada -> ejecutada`, which is WRONG / stale. Use
 * ONLY these real names (confirmed against the already-implemented and
 * tested backend code).
 */
export const ANULACION_ESTADOS = ['iniciada', 'autorizada', 'ejecutada', 'rechazada'] as const;
export type AnulacionEstado = (typeof ANULACION_ESTADOS)[number];

/** Polymorphic discriminator for what's being anulado. */
export const ANULACION_TIPOS = ['ingreso', 'salida'] as const;
export type AnulacionTipo = (typeof ANULACION_TIPOS)[number];

export const anulacionReadSchema = z.object({
  uuid: z.string().uuid(),
  fecha_retencion_hasta: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  tipo_anulable: z.enum(ANULACION_TIPOS).nullable(),
  uuid_ingreso: z.string().uuid().nullable(),
  uuid_salida: z.string().uuid().nullable(),
  uuid_usuario: z.string().uuid().nullable(),
  motivo: z.string().nullable(),
  uuid_anulacion_padre: z.string().uuid().nullable(),
  timestamp_evento: z.string().nullable(),
  vigente_desde: z.string().nullable(),
  vigente_hasta: z.string().nullable(),
  estado: z.enum(ANULACION_ESTADOS).nullable(),
});
export type AnulacionRead = z.infer<typeof anulacionReadSchema>;

export const anulacionesListResponseSchema = z.object({
  items: z.array(anulacionReadSchema),
  next_cursor: z.string().nullable(),
});
export type AnulacionesListResponse = z.infer<typeof anulacionesListResponseSchema>;

/** Only `cursor`/`limit` exist server-side for this list (see module docblock). */
export interface AnulacionesListQuery {
  limit: number;
  cursor?: string;
}

/**
 * react-hook-form + zodResolver input for the transition modal.
 * `motivo` mandatory + non-blank, mirrors `alertaDescartarFormSchema`
 * and the BE's `extra='forbid'` + non-blank validation.
 */
export const anulacionTransicionFormSchema = z.object({
  motivo: z.string().trim().min(1, 'El motivo es obligatorio.'),
});
export type AnulacionTransicionFormInput = z.infer<typeof anulacionTransicionFormSchema>;

/**
 * Legal destination states for a given TIP `estado`, per the HU-F20.3
 * contract. Client-side UX only (which buttons to offer) — the backend
 * remains the sole source of truth (409 `illegal_transition` on a race).
 */
export const ANULACION_TRANSICIONES: Record<AnulacionEstado, readonly AnulacionEstado[]> = {
  iniciada: ['autorizada', 'rechazada'],
  autorizada: ['ejecutada', 'rechazada'],
  ejecutada: [],
  rechazada: [],
};
