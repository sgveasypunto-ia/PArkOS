/**
 * `configuracionSeguridadSchema.ts` — Zod schemas for the admin
 * Seguridad CRUD UI (PR-D).
 *
 * Mirrors `backend/.../schemas/configuracion.py::ConfiguracionSeguridadCreate/Read`.
 *
 * The `dias_expiracion_password` field is on the backend schema but
 * is dead — there is no `cambiar_password` flow yet. We accept it for
 * forward compatibility but the form layer hides it (or, for PR-D,
 * the form simply surfaces the two read-by-shipping columns:
 * ``max_intentos_login`` and ``minutos_bloqueo_login``).
 *
 * The effective resolution server-side uses the
 * ``GET /configuracion-seguridad/efectiva?uuid_sucursal=…`` route
 * (T-PR4-04) — per-branch override OR global default.
 */
import { z } from 'zod';

const nullableUuid = z.string().uuid().nullable();

export const configuracionSeguridadCreateSchema = z.object({
  uuid_sucursal: nullableUuid,
  dias_expiracion_password: z
    .number()
    .int()
    .min(0)
    .nullable()
    .optional(),
  max_intentos_login: z
    .union([
      z.number().int().min(1, 'Mínimo 1 intento').max(20, 'Máximo 20 intentos'),
      z.null(),
    ]),
  minutos_bloqueo_login: z
    .union([
      z.number().int().min(1, 'Mínimo 1 minuto').max(1440, 'Máximo 1440 minutos (24h)'),
      z.null(),
    ]),
});

export type ConfiguracionSeguridadCreateInput = z.infer<
  typeof configuracionSeguridadCreateSchema
>;

export const configuracionSeguridadUpdateSchema =
  configuracionSeguridadCreateSchema;

export type ConfiguracionSeguridadUpdateInput = z.infer<
  typeof configuracionSeguridadUpdateSchema
>;

export const configuracionSeguridadReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  dias_expiracion_password: z.number().int().nullable(),
  max_intentos_login: z.number().int().nullable(),
  minutos_bloqueo_login: z.number().int().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type ConfiguracionSeguridad = z.infer<typeof configuracionSeguridadReadSchema>;

export const configuracionSeguridadReadListEnvelopeSchema = z.object({
  items: z.array(configuracionSeguridadReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type ConfiguracionSeguridadReadListEnvelope = z.infer<
  typeof configuracionSeguridadReadListEnvelopeSchema
>;
