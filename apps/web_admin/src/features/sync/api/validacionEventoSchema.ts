/**
 * `validacionEventoSchema.ts` — Zod schemas for the HU-F19.6 "bandeja de
 * validación de eventos" tab (web_admin), mirroring the backend response
 * model verbatim (`backend/.../schemas/workflows.py::ValidacionEventoRead`,
 * consumed via `dian/cloud_router.py`'s `GET /api/v1/validacion-evento` /
 * `POST /api/v1/validacion-evento`, both already real and implemented in
 * this same worktree).
 *
 * `estado` is exactly `'pendiente' | 'validado' | 'rechazado'`
 * (`repo.workflow.STATE_MACHINES['validacion_evento']`) — NOT
 * `'recibido'`/`'observado'`, which older docs mention but no writer in
 * this codebase ever produces (`dian/cloud_router.py`'s own module-level
 * comment documents this exact drift: those two values belong to the
 * unrelated `reclamos` state machine).
 *
 * `GET /api/v1/validacion-evento` filters `WHERE vigente_hasta IS NULL`
 * server-side (cloud_router.py::_list_workflow_rows) — it ONLY ever
 * returns the CURRENT tip of each chain, never superseded historical
 * rows. There is also no `GET /validacion-evento/{uuid}` endpoint (unlike
 * `alerta`, which has one and lets `useAlertaChain` walk
 * `uuid_alerta_padre` backwards). See `ValidacionEventos.tsx`'s docblock
 * for how this shapes the per-row "historial" rendering.
 */
import { z } from 'zod';

export const VALIDACION_EVENTO_ESTADOS = ['pendiente', 'validado', 'rechazado'] as const;
export type ValidacionEventoEstado = (typeof VALIDACION_EVENTO_ESTADOS)[number];

export const validacionEventoReadSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_usuario: z.string().uuid().nullable(),
  tabla_origen: z.string().nullable(),
  uuid_registro: z.string().uuid().nullable(),
  hash_evento: z.string().nullable(),
  observaciones: z.string().nullable(),
  uuid_validacion_padre: z.string().uuid().nullable(),
  timestamp_evento: z.string().nullable(),
  vigente_desde: z.string().nullable(),
  vigente_hasta: z.string().nullable(),
  estado: z.enum(VALIDACION_EVENTO_ESTADOS).nullable(),
});
export type ValidacionEventoRead = z.infer<typeof validacionEventoReadSchema>;

export const validacionEventoListResponseSchema = z.object({
  items: z.array(validacionEventoReadSchema),
  next_cursor: z.string().nullable(),
});
export type ValidacionEventoListResponse = z.infer<typeof validacionEventoListResponseSchema>;

/**
 * Query shape for `GET /api/v1/validacion-evento`. All fields optional
 * except nothing is required — mirrors `syncSchema.ts::SyncConflictQuery`.
 * The container/hook builds the `URLSearchParams` with only the
 * non-empty fields (see `validacionEventoApi.ts::fetchValidacionEventos`).
 */
export interface ValidacionEventoListQuery {
  uuid_sucursal?: string;
  estado?: ValidacionEventoEstado;
  cursor?: string;
  limit?: number;
}

/**
 * react-hook-form + zodResolver input for `<ValidarEventoModal />`.
 * `observaciones` is mandatory + non-blank ONLY when `estado ===
 * 'rechazado'` (BE: `ValidacionEventoCreate._validar_estado_transicion`
 * — no such requirement for `'validado'`), enforced here via
 * `superRefine` since the requirement is conditional on a sibling field
 * (a plain per-field `.min(1)` can't express that).
 */
export const validarEventoFormSchema = z
  .object({
    estado: z.enum(['validado', 'rechazado']),
    observaciones: z.string(),
  })
  .superRefine((data, ctx) => {
    if (data.estado === 'rechazado' && data.observaciones.trim().length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['observaciones'],
        message: 'Las observaciones son obligatorias al rechazar.',
      });
    }
  });
export type ValidarEventoFormInput = z.infer<typeof validarEventoFormSchema>;
