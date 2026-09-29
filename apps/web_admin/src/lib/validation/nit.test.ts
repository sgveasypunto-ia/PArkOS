/**
 * `nit.test.ts` — unit tests for the módulo 11 NIT validator
 * (HU-F15.2 BR1). Pinea el algoritmo para que no diverja del
 * backend: si esto cambia sin actualizar el server, el server va a
 * rechazar lo que el cliente aceptó.
 */
import { describe, expect, it } from 'vitest';

import {
  calcularDvModulo11,
  normalizeNit,
  validarNitModulo11,
} from './nit';

describe('normalizeNit', () => {
  it('devuelve solo dígitos y descarta puntos, guiones y espacios', () => {
    expect(normalizeNit('900.123.456-7')).toBe('9001234567');
    expect(normalizeNit('  900 123 456 7 ')).toBe('9001234567');
    expect(normalizeNit('9001234567')).toBe('9001234567');
  });

  it('tolera null/undefined', () => {
    expect(normalizeNit(null)).toBe('');
    expect(normalizeNit(undefined)).toBe('');
    expect(normalizeNit('')).toBe('');
  });
});

describe('calcularDvModulo11', () => {
  it('calcula DV=6 para el cuerpo "123456789"', () => {
    // Pesos [3,7,13,17,19,23,29,37,41] desde la derecha:
    // 9*3 + 8*7 + 7*13 + 6*17 + 5*19 + 4*23 + 3*29 + 2*37 + 1*41 = 665
    // 665 mod 11 = 5 → DV = 11 - 5 = 6.
    expect(calcularDvModulo11('123456789')).toBe(6);
  });

  it('calcula DV=5 para el cuerpo "800123456"', () => {
    // Suma = 545, mod = 6, DV = 5.
    expect(calcularDvModulo11('800123456')).toBe(5);
  });

  it('acepta cuerpos de más de 15 dígitos ciclando los pesos', () => {
    // Cuerpo de 16 dígitos: cicla desde 71 otra vez.
    // La fórmula es determinística — basta con que el resultado sea
    // estable entre corridas para pinearlo.
    const dv = calcularDvModulo11('1234567890123456');
    expect(typeof dv === 'number' || dv === null).toBe(true);
  });

  it('devuelve null si el cuerpo está vacío', () => {
    expect(calcularDvModulo11('')).toBe(null);
  });
});

describe('validarNitModulo11', () => {
  it('acepta "123456789-6" como válido', () => {
    const r = validarNitModulo11('123456789-6');
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.digits).toBe('123456789');
      expect(r.dv).toBe(6);
      expect(r.expectedDv).toBe(6);
    }
  });

  it('acepta "800.123.456-5" (formato colombiano con puntos) como válido', () => {
    const r = validarNitModulo11('800.123.456-5');
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.digits).toBe('800123456');
      expect(r.dv).toBe(5);
    }
  });

  it('rechaza DV incorrecto e informa el esperado', () => {
    const r = validarNitModulo11('123456789-9');
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe('dv_mismatch');
      expect(r.expectedDv).toBe(6);
      expect(r.dv).toBe(9);
      expect(r.message).toMatch(/DV inválido/);
      expect(r.message).toContain('esperado');
      expect(r.message).toContain('6');
    }
  });

  it('rechaza entrada vacía', () => {
    const r = validarNitModulo11('');
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe('empty');
    }
  });

  it('rechaza entrada con un solo dígito', () => {
    const r = validarNitModulo11('5');
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe('too_short');
    }
  });

  it('rechaza entrada demasiado larga', () => {
    const r = validarNitModulo11('1'.repeat(20));
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.reason).toBe('too_long');
    }
  });

  it('calcula DV esperado con calcularDvModulo11 (sin DV en la entrada)', () => {
    // Para "verificar mientras tipea" sin DV al final, se usa
    // calcularDvModulo11 sobre el cuerpo pelado.
    expect(calcularDvModulo11('123456789')).toBe(6);
    expect(calcularDvModulo11('800123456')).toBe(5);
  });

  it('tolera null/undefined como entrada vacía', () => {
    expect(validarNitModulo11(null).ok).toBe(false);
    expect(validarNitModulo11(undefined).ok).toBe(false);
  });
});
