/**
 * HU-F16 must-change enforcement: change the operator's temporary password.
 * Mirror of web_admin's schema -- duplicated (not in @parkos/ui-kit) for
 * the same reason as loginSchema.
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