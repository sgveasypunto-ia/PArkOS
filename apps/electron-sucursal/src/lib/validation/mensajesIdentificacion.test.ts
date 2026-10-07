import { describe, it, expect } from 'vitest';

import { mensajeIdentificacion } from './mensajesIdentificacion';

describe('mensajeIdentificacion', () => {
  it.each([
    'dv_invalido',
    'dv_requerido',
    'numero_identificacion_requerido',
    'documento_min_5',
    'cc_formato_invalido',
    'documento_formato_invalido',
    'nombre_requerido',
    'apellido_requerido',
  ])('traduce %s a un mensaje en español sin el código crudo', (codigo) => {
    const msg = mensajeIdentificacion(codigo);
    expect(msg).not.toBe(codigo);
    expect(msg).not.toMatch(/_/);
  });

  it('deja pasar un texto desconocido y tolera vacíos', () => {
    expect(mensajeIdentificacion('Texto libre')).toBe('Texto libre');
    expect(mensajeIdentificacion(null)).toBeUndefined();
    expect(mensajeIdentificacion(undefined)).toBeUndefined();
  });
});
