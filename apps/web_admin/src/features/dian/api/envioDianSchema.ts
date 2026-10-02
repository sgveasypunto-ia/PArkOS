/**
 * `envioDianSchema.ts` — Zod schemas + TS types for HU-F20.5 "monitor de
 * envíos DIAN" (web_admin).
 *
 * Wire shapes mirror the BE 1:1, verified against
 * `backend/packages/parkos_core/src/parkos_core/dian/cloud_router.py`
 * and `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py`
 * (the actual `EnvioDianRead` class — `schemas/dian.py` is a pure
 * re-export layer, see that module's docblock):
 *
 *   - `GET /api/v1/envio-dian?uuid_sucursal=&estado=&cursor=&limit=` —
 *     cursor-paginated `{items: EnvioDianRead[], next_cursor: string|null}`,
 *     same envelope every other list endpoint in this repo uses.
 *   - `estado` domain: per `cloud_router.py::_ENVIO_DIAN_ESTADOS`, the
 *     UNION of `repo.workflow.STATE_MACHINES['envio_dian']` keys
 *     (`pendiente|enviado|ack|error`) and `dian.cloud.dispatcher`'s
 *     `ESTADO_*` constants (`aceptado|rechazado|timeout|en_proceso|error`)
 *     — 8 distinct values total. This is DRIFT vs. plan.md's HU-F13.4 BR2
 *     (`pendiente|enviado|aceptado|rechazado`), which actually describes
 *     `schemas.facturacion.FacturaDisplayFE.estado_dian` (a simplified FE
 *     projection), not this raw table's real domain — see the long
 *     comment block directly above `_ENVIO_DIAN_ESTADOS` in
 *     `cloud_router.py` for the full rationale (confirmed against every
 *     writer in the codebase, not assumed).
 *   - There is NO `GET /envio-dian/{uuid}` single-item read and NO
 *     `/history` endpoint for this table (confirmed by reading the full
 *     file — only the 6 routes in that module's docstring exist). Unlike
 *     `prod.alerta` (`workflows_alerta.py`, which reuses the generic
 *     `make_router` factory and gets a single-item GET for free), the
 *     cloud-only `envio_dian`/`validacion_evento` routes are hand-built
 *     and only ship the list + create endpoints (REQ-X3 boundary —
 *     `workflows.py` must not mount them). `useEnvioDianChain.ts`
 *     documents the client-side workaround this forces.
 *   - The REAL "retry" endpoint is `POST
 *     /api/v1/facturacion/factura-electronica/{uuid}/reintentar`
 *     (`api/v1/facturacion.py::retry_envio_dian`, HU-F1.10) — NOT
 *     `POST /api/v1/envio-dian` with a client-supplied `uuid_envio_padre`.
 *     See `envioDianApi.ts`'s docblock for the full drift rationale.
 */
import { z } from 'zod';

/** `cloud_router.py::_ENVIO_DIAN_ESTADOS` — the real, confirmed domain. */
export const ENVIO_DIAN_ESTADOS = [
  'pendiente',
  'enviado',
  'ack',
  'error',
  'aceptado',
  'rechazado',
  'timeout',
  'en_proceso',
] as const;
export type EnvioDianEstado = (typeof ENVIO_DIAN_ESTADOS)[number];

/** `schemas/workflows.py::EnvioDianRead` (re-exported via `schemas/dian.py`). */
export const envioDianReadSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_factura_electronica: z.string().uuid().nullable(),
  uuid_resolucion_facturacion: z.string().uuid().nullable(),
  payload: z.record(z.unknown()).nullable(),
  respuesta_proveedor: z.record(z.unknown()).nullable(),
  cufe: z.string().nullable(),
  uuid_envio_padre: z.string().uuid().nullable(),
  timestamp_evento: z.string().nullable(),
  vigente_desde: z.string().nullable(),
  vigente_hasta: z.string().nullable(),
  // Nullable (not the narrow `ENVIO_DIAN_ESTADOS` enum): the BE column
  // itself is `str | None` (`EnvioDianRead.estado: str | None`); modeling
  // it as a free-form nullable string instead of the enum avoids a zod
  // parse crash if an unexpected/legacy value ever lands on the wire
  // (defense in depth, same reasoning `alertaDetailReadSchema` uses for
  // `severity`).
  estado: z.string().nullable(),
});
export type EnvioDianRead = z.infer<typeof envioDianReadSchema>;

export const envioDianReadListSchema = z.object({
  items: z.array(envioDianReadSchema),
  next_cursor: z.string().nullable(),
});
export type EnvioDianReadList = z.infer<typeof envioDianReadListSchema>;

/** Query shape for `GET /api/v1/envio-dian`. */
export interface EnvioDianListQuery {
  uuid_sucursal?: string;
  estado?: EnvioDianEstado;
  cursor?: string;
  limit: number;
}

/**
 * `schemas/facturacion.py::EnvioDianRetryRead` — response of
 * `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar`.
 *
 * `uuid_envio_padre` is modeled nullable here even though the Python
 * schema declares it as a required `UUID`: the handler's defensive
 * "empty chain" branch (`retry_envio_dian`, `chain_tip is None`) sets
 * `uuid_envio_padre = None` with a `type: ignore[assignment]` — a
 * pre-existing BE inconsistency, not something this FE-only slice
 * should paper over by assuming the stricter type always holds.
 */
export const envioDianRetryReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_factura_electronica: z.string().uuid(),
  estado: z.literal('pendiente'),
  timestamp_evento: z.string(),
  uuid_envio_padre: z.string().uuid().nullable(),
});
export type EnvioDianRetryRead = z.infer<typeof envioDianRetryReadSchema>;
