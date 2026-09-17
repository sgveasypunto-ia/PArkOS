/**
 * Unit tests for `format.ts` helpers (F3.3 — T1).
 *
 * U1: formatCOP(50000) → "$ 50.000" (es-CO, 0 decimales).
 * U2: formatCOP(0) → "$ 0".
 * U2-plan: formatCOP(8000) → "$ 8.000" (F4.2 plan.md T2 verbatim literal).
 * U2b: formatCOP(1234567) → "$ 1.234.567".
 * U3: formatTiempoTranscurrido(fecha hace 30s) → "recién".
 * U4: formatTiempoTranscurrido(fecha hace 5min) → "hace 5 minutos".
 * U5: formatTiempoTranscurrido(fecha hace 2h) → "hace 2 horas".
 * U6: formatTiempoTranscurrido(fecha hace 3d) → "hace 3 días".
 */
import { describe, it, expect, vi } from 'vitest';

import { formatCOP, formatTiempoTranscurrido } from './format';

describe('formatCOP', () => {
  it('U1: formatea 50000 como "$ 50.000" (es-CO, 0 decimales)', () => {
    const result = formatCOP(50000);
    // es-CO Intl uses non-breaking space between $ and number on some platforms;
    // accept any whitespace separator.
    expect(result.replace(/\s/g, ' ')).toMatch(/^\$\s?50\.000$/);
  });

  it('U2: formatCOP(0) → "$ 0"', () => {
    const result = formatCOP(0);
    expect(result.replace(/\s/g, ' ')).toMatch(/^\$\s?0$/);
  });

  it('U2-plan: formatCOP(8000) → "$ 8.000" (F4.2 plan.md T2 verbatim fixture)', () => {
    const result = formatCOP(8000);
    // es-CO Intl uses non-breaking space between $ and number on some platforms;
    // accept any whitespace separator.
    expect(result.replace(/\s/g, ' ')).toMatch(/^\$\s?8\.000$/);
  });

  it('U2b: formatCOP(1234567) → "$ 1.234.567"', () => {
    const result = formatCOP(1234567);
    expect(result.replace(/\s/g, ' ')).toMatch(/^\$\s?1\.234\.567$/);
  });
});

describe('formatTiempoTranscurrido', () => {
  it('U3: fecha hace 30s → "recién"', () => {
    const hace30s = new Date(Date.now() - 30 * 1000);
    expect(formatTiempoTranscurrido(hace30s)).toBe('recién');
  });

  it('U4: fecha hace 5min → "hace 5 minutos"', () => {
    const hace5min = new Date(Date.now() - 5 * 60 * 1000);
    expect(formatTiempoTranscurrido(hace5min)).toBe('hace 5 minutos');
  });

  it('U4b: fecha hace 1min → "hace 1 minuto" (singular)', () => {
    const hace1min = new Date(Date.now() - 1 * 60 * 1000);
    expect(formatTiempoTranscurrido(hace1min)).toBe('hace 1 minuto');
  });

  it('U5: fecha hace 2h → "hace 2 horas"', () => {
    const hace2h = new Date(Date.now() - 2 * 60 * 60 * 1000);
    expect(formatTiempoTranscurrido(hace2h)).toBe('hace 2 horas');
  });

  it('U5b: fecha hace 1h → "hace 1 hora" (singular)', () => {
    const hace1h = new Date(Date.now() - 60 * 60 * 1000);
    expect(formatTiempoTranscurrido(hace1h)).toBe('hace 1 hora');
  });

  it('U6: fecha hace 3d → "hace 3 días"', () => {
    const hace3d = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000);
    expect(formatTiempoTranscurrido(hace3d)).toBe('hace 3 días');
  });

  it('U6b: fecha hace 1d → "hace 1 día" (singular)', () => {
    const hace1d = new Date(Date.now() - 24 * 60 * 60 * 1000);
    expect(formatTiempoTranscurrido(hace1d)).toBe('hace 1 día');
  });

  it('acepta string ISO 8601', () => {
    const hace5min = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatTiempoTranscurrido(hace5min)).toBe('hace 5 minutos');
  });

  it('fecha futura (clock skew) → "recién" (no negativo)', () => {
    const futuro = new Date(Date.now() + 30 * 1000);
    expect(formatTiempoTranscurrido(futuro)).toBe('recién');
  });
});

// Ensure vi import is not pruned (used by potential future cases).
void vi;