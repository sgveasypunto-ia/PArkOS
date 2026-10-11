/**
 * `cupoSchema.ts` — Zod schemas for the admin Cupo (cantidad-vehiculos-
 * sucursal) CRUD UI (PR-D).
 *
 * Mirrors `backend/.../schemas/empresa.py::CantidadVehiculosSucursalCreate`
 * / `Update` / `Read`. The POST/PUT endpoints added in PR-C v2 include
 * two guards that surface typed errors to the UI:
 *
 *   - 409 ``cantidad_overlap`` — bi-temporal window collides with another
 *     open row for the same ``(uuid_sucursal, uuid_tipo_vehiculo)``.
 *   - 422 ``capacidad_insuficiente`` (BR2, HU-F14.4) — the new
 *     ``cantidad`` is below ``ocupado_actual`` (currently-active
 *     ``ingreso`` rows for the tipo); the operator must close those
 *     ``ingreso`` first.
 *   - 422 ``sucursal_inmutable`` — same as tarifas.
 *
 * ``cantidad`` is an integer column; we validate as ``z.number().int()``
 * with a server-side bound of 0 (the canonical "disable this tipo"
 * option in lieu of a DELETE).
 *
 * Datetime wire contract: post-Commit-3 the backend emits ISO 8601
 * with the ``Z`` suffix (or any ``±HH:MM`` offset for already-aware
 * columns). The read schemas use :func:`utcDateTime` to defensively
 * accept the legacy naive shape (``"2026-10-09T22:24:00"``) during
 * the rollout window and normalize it to ``...Z`` so downstream code
 * (the form, the boundary check, ``isAtOrBefore``) sees a single
 * shape. The transformation is invisible to the operator — the
 * form's ``parseApiUtc`` would do the same thing in JavaScript.
 */
import { z } from 'zod';

const nullableUuid = z.string().uuid().nullable();

/**
 * Accepts a Zod datetime string and normalizes the legacy naive form
 * (no offset) to the canonical ``Z`` suffix. Post-Commit-3 every
 * datetime the backend emits already has a suffix, so the normalize
 * step is a no-op — but during the rollout window, when the front
 * is deployed before the backend, we still parse the legacy payload
 * correctly instead of failing the read.
 */
const utcDateTime = z
  .string()
  .transform((value) =>
    /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`,
  )
  .pipe(z.string().datetime({ offset: true }));

export const cupoCreateSchema = z.object({
  uuid_sucursal: nullableUuid,
  uuid_tipo_vehiculo: nullableUuid,
  cantidad: z
    .union([z.number().int().min(0, 'La cantidad debe ser >= 0'), z.null()]),
  vigente_desde: utcDateTime,
});

export type CupoCreateInput = z.infer<typeof cupoCreateSchema>;

export const cupoUpdateSchema = cupoCreateSchema;

export type CupoUpdateInput = z.infer<typeof cupoCreateSchema>;

export const cupoReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_tipo_vehiculo: z.string().uuid().nullable(),
  cantidad: z.number().int().nullable(),
  vigente_desde: utcDateTime,
  vigente_hasta: utcDateTime.nullable(),
  estado: z.string(),
  created_at: utcDateTime,
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type Cupo = z.infer<typeof cupoReadSchema>;

export const cupoReadListEnvelopeSchema = z.object({
  items: z.array(cupoReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type CupoReadListEnvelope = z.infer<typeof cupoReadListEnvelopeSchema>;

/** `GET /cantidad-vehiculos-sucursal/by-key` returns a bare JSON array
 * (`response_model=list[CantidadVehiculosSucursalRead]`, not the
 * paginated `{items, next_cursor}` envelope the plain list endpoint
 * uses). Same shape bug as tarifas's by-key -- see tarifaSchema.ts. */
export const cupoReadArraySchema = z.array(cupoReadSchema);

export const cupoOverlapErrorSchema = z.object({
  detail: z.object({
    error: z.literal('cantidad_overlap'),
    conflicting_uuid: z.string().uuid(),
    conflicting_vigente_desde: z.string().nullable(),
    conflicting_vigente_hasta: z.string().nullable(),
  }),
});

export const cupoBajoIngresosErrorSchema = z.object({
  detail: z.object({
    error: z.literal('capacidad_insuficiente'),
    tipo: z.string().nullable(),
    ocupado_actual: z.number().int(),
    solicitado: z.number().int(),
  }),
});

export const cupoSucursalInmutableErrorSchema = z.object({
  detail: z.object({
    error: z.literal('sucursal_inmutable'),
    uuid: z.string().uuid(),
    existing_sucursal: z.string().uuid(),
    attempted_sucursal: z.string().uuid(),
  }),
});
