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
 * Numbering: `prefijo`, `rango_desde` and `rango_hasta` ARE client-writable
 * (the backend `ResolucionFacturacionCreate`/`Update` accept them and are the
 * source of the invoice numbering the branch emits with — electronic invoice
 * emission fails with `resolucion_sin_prefijo` when they are missing). The
 * form requires all three; the backend keeps them optional only so legacy
 * rows stay editable. Rules mirror the backend: prefijo 1-4 alphanumeric
 * (upper-cased), rango_desde >= 1, rango_hasta >= rango_desde.
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

/** Tope de DIAN para un rango de numeración (10 dígitos); espeja el backend. */
export const RANGO_MAXIMO = 9_999_999_999;

/** Largo máximo del prefijo de numeración DIAN. */
export const PREFIJO_MAX_LENGTH = 4;

/** `<input type="number">` entrega string; vacío debe leerse como "falta". */
const rangoEntero = (etiqueta: string) =>
  z.preprocess(
    (v) => {
      if (v === '' || v === null || v === undefined) return undefined;
      return typeof v === 'string' ? Number(v) : v;
    },
    z
      .number({
        required_error: `${etiqueta} es obligatorio`,
        invalid_type_error: `${etiqueta} debe ser un número`,
      })
      .int(`${etiqueta} debe ser un número entero`)
      .min(1, `${etiqueta} debe ser mayor o igual a 1`)
      .max(RANGO_MAXIMO, `${etiqueta} no puede superar ${RANGO_MAXIMO}`),
  );

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
    prefijo: z
      .string()
      .trim()
      .min(1, 'El prefijo es obligatorio')
      .max(PREFIJO_MAX_LENGTH, `Máximo ${PREFIJO_MAX_LENGTH} caracteres`)
      .regex(/^[A-Za-z0-9]+$/, 'Solo letras y números, sin espacios ni símbolos')
      .transform((v) => v.toUpperCase()),
    rango_desde: rangoEntero('El rango inicial'),
    rango_hasta: rangoEntero('El rango final'),
  })
  .superRefine((val, ctx) => {
    if (val.fecha_fin_vigencia <= val.fecha_inicio_vigencia) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['fecha_fin_vigencia'],
        message: 'fecha_fin_vigencia debe ser posterior a fecha_inicio_vigencia',
      });
    }
    if (val.rango_hasta < val.rango_desde) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['rango_hasta'],
        message: 'El rango final debe ser mayor o igual al rango inicial',
      });
    }
  });

/** Valores crudos del formulario: los inputs numéricos entregan string o vacío. */
export interface ResolucionFacturacionFormValues {
  uuid_sucursal: string;
  numero_resolucion: string;
  fecha_resolucion: string;
  fecha_inicio_vigencia: string;
  fecha_fin_vigencia: string;
  prefijo: string;
  rango_desde: number | '';
  rango_hasta: number | '';
}

export type ResolucionFacturacionCreateInput = z.infer<
  typeof resolucionFacturacionCreateSchema
>;

// `ResolucionFacturacionUpdate` is byte-for-byte the same shape as Create
// on the backend — mirrors `tarifaUpdateSchema = tarifaBackendCreateSchema`.
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

/** Campos de numeración a los que el servidor puede atribuir un rechazo. */
export type ResolucionNumeracionCampo = 'prefijo' | 'rango_desde' | 'rango_hasta';

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
