/**
 * `tipoTarifaSchema.ts` — Zod schemas for the admin TipoTarifa CRUD UI
 * (PR-D).
 *
 * Same shape as TipoVehiculo (single `tipo` business column). The
 * canonical seed includes `hora | fraccion | plena | nocturna` (lowercase).
 */
import { z } from 'zod';

export const tipoTarifaCreateSchema = z.object({
  tipo: z
    .string()
    .min(1, 'El tipo es obligatorio')
    .max(64, 'Máximo 64 caracteres'),
});

export type TipoTarifaCreateInput = z.infer<typeof tipoTarifaCreateSchema>;

export const tipoTarifaUpdateSchema = tipoTarifaCreateSchema;

export type TipoTarifaUpdateInput = z.infer<typeof tipoTarifaUpdateSchema>;

export const tipoTarifaReadSchema = z.object({
  uuid: z.string().uuid(),
  tipo: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type TipoTarifa = z.infer<typeof tipoTarifaReadSchema>;

export const tipoTarifaReadListEnvelopeSchema = z.object({
  items: z.array(tipoTarifaReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type TipoTarifaReadListEnvelope = z.infer<
  typeof tipoTarifaReadListEnvelopeSchema
>;
