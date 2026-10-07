/**
 * Unit tests for `postIngreso` payload schemas (HU-F6.1, T3)
 * + HU-INGRESO-SIN-PLACA discriminated-union payload validation
 * (REQ-OPS-194 + REQ-OPS-197).
 *
 * Idempotency-Key per user action is covered in idempotencyReplay.test.ts.
 *
 * HU-INGRESO-SIN-PLACA spec scenarios:
 *   - Con-placa payload validates.
 *   - Sin-placa payload validates.
 *   - Mixed payload (`placa_presente: true` + `placa: null`) is rejected.
 *   - Response with `consecutivo: 'BICI-000001-3f8a1b2c'` parses.
 */
import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import {
  PostIngresoPayloadSchema,
  PostIngresoResponseSchema,
} from './ingresoApi';

/**
 * HU-INGRESO-SIN-PLACA discriminated-union coverage (REQ-OPS-194 +
 * REQ-OPS-197). The schema rejects malformed payloads at the client
 * boundary so the network round-trip is not wasted on 422.
 */
describe('PostIngresoPayloadSchema (REQ-OPS-194 discriminated union)', () => {
  it('test_postIngreso_con_placa_payload_validation_accepted', () => {
    const result = PostIngresoPayloadSchema.safeParse({
      placa_presente: true,
      placa: 'ABC123',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
    });
    expect(result.success).toBe(true);
  });

  it('test_postIngreso_sin_placa_payload_validation_accepted', () => {
    const result = PostIngresoPayloadSchema.safeParse({
      placa_presente: false,
      placa: null,
      uuid_tipo_vehiculo: '22222222-2222-2222-2222-222222222222',
    });
    expect(result.success).toBe(true);
  });

  it('test_postIngreso_mixed_payload_rejected (placa_presente:true + placa:null → ZodError)', () => {
    const result = PostIngresoPayloadSchema.safeParse({
      placa_presente: true,
      placa: null,
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      // The discriminator failure surfaces a clear typed error.
      expect(result.error).toBeInstanceOf(z.ZodError);
      expect(result.error.issues.length).toBeGreaterThan(0);
    }
  });

  it('test_postIngreso_sin_placa_con_placa_string_rejected (placa_presente:false + placa:"ABC123")', () => {
    // The discriminator is the boolean literal; a sin-placa variant
    // with `placa: 'ABC123'` violates the literal-null constraint on
    // the no-placa schema.
    const result = PostIngresoPayloadSchema.safeParse({
      placa_presente: false,
      placa: 'ABC123',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
    });
    expect(result.success).toBe(false);
  });

  it('test_postIngreso_sin_placa_without_uuid_tipo_rejected', () => {
    // The sin-placa schema requires `uuid_tipo_vehiculo` (not optional,
    // unlike the con-placa variant).
    const result = PostIngresoPayloadSchema.safeParse({
      placa_presente: false,
      placa: null,
    });
    expect(result.success).toBe(false);
  });
});

describe('PostIngresoResponseSchema (REQ-OPS-197 + consecutivo field)', () => {
  it('test_postIngreso_response_parses_consecutivo (mock with BICI-000001-3f8a1b2c)', () => {
    // REQ-OPS-197: the backend field is `uuid` (see `PostIngresoResponseSchema`),
    // not the older `uuid_ingreso` discriminator this fixture used to mock.
    const result = PostIngresoResponseSchema.safeParse({
      uuid: '11111111-2222-4333-8444-555555555555',
      tipo_entrada: 'ROTACION',
      uuid_subscripcion_cliente: null,
      consecutivo: 'BICI-000001-3f8a1b2c',
    });
    expect(result.success).toBe(true);
  });

  it('test_postIngreso_response_parses_consecutivo_null (legacy carro/moto row)', () => {
    // Backward compat: legacy rows have `consecutivo = null` after
    // PR-A migration (REQ-OPS-192 scenario 1). The schema accepts null.
    const result = PostIngresoResponseSchema.safeParse({
      uuid: '11111111-2222-4333-8444-555555555555',
      tipo_entrada: 'ROTACION',
      uuid_subscripcion_cliente: null,
      consecutivo: null,
    });
    expect(result.success).toBe(true);
  });

  it('test_postIngreso_response_without_consecutivo_key_rejected (wire-shape drift guard)', () => {
    // The backend MUST always send `consecutivo` (even if null). A
    // response missing the key entirely is a wire-shape break.
    const result = PostIngresoResponseSchema.safeParse({
      uuid: '11111111-2222-4333-8444-555555555555',
      tipo_entrada: 'ROTACION',
      uuid_subscripcion_cliente: null,
    });
    expect(result.success).toBe(false);
  });
});
