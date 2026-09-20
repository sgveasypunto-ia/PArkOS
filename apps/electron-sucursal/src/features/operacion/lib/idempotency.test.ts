/**
 * Unit tests for `buildIdempotencyKey` (HU-F7.2, REQ-OPS-155).
 *
 * The Idempotency-Key MUST be stable across re-submissions of the same
 * logical mutation body. Two consecutive calls with the same
 * `{method, path, body}` triple MUST return identical hex digests
 * independent of property order, whitespace, or platform byte-order
 * (RFC 8785 canonicalization).
 *
 * Coverage:
 *   I1: same input → same output (deterministic across two calls).
 *   I2: property-order independence via `canonicalJson` (RFC 8785).
 */
import { describe, expect, it } from 'vitest';

import { buildIdempotencyKey } from './idempotency';

describe('buildIdempotencyKey — RFC 8785 + SHA-256 closure', () => {
  it('I1: same input triple → same hex digest across two calls', async () => {
    const args = {
      method: 'POST',
      path: '/api/v1/operacion/salidas',
      body: { uuid_ingreso: '00000000-0000-0000-0000-000000000001' },
    };
    const k1 = await buildIdempotencyKey(args);
    const k2 = await buildIdempotencyKey(args);
    expect(k1).toBe(k2);
    expect(k1).toMatch(/^[a-f0-9]{64}$/);
  });

  it('I2: property-order independence — shuffled keys produce same digest', async () => {
    const a = await buildIdempotencyKey({
      method: 'POST',
      path: '/api/v1/operacion/salidas',
      body: { a: 1, b: 2, c: 3 },
    });
    const b = await buildIdempotencyKey({
      method: 'POST',
      path: '/api/v1/operacion/salidas',
      body: { c: 3, a: 1, b: 2 },
    });
    const c = await buildIdempotencyKey({
      method: 'POST',
      path: '/api/v1/operacion/salidas',
      body: { b: 2, c: 3, a: 1 },
    });
    expect(a).toBe(b);
    expect(a).toBe(c);
  });
});