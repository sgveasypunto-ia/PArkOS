/**
 * `tarifaSchema.ts` — Zod schemas for the admin Tarifa CRUD UI (PR-D).
 *
 * Mirrors the backend `schemas/empresa.py::TarifasSucursalCreate` /
 * `TarifasSucursalUpdate` / `TarifasSucursalRead` shape, plus the
 * `by-key/history` list endpoint that PR-C added
 * (`GET /api/v1/empresa/tarifas-sucursal/by-key`).
 *
 * Decimal fields use Zod's `union([z.string(), z.number()])` because the
 * backend serializes `Numeric(18,4)` as a JSON string (`"1500.0000"`).
 * The `coerce.number()` decorator normalises both inputs to a `number`
 * before validation; the helper `.decimalFromString` in the form layer
 * (PR-D-ui-tarifas-cupos) re-stringifies on submit so the wire format
 * stays consistent with what the backend expects.
 *
 * No HTTP client lives here; that lives in `tarifasApi.ts`.
 */
import { z } from 'zod';

const nullableUuid = z.string().uuid().nullable();

const decimalString = z
  .union([z.string(), z.number()])
  .transform((v) => (typeof v === 'number' ? v.toString() : v))
  .refine((v) => /^-?\d+(\.\d+)?$/.test(v), {
    message: 'Debe ser un número decimal válido',
  });

export const tarifaCreateSchema = z.object({
  uuid_sucursal: nullableUuid,
  uuid_tipo_vehiculo: nullableUuid,
  uuid_tipo_tarifa: nullableUuid,
  valor: z
    .union([decimalString, z.null()])
    .refine((v) => v === null || Number(v) > 0, {
      message: 'El valor debe ser mayor a 0',
    }),
  valor_plena: z
    .union([decimalString, z.null()])
    .refine((v) => v === null || Number(v) >= 0, {
      message: 'El valor plena debe ser >= 0',
    }),
  vigente_desde: z
    .string()
    .datetime({ offset: true }),
});

export type TarifaCreateInput = z.infer<typeof tarifaCreateSchema>;

export const tarifaUpdateSchema = tarifaCreateSchema;

export type TarifaUpdateInput = z.infer<typeof tarifaUpdateSchema>;

export const tarifaReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_tipo_vehiculo: z.string().uuid().nullable(),
  uuid_tipo_tarifa: z.string().uuid().nullable(),
  valor: z.string().nullable(),
  valor_plena: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type Tarifa = z.infer<typeof tarifaReadSchema>;

export const tarifaReadListEnvelopeSchema = z.object({
  items: z.array(tarifaReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type TarifaReadListEnvelope = z.infer<typeof tarifaReadListEnvelopeSchema>;

export const tarifaOverlapErrorSchema = z.object({
  detail: z.object({
    error: z.literal('tarifa_overlap'),
    conflicting_uuid: z.string().uuid(),
    conflicting_vigente_desde: z.string().nullable(),
    conflicting_vigente_hasta: z.string().nullable(),
  }),
});

export const tarifaSucursalInmutableErrorSchema = z.object({
  detail: z.object({
    error: z.literal('sucursal_inmutable'),
    uuid: z.string().uuid(),
    existing_sucursal: z.string().uuid(),
    attempted_sucursal: z.string().uuid(),
  }),
});
