/**
 * Unit tests for `validarNitModulo11()` (HU-F8.1, BR7 / DEC-SUC-29).
 *
 * The DIAN RUT/NIT módulo-11 verification algorithm — Variant A
 * canónica, MUST mirror backend `repo/nit_modulo11.py` exactly:
 *   1. Take the NIT digits WITHOUT the verification digit (DV).
 *   2. Apply the DIAN weight vector RIGHT-TO-LEFT:
 *      `[71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]`
 *      (15 elements, NO `31`). For NITs >15 digits the cycle repeats.
 *   3. Sum the products.
 *   4. `DV = sum % 11` directly (0..10) — NOT `11 - mod`.
 *   5. Compare the computed DV with the supplied DV.
 *
 * BUGFIX (2026-09-25, hallado en validación en vivo Chrome DevTools):
 * this file's ``computeDV`` helper (and the production ``nit.ts`` it
 * mirrored) implemented a DIFFERENT algorithm — 16 weights (including
 * `31`), LEFT-TO-RIGHT, `DV = 11 - mod`. It only agreed with the real
 * backend algorithm on `800.123.456` (DV `7`, pure coincidence for
 * that digit sequence — verified by hand below); a second real NIT
 * (`900123456`) diverges: this file's old algorithm computed `2`,
 * the backend computes `3` (confirmed live: `POST /facturacion/factura`
 * with `dv=2` → 422 "DV inválido: recibido=2, esperado=3"). Both
 * ``nit.ts`` and this test file are now corrected to match backend
 * byte-for-byte.
 *
 * Reference test (BR7 / plan.md:1857-1871): NIT `800.123.456-7`.
 *   digits reversed (no DV) = [6,5,4,3,2,1,0,0,8]
 *   products (weights 71..67..29 right-to-left):
 *     6×71=426, 5×67=335, 4×59=236, 3×53=159, 2×47=94,
 *     1×43=43, 0×41=0, 0×37=0, 8×29=232
 *   sum = 1525; 1525 % 11 = 7 → dv = 7 ✓ (both algorithms agree here)
 *
 * Second reference (discriminates the two variants): NIT `900123456`.
 *   Old (wrong) algorithm → dv = 2. Backend (correct) → dv = 3.
 *
 * Coverage (6 tests):
 *   T1: `validarNitModulo11('800.123.456', '7')` returns `{ok: true}`
 *       — canonical reference (BR7).
 *   T2: `validarNitModulo11('800.123.456', '1')` returns
 *       `{ok: false, dvEsperado: '7'}` — wrong DV rejected with the
 *       correct expected DV surfaced so the operator can correct it.
 *   T3: `validarNitModulo11('800123456', '7')` returns `{ok: true}`
 *       when normalized (no dots / dashes / whitespace).
 *   T4: `validarNitModulo11('123', '0')` returns `{ok: false}` (too
 *       short; minimum 5 digits, mirrors backend `dv_esperado`).
 *   T5: `validarNitModulo11('900.123.456', '<correct-DV>')` returns
 *       `{ok: true}` (different valid NIT — same algorithm, different
 *       digits → different valid DV).
 *   T6: `validarNitModulo11('900123456', '3')` returns `{ok: true}` —
 *       the exact case that discriminated the two variants, pinned to
 *       the backend-confirmed value (not the self-referential helper).
 *
 * No mocks — the function is pure deterministic.
 */
import { describe, it, expect } from 'vitest';

import { validarNitModulo11 } from './nit';

// Helper — recompute the DIAN módulo-11 DV inline (mirrors nit.ts /
// backend exactly) so T5 can pin the "different valid NIT" round-trip
// without baking the answer into the test. T6 additionally pins a
// value confirmed against the REAL backend (not just this helper), so
// a future regression that reintroduces the wrong (self-consistent)
// algorithm in BOTH nit.ts and this helper still gets caught.
function computeDV(nit: string): string {
  const digitsOnly = nit.replace(/\D+/g, '');
  const digits = (digitsOnly.replace(/^0+/, '') || '0').split('').reverse();
  const weights = [71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3];
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    // `weights[i % weights.length]` is always defined because
    // `i < digits.length < ∞` and `weights.length === 15 > 0`;
    // mirrors the same reasoning documented in `nit.ts::validarNitModulo11`.
    const w = weights[i % weights.length]!;
    sum += Number(digits[i]) * w;
  }
  return String(sum % 11);
}

describe('validarNitModulo11 — canonical reference (HU-F8.1 / BR7)', () => {
  it('T1: 800.123.456-7 (canonical reference, dots accepted)', () => {
    const result = validarNitModulo11('800.123.456', '7');
    expect(result.ok).toBe(true);
  });

  it('T2: 800.123.456 with WRONG DV returns {ok:false, dvEsperado:"7"}', () => {
    const result = validarNitModulo11('800.123.456', '1');
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error('expected {ok:false}, got {ok:true}');
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

  it('T6: 900123456 with DV "3" (confirmed against the real backend, not just this helper) → {ok:true}', () => {
    const result = validarNitModulo11('900123456', '3');
    expect(result.ok).toBe(true);
  });

  it('T6b: 900123456 with the OLD (wrong) DV "2" is now correctly rejected', () => {
    const result = validarNitModulo11('900123456', '2');
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error('expected {ok:false}, got {ok:true}');
    expect(result.dvEsperado).toBe('3');
  });
});