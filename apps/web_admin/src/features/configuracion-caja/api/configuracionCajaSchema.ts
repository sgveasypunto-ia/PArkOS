/**
 * `configuracionCajaSchema.ts` — Zod schemas for `configuracion_caja`
 * (HU-F15.5, CU-13).
 *
 * Mirrors `backend/.../schemas/configuracion.py::ConfiguracionCajaCreate/Read`
 * (HU-F13.3) and follows the same shape/convention as the sibling
 * `features/configuracion-tolerancias/api/configuracionToleranciasSchema.ts`
 * (decimal-as-string wire format, `uuid_sucursal` nullable = global default).
 *
 * Deliberately colocated under `features/configuracion-caja/api/` rather
 * than `src/lib/schemas/` (the path plan.md's HU-F15.5 task table names):
 * `src/lib/schemas/` does not exist anywhere in this app — every other
 * configuracion-* feature (tolerancias, seguridad) colocates its Zod
 * schema next to its API client under `features/<feature>/api/`. This
 * file follows the real, established convention instead.
 *
 * `denominaciones_permitidas` is `list[int]` server-side (JSONB,
 * UI-validated per the model docstring) with no positivity constraint
 * in the backend Pydantic schema. HU-F15.5 explicitly asks for "array
 * de enteros positivos", so that constraint is enforced HERE, stricter
 * than the backend — a 0 or negative denomination would be accepted by
 * the API but is rejected client-side before it ever reaches the wire.
 *
 * The create/update schema keeps `denominaciones_permitidas` as
 * `string[] | null` (one numeric-token string per denomination), the
 * same "string all the way through the form" convention
 * `decimalString` already uses for the two money fields: the Zod
 * output type stays whatever the `<input>` naturally edits, so
 * `useForm<ConfiguracionCajaCreateInput>` never fights the DOM. The
 * read schema (`denominaciones_permitidas: number[]`, matching the
 * backend's actual `list[int]` JSON) is the one place real numbers
 * appear; `configuracionCajaApi.ts` converts string tokens -> numbers
 * at the wire boundary right before `JSON.stringify`.
 */
import { z } from 'zod';

const nullableUuid = z.string().uuid().nullable();

const decimalString = z
  .union([z.string(), z.number()])
  .transform((v) => (typeof v === 'number' ? v.toString() : v))
  .refine((v) => /^-?\d+(\.\d+)?$/.test(v), {
    message: 'Debe ser un número decimal válido',
  });

export const REDONDEO_VALUES = ['ninguno', '100', '500', '1000'] as const;
export const redondeoSchema = z.enum(REDONDEO_VALUES);
export type Redondeo = z.infer<typeof redondeoSchema>;

const DENOMINACION_TOKEN_PATTERN = /^\d+$/;

// Refined as a WHOLE array (not per-item) so a validation failure
// attaches directly to `denominaciones_permitidas` itself — same
// pattern `base_inicial_sugerida`'s refine uses just below. A per-item
// `z.array(itemSchema.refine(...))` would instead nest the error at
// `denominaciones_permitidas[<index>]`, which RHF's `getFieldState`
// (keyed on the exact field name) would never surface via `FormMessage`.
const denominacionesPermitidasSchema = z
  .array(z.string())
  .nullable()
  .refine(
    (arr) =>
      arr === null ||
      arr.every((token) => DENOMINACION_TOKEN_PATTERN.test(token) && Number(token) > 0),
    { message: 'Cada denominación debe ser un entero positivo' },
  );

export const configuracionCajaCreateSchema = z.object({
  uuid_sucursal: nullableUuid,
  base_inicial_sugerida: z
    .union([decimalString, z.null()])
    .refine((v) => v === null || Number(v) >= 0, {
      message: 'La base inicial sugerida debe ser >= 0',
    }),
  redondeo: redondeoSchema.nullable(),
  denominaciones_permitidas: denominacionesPermitidasSchema,
});

export type ConfiguracionCajaCreateInput = z.infer<typeof configuracionCajaCreateSchema>;

export const configuracionCajaUpdateSchema = configuracionCajaCreateSchema;

export type ConfiguracionCajaUpdateInput = z.infer<typeof configuracionCajaUpdateSchema>;

export const configuracionCajaReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  base_inicial_sugerida: z.string().nullable(),
  redondeo: z.string().nullable(),
  denominaciones_permitidas: z.array(z.number()).nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type ConfiguracionCaja = z.infer<typeof configuracionCajaReadSchema>;

export const configuracionCajaReadListEnvelopeSchema = z.object({
  items: z.array(configuracionCajaReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type ConfiguracionCajaReadListEnvelope = z.infer<
  typeof configuracionCajaReadListEnvelopeSchema
>;
