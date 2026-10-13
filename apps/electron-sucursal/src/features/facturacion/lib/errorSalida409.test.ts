import { describe, it, expect } from 'vitest';
import { leerErrorSalida409 } from './errorSalida409';

const httpError = (status: number, body: unknown) =>
  Object.assign(new Error('http'), { status, body: JSON.stringify(body) });

describe('leerErrorSalida409', () => {
  it('reconoce salida_anulada', () => {
    expect(leerErrorSalida409(httpError(409, { detail: { error: 'salida_anulada' } }))).toBe(
      'salida_anulada',
    );
  });
  it('reconoce salida_ya_pagada', () => {
    expect(leerErrorSalida409(httpError(409, { detail: { error: 'salida_ya_pagada' } }))).toBe(
      'salida_ya_pagada',
    );
  });
  it('ignora otros códigos, otros status y no-errores', () => {
    expect(leerErrorSalida409(httpError(409, { detail: { error: 'salida_ya_anulada' } }))).toBeNull();
    expect(leerErrorSalida409(httpError(422, { detail: { error: 'salida_anulada' } }))).toBeNull();
    expect(leerErrorSalida409(new Error('x'))).toBeNull();
    expect(leerErrorSalida409(null)).toBeNull();
  });
});
