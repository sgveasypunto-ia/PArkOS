/**
 * `turnoSchema.ts` — Zod schemas compartidos para AbrirTurno + CerrarTurno (F3.3 — T2/T3).
 *
 * DEC-F3.3-01 + DEC-F3.3-02 + DEC-F3.3-08:
 *   - Container/Presentational split (F1.3 verbatim).
 *   - UI: `<Input type="text" inputMode="decimal">` con filtro regex
 *     numérico en onChange. El schema acepta STRING (lo que produce el
 *     input filtrado) y aplica `.transform()` a number ANTES de la
 *     validación final, así el backend recibe number pero el form
 *     nunca se rompe por el `type="number"` quirks (defaultValue=0
 *     pegado, no se puede borrar, scroll-wheels molestos en Electron).
 *   - 409 UX mapping via SesionAlreadyActiveError typed error.
 *
 * Defense in depth XR6 layer 4 contract:
 *   - Zod local (este archivo, frontend)
 *   - Backend Pydantic `SesionCreate` (F1.3) + `SesionCerrarRequest` (F1.13)
 *   - Partial unique index `prod.uq_prod_sesion_one_active_per_user` (F1.3)
 *   - 6 new REQ-OPS-119..124 (F3.3, spec canónico)
 *
 * Mensajes son KEYS de i18n — los componentes `<AbrirTurnoForm>` /
 * `<CerrarTurnoForm>` los traducen via `useTranslation('caja')`.
 * NOTA: validación local usa KEYS (no strings traducidos) — el resolver
 * RHF acepta strings arbitrarios y el componente mapea al traducir.
 */
import { z } from 'zod';

/**
 * Regex que el input numérico enforced cada keystroke.
 *
 * Matchea:
 *   - ""        (vacío)                  -> tratado como 0 por el onChange
 *   - "0", "12" (entero)                -> Number(x)
 *   - "12.", "12.3", "12.34" (decimales) -> Number(x)
 *   - ".5", ".99" (sin 0 a la izquierda) -> Number(x)
 *
 * NO matchea (silent drop):
 *   - "." solo ("0" sin parte entera)
 *   - letras, símbolos (`+`, `-`, `e`, whitespace)
 *   - más de 2 dígitos decimales ("12.345")
 *
 * Cubre todos los flujos del kiosko (céntimos = 2 decimales), no
 * acepta exponentes porque los valores son magnitudes físicas, no
 * cantidades científicas.
 */
export const NUMERIC_INPUT_REGEX =
  /^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/;

/**
 * Form input schema para AbrirTurno (REQ-OPS-119).
 *
 * Campos:
 *   - uuid_sucursal: string UUID (F1.3 backend Pydantic requiere UUID).
 *   - uuid_usuario:  string UUID (F1.3).
 *   - valor_inicial_efectivo: STRING en form / NUMBER a la API.
 *     El input es `type="text"` para evitar los quirks de
 *     `<input type="number">` (defaultValue=0 pegado, sin clear,
 *     scroll-wheel en Electron). Validamos con `NUMERIC_INPUT_REGEX`
 *     en cada keystroke Y en blur. `.transform(Number)` convierte
 *     el string aceptado al número que espera la API.
 *   - valor_inicial_datafono: mismo shape que efectivo.
 *   - observaciones: string opcional (libre, RHF "" = omitido en POST).
 */
export const abrirTurnoSchema = z.object({
  uuid_sucursal: z
    .string({ required_error: 'validation.required' })
    .uuid({ message: 'validation.uuid.invalid' }),
  uuid_usuario: z
    .string({ required_error: 'validation.required' })
    .uuid({ message: 'validation.uuid.invalid' }),
  valor_inicial_efectivo: z
    .string({ required_error: 'validation.required' })
    .max(20, { message: 'validation.number.tooLong' })
    .regex(NUMERIC_INPUT_REGEX, { message: 'validation.number.format' })
    .transform((s) => (s === '' ? 0 : Number(s)))
    .pipe(
      z
        .number({ invalid_type_error: 'validation.number.required' })
        .min(0, { message: 'validation.number.minZero' }),
    ),
  valor_inicial_datafono: z
    .string({ required_error: 'validation.required' })
    .max(20, { message: 'validation.number.tooLong' })
    .regex(NUMERIC_INPUT_REGEX, { message: 'validation.number.format' })
    .transform((s) => (s === '' ? 0 : Number(s)))
    .pipe(
      z
        .number({ invalid_type_error: 'validation.number.required' })
        .min(0, { message: 'validation.number.minZero' }),
    ),
  observaciones: z.string().optional(),
});

export type AbrirTurnoInput = z.infer<typeof abrirTurnoSchema>;

/**
 * Form input schema para CerrarTurno (REQ-OPS-122, REQ-OPS-157, AD-2).
 *
 * El uuid NO vive en el form (viene del path param via `useSesionActiva()`).
 * Campos:
 *   - valor_final_efectivo: number ≥ 0 (F3.3 — cuerpo del PUT).
 *   - valor_final_datafono: number ≥ 0 (F3.3 — cuerpo del PUT).
 *   - observaciones_cierre: string opcional (F3.3 — cuerpo del PUT).
 *
 * F10.2 HU delta (REQ-OPS-157, REQ-OPS-158): agrega los campos del
 * `POST /caja/arqueo` (HU-F1.13):
 *   - valor_efectivo_reportado: number ≥ 0 (cuerpo del POST arqueo).
 *   - valor_datafono_reportado: number ≥ 0 (cuerpo del POST arqueo).
 *   - justificacion: string opcional (F10.1 lenient; F10.2 strict-mode
 *     cuando `requiredMode='cierre_turno'` lo promueve a top-level
 *     `min(3)` en el presentational component).
 *
 * La validación strict-mode (top-level `min(3)` cuando `requiredMode`
 * es `'cierre_turno'` / `'cierre_dia'`) vive en el schema LOCAL del
 * componente que consume este input — el shared schema acepta
 * `justificacion.optional()` para mantener el F3.3 contrato.
 */
export const cerrarTurnoSchema = z.object({
  valor_final_efectivo: z
    .number({ invalid_type_error: 'validation.number.required' })
    .min(0, { message: 'validation.number.minZero' }),
  valor_final_datafono: z
    .number({ invalid_type_error: 'validation.number.required' })
    .min(0, { message: 'validation.number.minZero' }),
  observaciones_cierre: z.string().optional(),
  valor_efectivo_reportado: z
    .number({ invalid_type_error: 'validation.number.required' })
    .min(0, { message: 'validation.number.minZero' }),
  valor_datafono_reportado: z
    .number({ invalid_type_error: 'validation.number.required' })
    .min(0, { message: 'validation.number.minZero' }),
  justificacion: z.string().optional(),
});

export type CerrarTurnoInput = z.infer<typeof cerrarTurnoSchema>;