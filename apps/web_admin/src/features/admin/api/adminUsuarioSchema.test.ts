/**
 * `adminUsuarioSchema.test.ts` — Zod round-trip tests (IT-1.4 + HU-F16.2).
 */
import { describe, expect, it } from 'vitest';

import {
  ESTADOS,
  ROLES,
  adminUsuarioCreateSchema,
  adminUsuarioReadSchema,
  datosPersonalesStepSchema,
  rolStepSchema,
  sucursalesStepSchema,
} from './adminUsuarioSchema';

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

  it('parses the embedded sucursales array from the list payload', () => {
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
      sync_status: null,
      sucursales: [
        {
          uuid_sucursal: '11111111-1111-4111-8111-111111111111',
          nombre: 'Sucursal Norte',
          prefijo_nombre: 'NOR',
          vigente_desde: '2026-09-27T00:00:00',
        },
        {
          uuid_sucursal: '22222222-2222-4222-8222-222222222222',
          nombre: null,
          prefijo_nombre: 'SUR',
          vigente_desde: '2026-09-27T00:00:00',
        },
      ],
    });
    expect(r.success).toBe(true);
    if (r.success) {
      expect(r.data.sucursales).toHaveLength(2);
      expect(r.data.sucursales[0]?.nombre).toBe('Sucursal Norte');
      expect(r.data.sucursales[1]?.nombre).toBeNull();
      expect(r.data.sucursales[1]?.prefijo_nombre).toBe('SUR');
    }
  });

  it('defaults sucursales to [] when the backend omits the field', () => {
    // Defense against stale responses from a deployment that predates
    // the backend embedding the array: the parser must still succeed
    // so the table renders "Sin sucursales" instead of crashing.
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
      sync_status: null,
    });
    expect(r.success).toBe(true);
    if (r.success) {
      expect(r.data.sucursales).toEqual([]);
    }
  });
});

describe('wizard per-step schemas (HU-F16.2)', () => {
  // The step schemas `.pick()` their fields straight off
  // `adminUsuarioCreateSchema` so the wizard validates against the SAME
  // rules as the single-shot payload -- these tests guard that contract,
  // not just the individual field rules (already covered above).

  describe('datosPersonalesStepSchema', () => {
    it('accepts email + password with optional fields omitted', () => {
      const r = datosPersonalesStepSchema.safeParse({
        email: 'op@parkos.local',
        password: 'Pass1234word',
      });
      expect(r.success).toBe(true);
    });

    it('accepts nombre/apellido/cedula when provided', () => {
      const r = datosPersonalesStepSchema.safeParse({
        email: 'op@parkos.local',
        password: 'Pass1234word',
        nombre: 'Ana',
        apellido: 'Gomez',
        cedula: '123456789',
      });
      expect(r.success).toBe(true);
    });

    it('rejects invalid email (same rule as the full schema)', () => {
      const r = datosPersonalesStepSchema.safeParse({
        email: 'not-an-email',
        password: 'Pass1234word',
      });
      expect(r.success).toBe(false);
    });

    it('rejects short password (backend min_length=8, NOT the 12 in plan.md)', () => {
      const r = datosPersonalesStepSchema.safeParse({
        email: 'op@parkos.local',
        password: 'short',
      });
      expect(r.success).toBe(false);
    });

    it('does NOT require rol or sucursales_asignadas (picked out of the step)', () => {
      const r = datosPersonalesStepSchema.safeParse({
        email: 'op@parkos.local',
        password: 'Pass1234word',
        rol: 'not-a-real-rol-but-irrelevant-here',
      });
      // `rol` is simply ignored by `.pick()` -- it is not part of this
      // step's shape, so an invalid value for it must not fail parsing.
      expect(r.success).toBe(true);
    });
  });

  describe('rolStepSchema', () => {
    it('accepts a valid rol', () => {
      expect(rolStepSchema.safeParse({ rol: 'admin' }).success).toBe(true);
      expect(rolStepSchema.safeParse({ rol: 'operador' }).success).toBe(true);
    });

    it('rejects an unknown rol', () => {
      expect(rolStepSchema.safeParse({ rol: 'supervisor' }).success).toBe(false);
    });

    it('rejects a missing rol', () => {
      expect(rolStepSchema.safeParse({}).success).toBe(false);
    });
  });

  describe('sucursalesStepSchema', () => {
    it('defaults to [] when omitted', () => {
      const r = sucursalesStepSchema.safeParse({});
      expect(r.success).toBe(true);
      if (r.success) {
        expect(r.data.sucursales_asignadas).toEqual([]);
      }
    });

    it('accepts a list of branch UUIDs', () => {
      const r = sucursalesStepSchema.safeParse({
        sucursales_asignadas: ['00000000-0000-0000-0000-000000000001'],
      });
      expect(r.success).toBe(true);
    });

    it('rejects a non-UUID entry', () => {
      const r = sucursalesStepSchema.safeParse({
        sucursales_asignadas: ['not-a-uuid'],
      });
      expect(r.success).toBe(false);
    });
  });

  it('ESTADOS exposes activo and inactivo (bi-temporal close+insert states)', () => {
    expect(ESTADOS).toEqual(['activo', 'inactivo']);
  });
});
