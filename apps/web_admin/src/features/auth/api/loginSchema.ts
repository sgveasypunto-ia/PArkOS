/**
 * `loginSchema.ts` — Form input schema for `web_admin` admin login
 * (IT-1.10 of `openspec/_meta/iteration-plan.md`).
 *
 * Mirrors the pattern from `apps/electron-sucursal/src/features/auth/api/loginSchema.ts`
 * but is OWNED by `web_admin` (NOT yet shared via `@parkos/ui-kit`).
 * Sharing to ui-kit is deferred until `web_sucursal` also adopts the
 * same shape; right now each package owns its copy to keep the
 * dependency graph asymmetric (web_admin doesn't import from
 * electron-sucursal and vice-versa).
 *
 * Rules:
 *   - email: required + valid email format (z.string().email()).
 *   - password: required + minimum 8 chars (aligned with backend
 *     `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` —
 *     `LoginRequest.password: StringConstraints(min_length=8)`).
 *
 * Messages are KEYS of i18n — the `<LoginForm />` translates them
 * via `useTranslation('auth')`. The form's own copy stays ASCII so
 * i18n lookup never fails on missing translations.
 *
 * DEC-LOGIN-08 anti-enumeration (mirrors DEC-F3.1-08 from
 * electron-sucursal): the 401 response is collapsed to a SINGLE
 * `auth.invalidCredentials` string — the form never tells the user
 * whether the email or the password was the wrong one.
 */
import { z } from 'zod';

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
