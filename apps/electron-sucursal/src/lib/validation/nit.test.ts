/**
 * DIAN RUT/NIT módulo-11 verification digit (DV) — official algorithm:
 * weights `3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71`
 * applied from the RIGHTMOST digit leftwards, `r = sum % 11`,
 * `DV = r` when `r` is 0 or 1, else `11 - r`. Mirrors backend
 * `repo/nit_modulo11.py` and `web_admin/src/lib/validation/nit.ts`.
 *
 * The previous implementation (weights reversed, `DV = sum % 11`)
 * agreed with real NITs only by chance. The real institutional pairs
 * below pin the official behaviour.
 */
import { describe, it, expect } from 'vitest';

import { validarNitModulo11 } from './nit';

const REAL_NITS: ReadonlyArray<readonly [string, string]> = [
  ['899999068', '1'], // Ecopetrol
  ['890903938', '8'], // Bancolombia
  ['860034313', '7'], // Davivienda
  ['800197268', '4'], // DIAN
  ['860002964', '4'], // Banco de Bogotá
  ['890900608', '9'], // Almacenes Éxito
];

describe('validarNitModulo11 — official DIAN algorithm', () => {
  it.each(REAL_NITS)('real NIT %s-%s is accepted', (nit, dv) => {
    expect(validarNitModulo11(nit, dv)).toEqual({ ok: true });
  });

  it.each(REAL_NITS)('real NIT %s rejects a wrong DV and reports the right one', (nit, dv) => {
    const wrong = String((Number(dv) + 1) % 10);
    const result = validarNitModulo11(nit, wrong);
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error('expected {ok:false}');
    expect(result.dvEsperado).toBe(dv);
  });

  it('900123456 has DV 8 (the old algorithm said 3)', () => {
    expect(validarNitModulo11('900.123.456', '8')).toEqual({ ok: true });
    const old = validarNitModulo11('900123456', '3');
    expect(old.ok).toBe(false);
    if (old.ok) throw new Error('expected {ok:false}');
    expect(old.dvEsperado).toBe('8');
  });

  it('800.123.456 has DV 5 (formatted input accepted)', () => {
    expect(validarNitModulo11('800.123.456', '5')).toEqual({ ok: true });
    expect(validarNitModulo11('800123456', '7').ok).toBe(false);
  });

  it('remainder 0 and 1 map to DV 0 and 1; remainder 10 maps to DV 1', () => {
    const seen = new Map<string, string>();
    for (let n = 10000; n < 14000; n++) {
      const body = String(n);
      const probe = validarNitModulo11(body, 'x');
      if (probe.ok) throw new Error('unexpected ok');
      const dv = probe.dvEsperado!;
      expect(Number(dv)).toBeLessThanOrEqual(9);
      if (!seen.has(dv)) seen.set(dv, body);
    }
    expect(seen.has('0')).toBe(true);
    expect(seen.has('1')).toBe(true);
    for (const [dv, body] of seen) {
      expect(validarNitModulo11(body, dv)).toEqual({ ok: true });
    }
  });

  it('leading zeros do not change the DV', () => {
    expect(validarNitModulo11('000899999068', '1')).toEqual({ ok: true });
  });

  it('NIT shorter than 5 digits is rejected without a DV hint', () => {
    expect(validarNitModulo11('123', '0')).toEqual({ ok: false });
  });

  it('non-numeric or multi-digit DV is rejected with the expected DV', () => {
    const r = validarNitModulo11('899999068', '10');
    expect(r.ok).toBe(false);
    if (r.ok) throw new Error('expected {ok:false}');
    expect(r.dvEsperado).toBe('1');
    expect(validarNitModulo11('899999068', 'a').ok).toBe(false);
  });

  it('NIT longer than 15 digits cycles the weights', () => {
    const body = '1234567890123456';
    const w = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71];
    const sum = body
      .split('')
      .reverse()
      .reduce((acc, d, i) => acc + Number(d) * w[i % 15]!, 0);
    const r = sum % 11;
    const expected = String(r < 2 ? r : 11 - r);
    expect(validarNitModulo11(body, expected)).toEqual({ ok: true });
  });
});
