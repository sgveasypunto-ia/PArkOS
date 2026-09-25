/**
 * Unit tests for `postIngreso` Idempotency-Key derivation (HU-F6.1, T3)
 * + HU-INGRESO-SIN-PLACA discriminated-union payload validation
 * (REQ-OPS-194 + REQ-OPS-197).
 *
 * The spec §Requirement "Idempotent POST via Idempotency-Key" mandates
 * 3 scenarios:
 *   - Operator double-press (same body, 500ms apart): SAME key.
 *   - Body mutation (operator edits `observaciones`): DIFFERENT key.
 *   - Network retry (5xx → parkosFetch retry): SAME key (because the
 *     body didn't change between attempts; verified by re-deriving).
 *
 * We assert the keys directly via the exported `deriveIdempotencyKey`
 * helper (the network plumbing is exercised in `parkosFetch`'s own
 * suite; we don't re-test it here).
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
  deriveIdempotencyKey,
  PostIngresoPayloadSchema,
  PostIngresoResponseSchema,
  type PostIngresoPayload,
} from './ingresoApi';

const basePayload: PostIngresoPayload = {
  placa_presente: true,
  placa: 'ABC123',
  uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
  observaciones: 'first attempt',
};

describe('deriveIdempotencyKey', () => {
  it('returns the SAME key for two submissions with identical bodies (operator double-press)', async () => {
    const key1 = await deriveIdempotencyKey(basePayload);
    const key2 = await deriveIdempotencyKey(basePayload);
    expect(key1).toBe(key2);
    // SHA-256 hex is 64 chars.
    expect(key1).toMatch(/^[0-9a-f]{64}$/);
  });

  it('returns a DIFFERENT key when the body changes (observaciones edited)', async () => {
    const keyBefore = await deriveIdempotencyKey(basePayload);
    const keyAfter = await deriveIdempotencyKey({
      ...basePayload,
      observaciones: 'edited mid-session',
    });
    expect(keyBefore).not.toBe(keyAfter);
  });

  it('returns a DIFFERENT key when forzado toggles', async () => {
    const keyWithout = await deriveIdempotencyKey(basePayload);
    const keyWith = await deriveIdempotencyKey({
      ...basePayload,
      forzado: true,
    });
    expect(keyWithout).not.toBe(keyWith);
  });

  it('returns the SAME key when network retry fires with the same body (5xx → parkosFetch retry)', async () => {
    // Simulate the network retry path: same payload, same key.
    const keyAttempt1 = await deriveIdempotencyKey(basePayload);
    const keyAttempt2 = await deriveIdempotencyKey(basePayload);
    expect(keyAttempt1).toBe(keyAttempt2);
  });

  it('does NOT include `undefined` properties in the canonical material', async () => {
    const a = await deriveIdempotencyKey({
      placa_presente: true,
      placa: 'ABC123',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
      observaciones: undefined,
      forzado: undefined,
    });
    const b = await deriveIdempotencyKey({
      placa_presente: true,
      placa: 'ABC123',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
    });
    expect(a).toBe(b);
  });
});

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
