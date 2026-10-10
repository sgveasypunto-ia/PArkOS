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
    // AUD3: placa / cantidad de la venta de suscripción y ingreso/salida
    'placa_formato_invalido',
    'placa_tipo_incompatible',
    'placas_cantidad_invalida',
    'placa_duplicada_en_venta',
    'validation.cantidad.min_1',
    'validation.cantidad.max_excedida',
    'validation.number.required',
    'ingreso_sin_placa_tipo_requerido',
    'email_formato_invalido',
  ])('traduce %s a un mensaje en español sin el código crudo', (codigo) => {
    const msg = mensajeIdentificacion(codigo);
    expect(msg).not.toBe(codigo);
    expect(msg).not.toMatch(/_|validation\./);
  });

  it('deja pasar un texto desconocido y tolera vacíos', () => {
    expect(mensajeIdentificacion('Texto libre')).toBe('Texto libre');
    expect(mensajeIdentificacion(null)).toBeUndefined();
    expect(mensajeIdentificacion(undefined)).toBeUndefined();
  });
});
