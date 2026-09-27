/**
 * `adminUsuarioSchema.test.ts` — Zod round-trip tests (IT-1.4).
 */
import { describe, expect, it } from 'vitest';

import { ROLES, adminUsuarioCreateSchema, adminUsuarioReadSchema } from './adminUsuarioSchema';

describe('adminUsuarioCreateSchema', () => {
  it('accepts a minimal valid payload (operador, no branches)', () => {
    const r = adminUsuarioCreateSchema.safeParse({
      email: 'op@parkos.local',
      password: 'Pass1234word',
      rol: 'operador',
    });
    expect(r.success).toBe(true);
    if (r.success) {
      expect(r.data.sucursales_asignadas).toEqual([]);
    }
  });

  it('accepts a payload with branches', () => {
    const r = adminUsuarioCreateSchema.safeParse({
      email: 'admin@parkos.local',
      password: 'Pass1234word',
      rol: 'admin',
      sucursales_asignadas: ['00000000-0000-0000-0000-000000000001'],
    });
    expect(r.success).toBe(true);
  });

  it('rejects invalid email', () => {
    const r = adminUsuarioCreateSchema.safeParse({
      email: 'not-an-email',
      password: 'Pass1234word',
      rol: 'operador',
    });
    expect(r.success).toBe(false);
  });

  it('rejects short password', () => {
    const r = adminUsuarioCreateSchema.safeParse({
      email: 'op@parkos.local',
      password: 'short',
      rol: 'operador',
    });
    expect(r.success).toBe(false);
  });

  it('rejects unknown rol', () => {
    const r = adminUsuarioCreateSchema.safeParse({
      email: 'op@parkos.local',
      password: 'Pass1234word',
      rol: 'supervisor',
    });
    expect(r.success).toBe(false);
  });

  it('rejects non-UUID in sucursales_asignadas', () => {
    const r = adminUsuarioCreateSchema.safeParse({
      email: 'op@parkos.local',
      password: 'Pass1234word',
      rol: 'operador',
      sucursales_asignadas: ['not-a-uuid'],
    });
    expect(r.success).toBe(false);
  });

  it('exposes ROLES with admin and operador', () => {
    expect(ROLES).toEqual(['admin', 'operador']);
  });
});

describe('adminUsuarioReadSchema', () => {
  it('parses a backend-shape payload with password_hash absent', () => {
    const r = adminUsuarioReadSchema.safeParse({
      uuid: '00000000-0000-0000-0000-000000000001',
      email: 'op@parkos.local',
      nombre: null,
      apellido: null,
      cedula: null,
      rol: 'operador',
      vigente_desde: '2026-09-27T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-09-27T00:00:00',
      created_by: null,
      sync_status: 'pendiente',
    });
    expect(r.success).toBe(true);
  });
});
