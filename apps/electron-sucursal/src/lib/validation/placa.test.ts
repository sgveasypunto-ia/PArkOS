/**
 * Unit tests for `detectarTipoVehiculo()` (HU-F4.1, T1).
 *
 * Cobertura U1..U6 verbatim `plan.md:1381` (precedente F2.x `formatCOP` +
 * F4.2 plan.md:1416 — función pura reusable, misma estrategia):
 *   U1: placa válida Auto (`ABC123`) → `'Auto'`.
 *   U2: placa válida Moto (`ABC12D`) → `'Moto'`.
 *   U3: formato inválido (`ABCD12`) → `null`.
 *   U4: placa vacía (`''`) → `null`.
 *   U5: minúsculas (`abc123`) → `'Auto'` (normalización via `toUpperCase`).
 *   U6: placa con espacios (`'  ABC123  '`) → `'Auto'` (normalización via
 *       `trim()` + `replace(/\s+/g, '')`).
 *
 * Plus 2 tests de constantes exportadas — DRY contract F6.1 Zod validation:
 *   U7: `REGEX_AUTO` matchea `ABC123`.
 *   U8: `REGEX_MOTO` matchea `ABC12D`.
 *
 * No requiere mocks — la función es pura determinista.
 */
import { describe, it, expect } from 'vitest';

import { detectarTipoVehiculo, REGEX_AUTO, REGEX_MOTO } from './placa';

describe('detectarTipoVehiculo', () => {
  it('U1: ABC123 → Auto (happy path Auto)', () => {
    expect(detectarTipoVehiculo('ABC123')).toBe('carro');
  });

  it('U2: ABC12D → moto (happy path moto)', () => {
    expect(detectarTipoVehiculo('ABC12D')).toBe('moto');
  });

  it('U3: ABCD12 → null (formato inválido, 4 letras + 2 dígitos)', () => {
    expect(detectarTipoVehiculo('ABCD12')).toBeNull();
  });

  it('U4: "" → null (placa vacía)', () => {
    expect(detectarTipoVehiculo('')).toBeNull();
  });

  it('U5: abc123 → Auto (minúsculas normalizadas vía toUpperCase)', () => {
expect(detectarTipoVehiculo('abc123')).toBe('carro');
  });

  it('U6: placa con espacios (\'  ABC123  \') → \'carro\' (normalización via', () => {
    expect(detectarTipoVehiculo('  ABC123  ')).toBe('carro');
  });
});

describe('regex constants exported (DRY contract F6.1 Zod validation)', () => {
  it('U7: REGEX_AUTO matchea ABC123', () => {
    expect(REGEX_AUTO.test('ABC123')).toBe(true);
  });

  it('U8: REGEX_MOTO matchea ABC12D', () => {
    expect(REGEX_MOTO.test('ABC12D')).toBe(true);
  });
});
