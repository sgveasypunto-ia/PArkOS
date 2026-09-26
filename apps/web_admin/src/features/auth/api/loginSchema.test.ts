/**
 * `loginSchema.test.ts` — Unit tests for the Zod login schema.
 *
 * Verifies the four validation rules:
 *   - email is required (min(1))
 *   - email format must be valid (z.string().email())
 *   - password is required (min(1))
 *   - password must be at least 8 characters
 *
 * Messages are i18n KEYS (e.g. `validation.required`) — never the
 * translated text itself. The LoginForm calls `t(message)` so the
 * user-facing copy comes from the locale file, not the schema.
 */
import { describe, expect, it } from 'vitest';
import { loginSchema } from './loginSchema';

describe('loginSchema', () => {
  it('accepts a valid email + 8+ char password', () => {
    const r = loginSchema.safeParse({ email: 'admin@parkos.local', password: 'Pass1234word' });
    expect(r.success).toBe(true);
  });

  it('rejects an empty email with validation.required', () => {
    const r = loginSchema.safeParse({ email: '', password: 'Pass1234word' });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues[0]?.message).toBe('validation.required');
    }
  });

  it('rejects an invalid email format', () => {
    const r = loginSchema.safeParse({ email: 'not-an-email', password: 'Pass1234word' });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues[0]?.message).toBe('validation.email.invalid');
    }
  });

  it('rejects an empty password with validation.password.required', () => {
    const r = loginSchema.safeParse({ email: 'admin@parkos.local', password: '' });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues[0]?.message).toBe('validation.password.required');
    }
  });

  it('rejects a password shorter than 8 characters', () => {
    const r = loginSchema.safeParse({ email: 'admin@parkos.local', password: 'short' });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues[0]?.message).toBe('validation.password.minLength');
    }
  });
});
