/**
 * Unit tests for `validarIdentificacion()` (persona natural / empresa
 * extension of HU-F8.1).
 *
 * No mocks — pure deterministic dispatcher over `validarNitModulo11`
 * (NIT) + format-only checks (CC / CE / pasaporte, sin dígito de
 * verificación — Colombia no tiene DV para cédula).
 */
import { describe, it, expect } from 'vitest';

import { validarIdentificacion } from './identificacion';

describe('validarIdentificacion — NIT delega en validarNitModulo11', () => {
  it('NIT válido (referencia canónica 800.123.456-7)', () => {
    expect(validarIdentificacion('NIT', '800.123.456', '7')).toEqual({ ok: true });
  });

  it('NIT con DV incorrecto propaga dvEsperado', () => {
    const result = validarIdentificacion('NIT', '800.123.456', '1');
    expect(result.ok).toBe(false);
    expect(result).toMatchObject({ dvEsperado: '7' });
  });
});

describe('validarIdentificacion — CC (solo formato, sin DV)', () => {
  it('CC de 10 dígitos es válida', () => {
    expect(validarIdentificacion('CC', '1020304050')).toEqual({ ok: true });
  });

  it('CC de 6 dígitos (mínimo) es válida', () => {
    expect(validarIdentificacion('CC', '123456')).toEqual({ ok: true });
  });

  it('CC con letras es inválida', () => {
    const result = validarIdentificacion('CC', '10A0304050');
    expect(result.ok).toBe(false);
  });

  it('CC demasiado corta es inválida', () => {
    const result = validarIdentificacion('CC', '123');
    expect(result.ok).toBe(false);
  });
});

describe('validarIdentificacion — CE / pasaporte (alfanumérico, sin DV)', () => {
  it('CE alfanumérica es válida', () => {
    expect(validarIdentificacion('CE', 'AB1234567')).toEqual({ ok: true });
  });

  it('pasaporte alfanumérico es válido', () => {
    expect(validarIdentificacion('pasaporte', 'PA1234567')).toEqual({ ok: true });
  });

  it('pasaporte con caracteres especiales es inválido', () => {
    const result = validarIdentificacion('pasaporte', 'AB-123');
    expect(result.ok).toBe(false);
  });
});
