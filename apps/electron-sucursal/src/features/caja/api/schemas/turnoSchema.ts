/**
 * `turnoSchema.ts` — Zod schemas compartidos para AbrirTurno + CerrarTurno (F3.3 — T2/T3).
 *
 * Plan.md:1338 verbatim:
 *   `z.object({ valor_inicial_efectivo: z.number().min(0),
 *              valor_inicial_datafono: z.number().min(0),
 *              observaciones: z.string().optional() })`
 *
 * DEC-F3.3-01 + DEC-F3.3-02 + DEC-F3.3-08:
 *   - Container/Presentational split (F3.1 DEC-F3.1-02 verbatim).
 *   - inputMode="decimal" + type="number" + step="0.01" en `<Input>` (UI).
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
 * Form input schema para AbrirTurno (REQ-OPS-119).
 *
 * Campos:
 *   - uuid_sucursal: string UUID (F1.3 backend Pydantic requiere UUID).
 *   - uuid_usuario:  string UUID (F1.3).
 *   - valor_inicial_efectivo: number ≥ 0 (decimales, kiosko limita a 2).
 *   - valor_inicial_datafono: number ≥ 0 (decimales, kiosko limita a 2).
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
    .number({ invalid_type_error: 'validation.number.required' })
    .min(0, { message: 'validation.number.minZero' }),
  valor_inicial_datafono: z
    .number({ invalid_type_error: 'validation.number.required' })
    .min(0, { message: 'validation.number.minZero' }),
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