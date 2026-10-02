/**
 * `reclamosSchema.ts` — Zod schemas + TS types for the HU-F20.3 admin
 * "reclamos" surface (`[L-W]` workflow chain over `prod.reclamo`).
 *
 * Wire shapes verified against the real backend ORM model + the
 * HU-F20.3 contract handed down with this task (NOT `plan.md`'s prose,
 * which uses stale state names — see `RECLAMO_ESTADOS` below).
 *
 * NOTE vs `anulacionesSchema.ts`: `ReclamosRead` has NO
 * `fecha_retencion_hasta` and NO `uuid_usuario` — confirmed from the
 * real ORM model, deliberately NOT added here.
 *
 * NOTE on `tipo_reclamable`: the real polymorphic discriminator
 * (`_POLYMORPHIC_TARGETS` + the Pydantic `Literal` on the BE) allows
 * EXACTLY `ingreso | salida | factura`. A 4th `subscripcion` category
 * sometimes mentioned in plain-language task descriptions does NOT
 * exist server-side -- do not add it here.
 */
import { z } from 'zod';

/**
 * Real `STATE_MACHINES['reclamo']` vocabulary
 * (`backend/packages/parkos_core/src/parkos_core/repo/workflow.py`).
 *
 * DRIFT WARNING: `plan.md`'s prose describes
 * `abierto -> en_revision -> resuelto|rechazado`, which is WRONG / stale.
 * Use ONLY these real names.
 */
export const RECLAMO_ESTADOS = ['recibido', 'en_investigacion', 'resuelto', 'rechazado'] as const;
export type ReclamoEstado = (typeof RECLAMO_ESTADOS)[number];

/**
 * Polymorphic discriminator for what's being reclamado. EXACTLY 3
 * values server-side -- see module docblock re: `subscripcion`.
 */
export const RECLAMO_TIPOS = ['ingreso', 'salida', 'factura'] as const;
export type ReclamoTipo = (typeof RECLAMO_TIPOS)[number];

export const reclamoReadSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  tipo_reclamable: z.enum(RECLAMO_TIPOS).nullable(),
  uuid_reclamable: z.string().uuid().nullable(),
  motivo: z.string().nullable(),
  uuid_reclamo_padre: z.string().uuid().nullable(),
  timestamp_evento: z.string().nullable(),
  vigente_desde: z.string().nullable(),
  vigente_hasta: z.string().nullable(),
  estado: z.enum(RECLAMO_ESTADOS).nullable(),
});
export type ReclamoRead = z.infer<typeof reclamoReadSchema>;

export const reclamosListResponseSchema = z.object({
  items: z.array(reclamoReadSchema),
  next_cursor: z.string().nullable(),
});
export type ReclamosListResponse = z.infer<typeof reclamosListResponseSchema>;

/** Only `cursor`/`limit` exist server-side for this list. */
export interface ReclamosListQuery {
  limit: number;
  cursor?: string;
}

/**
 * react-hook-form + zodResolver input for the transition modal.
 * `motivo` mandatory + non-blank, mirrors `alertaDescartarFormSchema`.
 */
export const reclamoTransicionFormSchema = z.object({
  motivo: z.string().trim().min(1, 'El motivo es obligatorio.'),
});
export type ReclamoTransicionFormInput = z.infer<typeof reclamoTransicionFormSchema>;

/**
 * Legal destination states for a given TIP `estado`. Client-side UX only
 * -- the backend remains the sole source of truth (409 `illegal_transition`
 * on a race).
 */
export const RECLAMO_TRANSICIONES: Record<ReclamoEstado, readonly ReclamoEstado[]> = {
  recibido: ['en_investigacion'],
  en_investigacion: ['resuelto', 'rechazado'],
  resuelto: [],
  rechazado: [],
};
