/**
 * `tipoSucursalSchema.ts` — Zod schemas for the admin TipoSucursal
 * catalog read surface.
 *
 * The backend mount at `api/v1/catalogos/tipo-sucursal` is the same
 * factory-built C+Q+U as the other 9 catalogs (PR3 of the 49-table
 * plan). The admin UI does not yet expose create/update on this
 * catalog (IT-2 ships the seed via Alembic migration 0060, not via
 * CRUD); this client only reads.
 *
 * Mirror of `apps/web_admin/src/features/tipo-tarifa/api/tipoTarifaSchema.ts`
 * with `tipo` -> `codigo` (the canonical column name on the ER for
 * `tipo_sucursal`).
 */
import { z } from 'zod';

export const tipoSucursalReadSchema = z.object({
  uuid: z.string().uuid(),
  codigo: z.string().nullable(),
  nombre: z.string().nullable(),
  descripcion: z.string().nullable(),
  caracteristicas: z.unknown().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type TipoSucursal = z.infer<typeof tipoSucursalReadSchema>;

export const tipoSucursalReadListEnvelopeSchema = z.object({
  items: z.array(tipoSucursalReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type TipoSucursalReadListEnvelope = z.infer<
  typeof tipoSucursalReadListEnvelopeSchema
>;
