/**
 * Unit tests for `validarNitModulo11()` (HU-F8.1, BR7 / DEC-SUC-29).
 *
 * The DIAN RUT/NIT módulo-11 verification algorithm:
 *   1. Take the NIT digits WITHOUT the verification digit (DV).
 *   2. Apply the published DIAN weight vector LEFT-TO-RIGHT:
 *      `[71, 67, 59, 53, 47, 43, 41, 37, 31, 29, 23, 19, 17, 13, 7, 3]`.
 *      For NITs > 16 digits the cycle repeats from 71.
 *   3. Sum the products.
 *   4. Compute `mod = sum % 11`. Then:
 *        if mod === 0 → dv = 0
 *        else if mod === 1 → dv = 1 (special case per DIAN)
 *        else → dv = 11 - mod
 *   5. Compare the computed DV with the supplied DV.
 *
 * Reference test (BR7 / plan.md:1857-1871): NIT `800.123.456-7`.
 *   digits (no DV) = [8,0,0,1,2,3,4,5,6] (9 digits)
 *   products (weights 71..67..3 left-to-right):
 *     8×71 = 568
 *     0×67 = 0
 *     0×59 = 0
 *     1×53 = 53
 *     2×47 = 94
 *     3×43 = 129
 *     4×41 = 164
 *     5×37 = 185
 *     6×31 = 186
 *   sum = 1379
 *   1379 % 11 = 4
 *   dv = 11 - 4 = 7 ✓
 *
 * Coverage (5 tests):
 *   T1: `validarNitModulo11('800.123.456', '7')` returns `{ok: true}`
 *       — canonical reference (BR7).
 *   T2: `validarNitModulo11('800.123.456', '1')` returns
 *       `{ok: false, dvEsperado: '7'}` — wrong DV rejected with the
 *       correct expected DV surfaced so the operator can correct it.
 *   T3: `validarNitModulo11('800123456', '7')` returns `{ok: true}`
 *       when normalized (no dots / dashes / whitespace).
 *   T4: `validarNitModulo11('123', '0')` returns `{ok: false}` (too
 *       short; minimum 6 digits per F1.10 schema `nit.length >= 6`).
 *   T5: `validarNitModulo11('900.123.456', '<correct-DV>')` returns
 *       `{ok: true}` (different valid NIT — same algorithm, different
 *       digits → different valid DV).
 *
 * No mocks — the function is pure deterministic.
 */
import { describe, it, expect } from 'vitest';

import { validarNitModulo11 } from './nit';

// Helper — recompute the standard modulo-11 DV inline so T5 can pin
// the "different valid NIT" round-trip without baking the answer into
// the test (the helper IS the algorithm under test).
function computeDV(nit: string): string {
  const digits = nit.replace(/\D+/g, '');
  const weights = [71, 67, 59, 53, 47, 43, 41, 37, 31, 29, 23, 19, 17, 13, 7, 3];
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    const w = weights[i % weights.length];
    sum += Number(digits[i]) * w;
  }
  const mod = sum % 11;
  if (mod === 0) return '0';
  if (mod === 1) return '1';
  return String(11 - mod);
}

describe('validarNitModulo11 — canonical reference (HU-F8.1 / BR7)', () => {
  it('T1: 800.123.456-7 (canonical reference, dots accepted)', () => {
    const result = validarNitModulo11('800.123.456', '7');
    expect(result.ok).toBe(true);
  });

  it('T2: 800.123.456 with WRONG DV returns {ok:false, dvEsperado:"7"}', () => {
    const result = validarNitModulo11('800.123.456', '1');
    expect(result.ok).toBe(false);
    expect(result.dvEsperado).toBe('7');
  });

  it('T3: 800123456 (normalized, no dots) accepts the canonical DV', () => {
    const result = validarNitModulo11('800123456', '7');
    expect(result.ok).toBe(true);
  });

  it('T4: too-short input "123" returns {ok:false}', () => {
    const result = validarNitModulo11('123', '0');
    expect(result.ok).toBe(false);
  });

  it('T5: 900.123.456 with the algorithm-computed DV → {ok:true}', () => {
    const dv = computeDV('900.123.456');
    const result = validarNitModulo11('900.123.456', dv);
    expect(result.ok).toBe(true);
  });
});