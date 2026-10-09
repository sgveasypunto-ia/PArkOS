import { describe, expect, it } from 'vitest';
import { calcularFechaFinCobertura, formatFechaCO } from './vigencia';

describe('calcularFechaFinCobertura (regla del backend: inicio + duracion_dias - 1)', () => {
  it('plan de 30 dias cubre exactamente 30 dias calendario', () => {
    expect(calcularFechaFinCobertura('2026-10-01', 30)).toBe('2026-10-30');
  });
  it('cruza fin de mes y de anio', () => {
    expect(calcularFechaFinCobertura('2026-12-15', 60)).toBe('2027-02-12');
  });
  it('respeta anio bisiesto', () => {
    expect(calcularFechaFinCobertura('2028-02-01', 30)).toBe('2028-03-01');
  });
  it('plan de 1 dia termina el mismo dia', () => {
    expect(calcularFechaFinCobertura('2026-10-09', 1)).toBe('2026-10-09');
  });
  it('duracion invalida devuelve null', () => {
    expect(calcularFechaFinCobertura('2026-10-09', 0)).toBeNull();
    expect(calcularFechaFinCobertura('no-es-fecha', 30)).toBeNull();
  });
});

describe('formatFechaCO', () => {
  it('formatea YYYY-MM-DD como dd/mm/aaaa', () => {
    expect(formatFechaCO('2026-10-09')).toBe('09/10/2026');
  });
});
