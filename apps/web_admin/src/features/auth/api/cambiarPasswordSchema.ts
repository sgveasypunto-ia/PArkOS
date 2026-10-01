/**
 * HU-F16 must-change enforcement: change the operator's temporary password.
 *
 * Mirrors the LoginRequest shape (email + password) but the new
 * password is the only thing we send to ``POST /auth/cambiar-password``
 * because the temporary token carries the operator's identity.
 *
 * The schema intentionally does NOT ask for `email`: by the time the
 * form renders, the user has already proven email ownership (the
 * temp token would not exist otherwise), so re-typing it is friction
 * for no security gain.
 */
import { z } from 'zod';

export const cambiarPasswordSchema = z.object({
  new_password: z
    .string()
    .min(8, 'mustChangePassword.errors.minLength')
    .max(128, 'mustChangePassword.errors.maxLength'),
  confirm_password: z
    .string()
    .min(8, 'mustChangePassword.errors.minLength')
    .max(128, 'mustChangePassword.errors.maxLength'),
}).refine((data) => data.new_password === data.confirm_password, {
  message: 'mustChangePassword.errors.mismatch',
  path: ['confirm_password'],
});

export type CambiarPasswordInput = z.infer<typeof cambiarPasswordSchema>;