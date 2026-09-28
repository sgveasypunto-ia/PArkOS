/**
 * `configuracionToleranciasSchema.ts` — Zod schemas for the admin
 * Tolerancias CRUD UI (PR-D).
 *
 * Mirrors `backend/.../schemas/configuracion.py::ConfiguracionToleranciasCreate/Read`.
 *
 * The `uuid_sucursal` is optional: NULL writes the global default
 * (one row, ``uuid_sucursal IS NULL``); a non-null value writes the
 * per-branch override. The custom ``/efectiva?uuid_sucursal=...`` route
 * resolves the per-branch override OR the global default.
 *
 * ``tolerancia_efectivo`` and ``tolerancia_datafono`` are
 * ``Numeric(18,4)`` server-side. We coerce to string for the wire
 * format and use ``Decimal`` for the form (the form layer renders
 * via i18n's number formatting).
 */
import { z } from 'zod';

const nullableUuid = z.string().uuid().nullable();

const decimalString = z
  .union([z.string(), z.number()])
  .transform((v) => (typeof v === 'number' ? v.toString() : v))
  .refine((v) => /^-?\d+(\.\d+)?$/.test(v), {
    message: 'Debe ser un número decimal válido',
  });

export const configuracionToleranciasCreateSchema = z.object({
  uuid_sucursal: nullableUuid,
  tolerancia_efectivo: decimalString.refine((v) => Number(v) >= 0, {
    message: 'La tolerancia de efectivo debe ser >= 0',
  }),
  tolerancia_datafono: decimalString.refine((v) => Number(v) >= 0, {
    message: 'La tolerancia de datáfono debe ser >= 0',
  }),
});

export type ConfiguracionToleranciasCreateInput = z.infer<
  typeof configuracionToleranciasCreateSchema
>;

export const configuracionToleranciasUpdateSchema =
  configuracionToleranciasCreateSchema;

export type ConfiguracionToleranciasUpdateInput = z.infer<
  typeof configuracionToleranciasUpdateSchema
>;

export const configuracionToleranciasReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  tolerancia_efectivo: z.string().nullable(),
  tolerancia_datafono: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type ConfiguracionTolerancias = z.infer<
  typeof configuracionToleranciasReadSchema
>;

export const configuracionToleranciasReadListEnvelopeSchema = z.object({
  items: z.array(configuracionToleranciasReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type ConfiguracionToleranciasReadListEnvelope = z.infer<
  typeof configuracionToleranciasReadListEnvelopeSchema
>;
