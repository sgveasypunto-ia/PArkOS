/**
 * Unit tests for `canonicalJSON` (HU-F6.1, DEC-SUC-04).
 *
 * The Idempotency-Key header MUST be stable across re-submissions that
 * carry the same logical body. These tests pin the deterministic
 * contract:
 *   - Same object with shuffled keys → same canonical string.
 *   - Nested objects sorted recursively.
 *   - `undefined` stripped (matches F2.2 parkosFetch convention).
 *   - `null` preserved (semantic value, not a missing key).
 *   - Arrays preserve order (order is semantic for our payloads).
 *   - Output roundtrips through `JSON.parse`.
 */
import { describe, expect, it } from 'vitest';

import { canonicalJSON } from './canonicalJson';

describe('canonicalJSON', () => {
  it('sorts top-level keys alphabetically', () => {
    const a = canonicalJSON({ b: 1, a: 2 });
    const b = canonicalJSON({ a: 2, b: 1 });
    expect(a).toBe('{"a":2,"b":1}');
    expect(a).toBe(b);
  });

  it('sorts nested object keys recursively', () => {
    const a = canonicalJSON({ outer: { z: 1, a: { y: 1, x: 2 } } });
    const b = canonicalJSON({ outer: { a: { x: 2, y: 1 }, z: 1 } });
    expect(a).toBe(b);
    expect(a).toBe('{"outer":{"a":{"x":2,"y":1},"z":1}}');
  });

  it('strips undefined values from objects', () => {
    const a = canonicalJSON({ a: 1, b: undefined, c: 3 });
    expect(a).toBe('{"a":1,"c":3}');
  });

  it('preserves null as a semantic value', () => {
    const a = canonicalJSON({ a: null, b: 2 });
    expect(a).toBe('{"a":null,"b":2}');
  });

  it('preserves array order', () => {
    const a = canonicalJSON([3, 1, 2]);
    expect(a).toBe('[3,1,2]');
  });

  it('preserves object key order inside array elements (sort still applies per element)', () => {
    const a = canonicalJSON([{ b: 1, a: 2 }, { d: 3, c: 4 }]);
    expect(a).toBe('[{"a":2,"b":1},{"c":4,"d":3}]');
  });

  it('roundtrips through JSON.parse without losing data', () => {
    const payload = {
      placa: 'ABC123',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
      observaciones: 'test',
      forzado: undefined,
    };
    const canonical = canonicalJSON(payload);
    expect(JSON.parse(canonical)).toEqual({
      placa: 'ABC123',
      uuid_tipo_vehiculo: '11111111-1111-1111-1111-111111111111',
      observaciones: 'test',
    });
  });

  it('handles primitives unchanged', () => {
    expect(canonicalJSON('hello')).toBe('"hello"');
    expect(canonicalJSON(42)).toBe('42');
    expect(canonicalJSON(true)).toBe('true');
    expect(canonicalJSON(null)).toBe('null');
  });

  it('produces stable SHA-256 input across runs (F6.1 Idempotency-Key contract)', () => {
    // This is the actual property the spec requires: two POSTs with the
    // same logical body — even if keys are inserted in different orders
    // by the caller — MUST produce the SAME Idempotency-Key. We assert
    // it via the canonical string rather than hashing here; the hash
    // function is exercised in `ingresoApi.test.ts`.
    const body1 = canonicalJSON({ placa: 'ABC123', uuid_tipo_vehiculo: 'u' });
    const body2 = canonicalJSON({ uuid_tipo_vehiculo: 'u', placa: 'ABC123' });
    expect(body1).toBe(body2);
  });
});
