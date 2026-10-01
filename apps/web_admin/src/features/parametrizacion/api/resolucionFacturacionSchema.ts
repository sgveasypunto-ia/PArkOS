/**
 * `resolucionFacturacionSchema.ts` — Zod schemas for the HU-F15.3
 * "Resoluciones" tab (resolución DIAN create + read-only consecutivo).
 *
 * LOCATION NOTE: the master spec placed this file at
 * `src/lib/schemas/resolucionFacturacion.ts`, but that directory does not
 * exist in this repo — every sibling schema (`tarifaSchema.ts`,
 * `cupoSchema.ts`, `cambiarPasswordSchema.ts`) lives co-located with its
 * feature under `features/<feature>/api/`. This file follows that real
 * repo convention instead of the literal spec path (decision already taken,
 * not reopened here).
 *
 * Mirrors `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py`:
 *   - `ResolucionFacturacionRead` -> `resolucionFacturacionReadSchema`
 *   - `ResolucionFacturacionCreate` / `ResolucionFacturacionUpdate` (same
 *     shape) -> `resolucionFacturacionCreateSchema`
 *   - `ResolucionFacturacionConsecutivoActual` ->
 *     `resolucionFacturacionConsecutivoActualSchema`
 *
 * REQ-X3 drift note: the master spec also describes two extra 422 guards —
 * `rango_hasta > rango_desde` and no two resoluciones vigentes sharing
 * `prefijo` for the same sucursal. NEITHER applies here: per
 * `ResolucionFacturacionCreate`'s backend docstring, `prefijo`,
 * `rango_desde` and `rango_hasta` are server-assigned and blocked
 * (`extra='forbid'`) from the client payload, so there is nothing in this
 * form to validate against those two invariants — they belong to whatever
 * out-of-band process assigns the DIAN range. Only the third guard,
 * `fecha_fin_vigencia > fecha_inicio_vigencia`, applies to fields the
 * client actually sends, so only that one is reproduced below.
 */
import { z } from 'zod';

/** `YYYY-MM-DD`, matching `<input type="date">`'s native value and the
 * backend's `date` (not `datetime`) field type — no datetime-local
 * conversion helper needed here, unlike `TarifaForm.tsx`'s
 * `isoToDatetimeLocal`/`datetimeLocalToIso` (those exist because tarifas
 * use `datetime`, not plain `date`). */
const dateOnly = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, 'Debe ser una fecha válida (AAAA-MM-DD)');

export const resolucionFacturacionCreateSchema = z
  .object({
    uuid_sucursal: z.string().uuid(),
    numero_resolucion: z
      .string()
      .min(1, 'El número de resolución es obligatorio')
      .max(64, 'Máximo 64 caracteres'),
    fecha_resolucion: dateOnly,
    fecha_inicio_vigencia: dateOnly,
    fecha_fin_vigencia: dateOnly,
  })
  .superRefine((val, ctx) => {
    if (val.fecha_fin_vigencia <= val.fecha_inicio_vigencia) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['fecha_fin_vigencia'],
        message: 'fecha_fin_vigencia debe ser posterior a fecha_inicio_vigencia',
      });
    }
  });

export type ResolucionFacturacionCreateInput = z.infer<
  typeof resolucionFacturacionCreateSchema
>;

// `ResolucionFacturacionUpdate` is byte-for-byte the same shape as Create
// on the backend (same docstring note on why only the vigencia guard
// applies) — mirrors `tarifaUpdateSchema = tarifaBackendCreateSchema`.
export const resolucionFacturacionUpdateSchema = resolucionFacturacionCreateSchema;
export type ResolucionFacturacionUpdateInput = ResolucionFacturacionCreateInput;

export const resolucionFacturacionReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  numero_resolucion: z.string().nullable(),
  prefijo: z.string().nullable(),
  rango_desde: z.number().nullable(),
  rango_hasta: z.number().nullable(),
  fecha_resolucion: z.string().nullable(),
  fecha_inicio_vigencia: z.string().nullable(),
  fecha_fin_vigencia: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type ResolucionFacturacion = z.infer<typeof resolucionFacturacionReadSchema>;

export const resolucionFacturacionReadListEnvelopeSchema = z.object({
  items: z.array(resolucionFacturacionReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type ResolucionFacturacionReadListEnvelope = z.infer<
  typeof resolucionFacturacionReadListEnvelopeSchema
>;

export const resolucionFacturacionConsecutivoActualSchema = z.object({
  consecutivo_actual: z.number(),
  rango_hasta: z.number().nullable(),
  restantes: z.number().nullable(),
  agotandose: z.boolean(),
});

export type ResolucionFacturacionConsecutivoActual = z.infer<
  typeof resolucionFacturacionConsecutivoActualSchema
>;

/**
 * Typed error for the `fecha_fin_vigencia > fecha_inicio_vigencia` 422
 * guard. Unlike `tarifaOverlapErrorSchema` (which parses a bespoke typed
 * body the backend built for that guard), the vigencia guard here is a
 * plain pydantic `model_validator(mode="after")` raising `ValueError` —
 * FastAPI reports that through its STANDARD validation envelope
 * (`{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`), so this
 * schema parses THAT generic shape instead of inventing a bespoke one.
 */
export const resolucionFacturacionValidationErrorSchema = z.object({
  detail: z.array(
    z.object({
      loc: z.array(z.union([z.string(), z.number()])),
      msg: z.string(),
      type: z.string(),
    }),
  ),
});
