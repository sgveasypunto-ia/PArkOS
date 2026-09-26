/**
 * `sucursalSchema.test.ts` -- unit tests for the zod schemas
 * (IT-2.7).
 *
 * Pydantic/zod schemas are the boundary; tests here lock in:
 *   - Required-field rejection with the canonical i18n KEYS.
 *   - `prefijo_nombre` UK-format rejection (3-6 uppercase chars).
 *   - Optional fields stay optional (null or undefined both pass).
 *   - Read-side payload parses with `vigente_hasta=null`.
 */
import { describe, expect, it } from 'vitest';

import {
  pairingTokenResponseSchema,
  sucursalCreateSchema,
  sucursalReadListSchema,
  sucursalReadSchema,
} from './sucursalSchema';

describe('sucursalCreateSchema', () => {
  it('accepts a minimal valid payload', () => {
    const r = sucursalCreateSchema.safeParse({
      nombre: 'Sucursal Centro',
      prefijo_nombre: 'BOG-CEN',
    });
    expect(r.success).toBe(true);
  });
  it('rejects empty nombre', () => {
    const r = sucursalCreateSchema.safeParse({
      nombre: '',
      prefijo_nombre: 'BOG-CEN',
    });
    expect(r.success).toBe(false);
  });

  it('rejects empty prefijo_nombre', () => {
    const r = sucursalCreateSchema.safeParse({
      nombre: 'Sucursal Centro',
      prefijo_nombre: '',
    });
    expect(r.success).toBe(false);
  });

  it('rejects lowercase prefix', () => {
    const r = sucursalCreateSchema.safeParse({
      nombre: 'Sucursal Centro',
      prefijo_nombre: 'bog-cen',
    });
    expect(r.success).toBe(false);
  });

  it('rejects prefix longer than 6 chars', () => {
    const r = sucursalCreateSchema.safeParse({
      nombre: 'Sucursal Centro',
      prefijo_nombre: 'BOG-CENT',
    });
    expect(r.success).toBe(false);
  });

  it('accepts null for optional fields', () => {
    const r = sucursalCreateSchema.safeParse({
      nombre: 'X',
      prefijo_nombre: 'X1-CEN',
      direccion: null,
      telefono: null,
      ciudad: null,
      horario: null,
      uuid_tipo_sucursal: null,
      uuid_empresa: null,
    });
    expect(r.success).toBe(true);
  });
});

describe('sucursalReadSchema', () => {
  it('parses a backend-shape payload with vigente_hasta=null', () => {
    const r = sucursalReadSchema.safeParse({
      uuid: '00000000-0000-0000-0000-0000000000a1',
      nombre: 'Sucursal Centro',
      direccion: null,
      telefono: null,
      prefijo_nombre: 'BOG-CEN',
      ciudad: 'Bogota',
      horario: null,
      uuid_tipo_sucursal: null,
      uuid_empresa: null,
      vigente_desde: '2026-09-26T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-09-26T00:00:00',
      created_by: null,
      sync_status: null,
    });
    expect(r.success).toBe(true);
  });

  it('parses a list response', () => {
    const r = sucursalReadListSchema.safeParse({
      items: [
        {
          uuid: '00000000-0000-0000-0000-0000000000a1',
          nombre: 'X',
          direccion: null,
          telefono: null,
          prefijo_nombre: null,
          ciudad: null,
          horario: null,
          uuid_tipo_sucursal: null,
          uuid_empresa: null,
          vigente_desde: '2026-09-26T00:00:00',
          vigente_hasta: null,
          estado: 'activo',
          created_at: '2026-09-26T00:00:00',
          created_by: null,
          sync_status: null,
        },
      ],
      next_cursor: null,
    });
    expect(r.success).toBe(true);
  });
});

describe('pairingTokenResponseSchema', () => {
  it('parses a real response', () => {
    const r = pairingTokenResponseSchema.safeParse({
      token: 'header.payload.sig',
      expires_at: '2026-09-26T22:00:00',
      sucursal_uuid: '00000000-0000-0000-0000-0000000000a1',
    });
    expect(r.success).toBe(true);
  });

  it('rejects an empty token', () => {
    const r = pairingTokenResponseSchema.safeParse({
      token: '',
      expires_at: '2026-09-26T22:00:00',
      sucursal_uuid: '00000000-0000-0000-0000-0000000000a1',
    });
    expect(r.success).toBe(false);
  });
});
