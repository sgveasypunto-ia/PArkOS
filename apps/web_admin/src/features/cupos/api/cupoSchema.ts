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
 */
import { z } from 'zod';

const nullableUuid = z.string().uuid().nullable();

export const cupoCreateSchema = z.object({
  uuid_sucursal: nullableUuid,
  uuid_tipo_vehiculo: nullableUuid,
  cantidad: z
    .union([z.number().int().min(0, 'La cantidad debe ser >= 0'), z.null()]),
  vigente_desde: z
    .string()
    .datetime({ offset: true }),
});

export type CupoCreateInput = z.infer<typeof cupoCreateSchema>;

export const cupoUpdateSchema = cupoCreateSchema;

export type CupoUpdateInput = z.infer<typeof cupoUpdateSchema>;

export const cupoReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_tipo_vehiculo: z.string().uuid().nullable(),
  cantidad: z.number().int().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type Cupo = z.infer<typeof cupoReadSchema>;

export const cupoReadListEnvelopeSchema = z.object({
  items: z.array(cupoReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type CupoReadListEnvelope = z.infer<typeof cupoReadListEnvelopeSchema>;

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
