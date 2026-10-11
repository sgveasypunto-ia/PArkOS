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

/** Same defensive normalize as the cupos schema — accept naive or
 *  tz-aware, output tz-aware (``Z`` appended if needed). */
const utcDateTime = z
  .string()
  .transform((value) =>
    /[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`,
  )
  .pipe(z.string().datetime({ offset: true }));

const decimalString = z
  .union([z.string(), z.number()])
  .transform((v) => (typeof v === 'number' ? v.toString() : v))
  .refine((v) => /^-?\d+(\.\d+)?$/.test(v), {
    message: 'Debe ser un número decimal válido',
  });

export const tarifaCreateSchema = z.object({
  uuid_sucursal: nullableUuid,
  uuid_tipo_vehiculo: nullableUuid,
  // Required on CREATE: tarifa cells must have every modalidad priced.
  // Empty/blank inputs are rejected with "Requerido" -- the page
  // used to convert null to '0' and send it, the backend rightly
  // rejected it, and the operator saw a row with only one modalidad
  // configured and a raw-Zod-JSON alert. The strict refine now blocks
  // the submit at the form layer with an inline message; PR2's batch
  // endpoint is the new happy path (one POST, 4 items, atomic).
  //
  // On EDIT, the operator may leave a modalidad blank to indicate
  // "I am not changing this one" -- the form splits the submit into
  // a per-modalidad PUT for each present valor_* and skips the blank
  // ones. The pre-populated valor_* for an existing modalidad is
  // always a valid decimal string, so the > 0 check still applies.
  // The ``mode`` field flips the behavior:
  //   - "create" (default) -- the null branch is invalid; "Requerido".
  //   - "edit" -- the null branch is allowed (skips the modalidad);
  //     the > 0 check still applies to non-null values.
  valor_hora: z
    .union([decimalString, z.null(), z.undefined()])
    .transform((v) => (v === undefined || v === '' ? null : v))
    .refine((v) => v !== null, { message: 'Requerido' })
    .refine((v) => v === null || Number(v) > 0, {
      message: 'El valor hora debe ser mayor a 0',
    }),
  valor_fraccion: z
    .union([decimalString, z.null(), z.undefined()])
    .transform((v) => (v === undefined || v === '' ? null : v))
    .refine((v) => v !== null, { message: 'Requerido' })
    .refine((v) => v === null || Number(v) > 0, {
      message: 'El valor fracción debe ser mayor a 0',
    }),
  valor_plena: z
    .union([decimalString, z.null(), z.undefined()])
    .transform((v) => (v === undefined || v === '' ? null : v))
    .refine((v) => v !== null, { message: 'Requerido' })
    .refine((v) => v === null || Number(v) >= 0, {
      message: 'El valor plena debe ser >= 0',
    }),
  valor_nocturna: z
    .union([decimalString, z.null(), z.undefined()])
    .transform((v) => (v === undefined || v === '' ? null : v))
    .refine((v) => v !== null, { message: 'Requerido' })
    .refine((v) => v === null || Number(v) > 0, {
      message: 'El valor nocturna debe ser mayor a 0',
    }),
  vigente_desde: utcDateTime,
});

/**
 * Edit-mode schema: same shape as ``tarifaCreateSchema`` but allows
 * ``valor_*`` to be null/undefined/empty (the operator may leave a
 * modalidad blank to indicate "I am not changing this one"). The
 * per-row value > 0 (or >= 0 for ``plena``) still applies when the
 * operator types something.
 */
const tarifaEditRefine = (): ((v: string | null) => boolean) => (v) =>
  v === null || Number(v) > 0;

export const tarifaEditSchema = z.object({
  uuid_sucursal: nullableUuid,
  uuid_tipo_vehiculo: nullableUuid,
  valor_hora: z
    .union([decimalString, z.null(), z.undefined()])
    .transform((v) => (v === undefined || v === '' ? null : v))
    .refine(tarifaEditRefine(), {
      message: 'El valor hora debe ser mayor a 0',
    }),
  valor_fraccion: z
    .union([decimalString, z.null(), z.undefined()])
    .transform((v) => (v === undefined || v === '' ? null : v))
    .refine(tarifaEditRefine(), {
      message: 'El valor fracción debe ser mayor a 0',
    }),
  valor_plena: z
    .union([decimalString, z.null(), z.undefined()])
    .transform((v) => (v === undefined || v === '' ? null : v))
    .refine((v) => v === null || Number(v) >= 0, {
      message: 'El valor plena debe ser >= 0',
    }),
  valor_nocturna: z
    .union([decimalString, z.null(), z.undefined()])
    .transform((v) => (v === undefined || v === '' ? null : v))
    .refine(tarifaEditRefine(), {
      message: 'El valor nocturna debe ser mayor a 0',
    }),
  vigente_desde: utcDateTime,
});

export type TarifaCreateInput = z.infer<typeof tarifaCreateSchema>;

// Schema for the wire payload sent to the backend (one POST per
// modalidad). Mirrors `backend/.../schemas/empresa.py:283
// TarifasSucursalCreate` exactly: ``uuid_tipo_tarifa`` REQUIRED,
// ``valor`` > 0, ``valor_plena`` >= 0. The page-side ``onSubmit``
// (``Tarifas.tsx``) splits the 4-input form into 4 calls to
// ``createTarifa(input)`` where each input carries one
// (uuid_tipo_tarifa, valor, valor_plena) tuple.
export const tarifaBackendCreateSchema = z.object({
  uuid_sucursal: nullableUuid,
  uuid_tipo_vehiculo: z.string().uuid(),
  uuid_tipo_tarifa: z.string().uuid(),
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
  vigente_desde: utcDateTime,
});

export type TarifaBackendCreateInput = z.infer<typeof tarifaBackendCreateSchema>;

export const tarifaUpdateSchema = tarifaBackendCreateSchema;

export type TarifaUpdateInput = TarifaBackendCreateInput;

export const tarifaReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_tipo_vehiculo: z.string().uuid().nullable(),
  uuid_tipo_tarifa: z.string().uuid().nullable(),
  valor: z.string().nullable(),
  valor_plena: z.string().nullable(),
  vigente_desde: utcDateTime,
  vigente_hasta: utcDateTime.nullable(),
  estado: z.string(),
  created_at: utcDateTime,
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type Tarifa = z.infer<typeof tarifaReadSchema>;

export const tarifaReadListEnvelopeSchema = z.object({
  items: z.array(tarifaReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type TarifaReadListEnvelope = z.infer<typeof tarifaReadListEnvelopeSchema>;

/** `GET /tarifas-sucursal/by-key` returns a bare JSON array
 * (`response_model=list[TarifasSucursalRead]`, not the paginated
 * `{items, next_cursor}` envelope the plain list endpoint uses). */
export const tarifaReadArraySchema = z.array(tarifaReadSchema);

export const tarifaOverlapErrorSchema = z.object({
  detail: z.object({
    error: z.literal('tarifa_overlap'),
    conflicting_uuid: z.string().uuid(),
    conflicting_vigente_desde: utcDateTime.nullable(),
    conflicting_vigente_hasta: utcDateTime.nullable(),
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

// ---------------------------------------------------------------------------
// Batch schemas (HU-tarifas-batch, PR2 frontend)
// ---------------------------------------------------------------------------

/** One (uuid_tipo_tarifa, valor, valor_plena) triple in a batch.
 *  Mirrors the backend ``TarifasSucursalBatchItemCreate``.
 *  ``valor > 0`` is REQUIRED (no null/undefined/empty) -- the operator
 *  UI requires every modalidad, and the form layer's RHF refine
 *  guarantees this before the page-side ``onSubmit`` ever builds the
 *  payload. ``valor_plena`` stays optional and ``>= 0`` (the only
 *  modality where 0 is meaningful: "no full-day surcharge"). */
export const tarifaBatchItemSchema = z.object({
  uuid_tipo_tarifa: z.string().uuid(),
  valor: decimalString.refine((v) => Number(v) > 0, {
    message: 'El valor debe ser mayor a 0',
  }),
  valor_plena: z
    .union([decimalString, z.null(), z.undefined()])
    .transform((v) => (v === undefined || v === '' ? null : v))
    .refine((v) => v === null || Number(v) >= 0, {
      message: 'El valor plena debe ser >= 0',
    })
    .optional()
    .nullable(),
});

export type TarifaBatchItem = z.infer<typeof tarifaBatchItemSchema>;

/** Wire payload to ``POST /api/v1/empresa/tarifas-sucursal/batch``.
 *  Mirrors the backend ``TarifasSucursalBatchCreate`` (min/max 1..4
 *  items, atomic on the server side). */
export const tarifaBatchCreateSchema = z.object({
  uuid_sucursal: nullableUuid,
  uuid_tipo_vehiculo: z.string().uuid(),
  vigente_desde: utcDateTime.optional().nullable(),
  items: z.array(tarifaBatchItemSchema).min(1).max(4),
});

export type TarifaBatchCreateInput = z.infer<typeof tarifaBatchCreateSchema>;

/** Response shape: ``{ items: Tarifa[], next_cursor: null }`` (the batch
 *  endpoint uses the envelope, not the bare array). */
export const tarifaBatchResponseSchema = z.object({
  items: z.array(tarifaReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type TarifaBatchResponse = z.infer<typeof tarifaBatchResponseSchema>;

