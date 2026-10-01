/**
 * `tipoVehiculoSchema.ts` — Zod schemas for the admin TiposVehiculo CRUD UI
 * (PR-D).
 *
 * Mirrors `backend/.../schemas/tipos_vehiculo.py`. The catalog has a
 * single business column (``tipo``) — bi-temporal versioning columns
 * stay server-side.
 *
 * The lowercase seed convention: `commit 281bb66` seeded
 * `carro | moto | bicicleta | patineta` in lowercase. The schema does
 * not enforce lowercase at the API edge (lowercase is a convention,
 * not a DB constraint) — the form layer normalizes the input.
 */
import { z } from 'zod';

export const tipoVehiculoCreateSchema = z.object({
  tipo: z
    .string()
    .min(1, 'El tipo es obligatorio')
    .max(64, 'Máximo 64 caracteres'),
});

export type TipoVehiculoCreateInput = z.infer<typeof tipoVehiculoCreateSchema>;

export const tipoVehiculoUpdateSchema = tipoVehiculoCreateSchema;

export type TipoVehiculoUpdateInput = z.infer<typeof tipoVehiculoUpdateSchema>;

export const tipoVehiculoReadSchema = z.object({
  uuid: z.string().uuid(),
  tipo: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type TipoVehiculo = z.infer<typeof tipoVehiculoReadSchema>;

export const tipoVehiculoReadListEnvelopeSchema = z.object({
  items: z.array(tipoVehiculoReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type TipoVehiculoReadListEnvelope = z.infer<
  typeof tipoVehiculoReadListEnvelopeSchema
>;
