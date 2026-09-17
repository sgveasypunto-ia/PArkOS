/**
 * Unit tests for `postIngreso` Idempotency-Key derivation (HU-F6.1, T3).
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
 */
import { describe, expect, it } from 'vitest';

import { deriveIdempotencyKey, type PostIngresoPayload } from './ingresoApi';

const basePayload: PostIngresoPayload = {
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
      placa: 'ABC123',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
      observaciones: undefined,
      forzado: undefined,
    });
    const b = await deriveIdempotencyKey({
      placa: 'ABC123',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
    });
    expect(a).toBe(b);
  });
});
