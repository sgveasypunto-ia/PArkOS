import { describe, expect, it } from 'vitest';

import { formatTarifaValor, TARIFA_VACIO } from './formatTarifaValor';

describe('formatTarifaValor', () => {
  it('strips the four wire decimals and groups thousands (es-CO)', () => {
    expect(formatTarifaValor('1000.0000')).toBe('1.000');
    expect(formatTarifaValor('1500.0000')).toBe('1.500');
    expect(formatTarifaValor('2000.0000')).toBe('2.000');
  });

  it('groups every magnitude', () => {
    expect(formatTarifaValor('10000.0000')).toBe('10.000');
    expect(formatTarifaValor('1000000.0000')).toBe('1.000.000');
    expect(formatTarifaValor('999.0000')).toBe('999');
    expect(formatTarifaValor('0.0000')).toBe('0');
  });

  it('rounds a real fractional amount to whole pesos', () => {
    expect(formatTarifaValor('1500.5000')).toBe('1.501');
    expect(formatTarifaValor('0.5000')).toBe('1');
    expect(formatTarifaValor('0.4000')).toBe('0');
  });

  it('returns the em-dash marker for empty values', () => {
    expect(formatTarifaValor(null)).toBe(TARIFA_VACIO);
    expect(formatTarifaValor(undefined)).toBe(TARIFA_VACIO);
    expect(formatTarifaValor('')).toBe(TARIFA_VACIO);
  });

  it('passes non-numeric garbage through so it stays visible', () => {
    expect(formatTarifaValor('N/A')).toBe('N/A');
  });
});
