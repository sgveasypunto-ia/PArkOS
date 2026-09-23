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

import { formatCOP, formatFechaHoraCorta, formatHoraCorta, formatTiempoTranscurrido } from './format';

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

describe('formatFechaHoraCorta', () => {
  it('F1: ISO con milisegundos + Z → DD/MM/AA HH:mm en TZ Bogotá', () => {
    // 2026-09-23T02:46:50.322102Z → UTC 02:46 → Bogotá (UTC-5) → 21:46
    // del día anterior (22/sep). Si la TZ se respeta bien, debe
    // dar exactamente "22/09/26 21:46" — este es el test del
    // off-by-5h que el operador reportó.
    const result = formatFechaHoraCorta('2026-09-23T02:46:50.322102Z');
    expect(result).toBe('22/09/26 21:46');
  });

  it('F2: ISO naive (sin Z) → trata como UTC, mismo resultado que F1', () => {
    // El backend retorna naive timestamps por el `replace(tzinfo=None)`
    // de Pydantic. El parser interno debe añadir Z para que JS lo
    // parsee como UTC (consistente con F1).
    const result = formatFechaHoraCorta('2026-09-23T02:46:50.322102');
    expect(result).toBe('22/09/26 21:46');
  });

  it('F3: ISO con offset positivo (ej. +05:00) → respeta el offset', () => {
    // 2026-09-23T02:46:50+05:00 → 02:46 en TZ +05 → UTC 21:46 (día
    // anterior) → Bogotá 16:46 del 22/sep.
    const result = formatFechaHoraCorta('2026-09-23T02:46:50+05:00');
    expect(result).toBe('22/09/26 16:46');
  });

  it('F4: ISO con offset negativo (ej. -03:00 Chile) → respeta el offset', () => {
    // 2026-09-23T02:46:50-03:00 → 02:46 en TZ -03 → UTC 05:46 → Bogotá
    // 00:46 del mismo día (23/sep).
    const result = formatFechaHoraCorta('2026-09-23T02:46:50-03:00');
    expect(result).toBe('23/09/26 00:46');
  });

  it('F5: null → "—" (placeholder)', () => {
    expect(formatFechaHoraCorta(null)).toBe('—');
  });

  it('F6: undefined → "—"', () => {
    expect(formatFechaHoraCorta(undefined)).toBe('—');
  });

  it('F7: string vacío → "—"', () => {
    expect(formatFechaHoraCorta('')).toBe('—');
  });

  it('F8: string inválido → "—" (no crashea)', () => {
    expect(formatFechaHoraCorta('not-a-date')).toBe('—');
    expect(formatFechaHoraCorta('2026-13-99T99:99:99Z')).toBe('—');
  });

  it('F9: año se trunca a 2 dígitos (DD/MM/AA no DD/MM/AAAA)', () => {
    const result = formatFechaHoraCorta('2026-09-23T15:30:00Z');
    const parts = result.split(' ')[0]!.split('/');
    expect(parts).toHaveLength(3);
    expect(parts[2]).toHaveLength(2);
    expect(parts[2]).toMatch(/^\d{2}$/);
  });

  it('F10: día y mes con padding a 2 dígitos (zero-pad)', () => {
    // 2026-01-05T08:00:00Z → Bogotá 03:00 del mismo día.
    const result = formatFechaHoraCorta('2026-01-05T08:00:00Z');
    expect(result).toBe('05/01/26 03:00');
    // Shape: day/month son exactamente 2 dígitos.
    expect(result).toMatch(/^0\d\/0\d\/\d{2} \d{2}:\d{2}$/);
  });

  it('F11: cruza medianoche en Bogotá correctamente (UTC 04:00 → Bogotá 23/sep 23:00)', () => {
    // 2026-09-24T04:00:00Z → UTC 04:00 → Bogotá (UTC-5) → 23:00 del 23/sep.
    const result = formatFechaHoraCorta('2026-09-24T04:00:00Z');
    expect(result).toBe('23/09/26 23:00');
  });

  it('F12: cruza medianoche al revés (UTC 02:00 → Bogotá 22/sep 21:00 del día anterior)', () => {
    // 2026-09-23T02:00:00Z → UTC 02:00 → Bogotá (UTC-5) → 21:00 del 22/sep.
    const result = formatFechaHoraCorta('2026-09-23T02:00:00Z');
    expect(result).toBe('22/09/26 21:00');
  });
});

describe('formatHoraCorta', () => {
  it('H1: ISO con Z → HH:mm en TZ Bogotá (UTC-5)', () => {
    // 2026-09-23T02:46:50Z → Bogotá 21:46 del 22/sep.
    const result = formatHoraCorta('2026-09-23T02:46:50Z');
    expect(result).toBe('21:46');
  });

  it('H2: ISO naive → trata como UTC', () => {
    const result = formatHoraCorta('2026-09-23T02:46:50');
    expect(result).toBe('21:46');
  });

  it('H3: cruza medianoche correctamente', () => {
    // 2026-09-24T04:30:00Z → Bogotá 23:30 del 23/sep.
    const result = formatHoraCorta('2026-09-24T04:30:00Z');
    expect(result).toBe('23:30');
  });

  it('H4: null → "—"', () => {
    expect(formatHoraCorta(null)).toBe('—');
  });

  it('H5: undefined → "—"', () => {
    expect(formatHoraCorta(undefined)).toBe('—');
  });

  it('H6: string inválido → "—"', () => {
    expect(formatHoraCorta('not-a-date')).toBe('—');
  });
});