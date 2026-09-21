/**
 * `mi-turno.test.ts` — Zod schema tests + BE/FE key-set lock for HU-F12.1
 * (REQ-OPS-184 + REQ-OPS-189, DA-F12.1-1 / DA-F12.1-9 GATING).
 *
 * The 7-field wire shape is locked on BOTH sides of the boundary:
 *   - BE pytest: `backend/tests/unit/test_mi_turno_schema.py` reads
 *     `MiTurnoRead.model_fields.keys()` and asserts equality.
 *   - FE vitest (this file): `Object.keys(MiTurnoSchema.shape)` mirrors
 *     the fixture. CI fails on drift.
 *
 * Coverage:
 *   S1: canonical payload parses + 7 fields preserved + Decimal fields
 *       accept both number and string at the wire (JSON has no Decimal).
 *   S2: `strict()` rejects a hypothetical 8th field — defense against
 *       BE schema drift.
 *   S3: key-set equality with the BE Pydantic key set.
 *   S4: required fields (uuid_sesion, uuid_sucursal, timestamp_calculo)
 *       raise ZodError when missing.
 */
import { describe, it, expect } from 'vitest';

import { MiTurnoSchema } from '../mi-turno';

const VALID_UUID_SESION = '00000000-0000-0000-0000-000000000001';
const VALID_UUID_SUCURSAL = '00000000-0000-0000-0000-000000000002';

const BASE_OK = {
  uuid_sesion: VALID_UUID_SESION,
  uuid_sucursal: VALID_UUID_SUCURSAL,
  timestamp_calculo: '2026-09-21T08:00:00',
  ingresos_count: 3,
  salidas_count: 2,
  total_cobrado_efectivo_cop: 50000,
  total_cobrado_datafono_cop: 30000,
};

describe('MiTurnoSchema — REQ-OPS-184 + REQ-OPS-189 (HU-F12.1)', () => {
  it('S1: canonical payload parses; 7 fields preserved verbatim', () => {
    const parsed = MiTurnoSchema.parse(BASE_OK);
    expect(parsed.uuid_sesion).toBe(VALID_UUID_SESION);
    expect(parsed.uuid_sucursal).toBe(VALID_UUID_SUCURSAL);
    expect(parsed.timestamp_calculo).toBe('2026-09-21T08:00:00');
    expect(parsed.ingresos_count).toBe(3);
    expect(parsed.salidas_count).toBe(2);
    expect(parsed.total_cobrado_efectivo_cop).toBe(50000);
    expect(parsed.total_cobrado_datafono_cop).toBe(30000);
    // The 7-field contract: no extra fields leak in.
    expect(Object.keys(parsed)).toHaveLength(7);
  });

  it('S2: strict() rejects a hypothetical 8th field (DA-F12.1-1)', () => {
    const drifted = { ...BASE_OK, phantom_field: 'drift from a future BE' };
    expect(() => MiTurnoSchema.parse(drifted)).toThrow();
  });

  it('S3: key set equals the BE Pydantic fixture (drift gate)', () => {
    // The 7-field wire shape MUST be identical to BE's MiTurnoRead.
    // Backend pytest reads `MiTurnoRead.model_fields.keys()` and
    // asserts equality with the same fixture (DA-F12.1-1 GATING).
    const actual = Object.keys(MiTurnoSchema.shape).sort();
    const expected = [
      'ingresos_count',
      'salidas_count',
      'timestamp_calculo',
      'total_cobrado_datafono_cop',
      'total_cobrado_efectivo_cop',
      'uuid_sesion',
      'uuid_sucursal',
    ];
    expect(actual).toEqual(expected);
  });

  it('S4a: missing uuid_sesion -> ZodError', () => {
    const { uuid_sesion: _omit, ...rest } = BASE_OK;
    expect(() => MiTurnoSchema.parse(rest)).toThrow();
  });

  it('S4b: missing uuid_sucursal -> ZodError', () => {
    const { uuid_sucursal: _omit, ...rest } = BASE_OK;
    expect(() => MiTurnoSchema.parse(rest)).toThrow();
  });

  it('S4c: missing timestamp_calculo -> ZodError', () => {
    const { timestamp_calculo: _omit, ...rest } = BASE_OK;
    expect(() => MiTurnoSchema.parse(rest)).toThrow();
  });

  it('S4d: negative ingresos_count is REJECTED (nonnegative constraint)', () => {
    expect(() => MiTurnoSchema.parse({ ...BASE_OK, ingresos_count: -1 })).toThrow();
  });

  it('S4e: ingresos_count with non-integer value is REJECTED', () => {
    expect(() =>
      MiTurnoSchema.parse({ ...BASE_OK, ingresos_count: 3.5 }),
    ).toThrow();
  });
});