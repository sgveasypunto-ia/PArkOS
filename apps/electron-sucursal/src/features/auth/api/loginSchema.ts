import { z } from 'zod';

/**
 * Form input schema para Login (F3.1 — DEC-F3.1-06).
 *
 * Zod local en form (NO en parkosFetch schema boundary — DEC-FETCH-05
 * opcional queda para otra HU). Mensajes son KEYS de i18n — el componente
 * `<LoginForm>` los traduce via useTranslation('auth').
 *
 * Reglas:
 *   - email: requerido + formato email válido (z.string().email()).
 *   - password: requerido + mínimo 8 caracteres (alineado con backend
 *     `schemas/auth.py: LoginRequest.password: StringConstraints(min_length=8)`).
 *
 * DEC-F3.1-08 anti-enumeración: NO se diferencia "email no existe" vs
 * "password incorrecta" — el backend colapsa 401 a errors.invalid_credentials
 * único (auth.py:159-191, 248-251), el frontend matchea.
 */
export const loginSchema = z.object({
  email: z
    .string()
    .min(1, { message: 'validation.required' })
    .email({ message: 'validation.email.invalid' }),
  password: z
    .string()
    .min(1, { message: 'validation.password.required' })
    .min(8, { message: 'validation.password.minLength' }),
});

export type LoginInput = z.infer<typeof loginSchema>;