import { describe, expect, it } from 'vitest';

import { desglosarIvaIncluido } from './ivaIncluido';

describe('desglosarIvaIncluido', () => {
  it('120000 al 19% => base 100840.34 + IVA 19159.66 = 120000', () => {
    expect(desglosarIvaIncluido(120000, 0.19)).toEqual({
      base: 100840.34,
      iva: 19159.66,
      total: 120000,
    });
  });

  it('base + iva == total exacto (centavos)', () => {
    for (const total of [1, 999.99, 30000, 100000, 1234567.89]) {
      const d = desglosarIvaIncluido(total, 0.19);
      expect(Math.round((d.base + d.iva) * 100)).toBe(Math.round(total * 100));
    }
  });

  it('IVA 0 no grava', () => {
    expect(desglosarIvaIncluido(50000, 0)).toEqual({ base: 50000, iva: 0, total: 50000 });
  });
});
