/**
 * Pure helpers of the suscripciones feature:
 *   - `cuposErrorMessage` (PT-2): every backend error -> clear es-CO message.
 *   - `clienteEstandar` (TRANSVERSAL): "Consumidor final" never listed/searched.
 */
import { describe, expect, it } from 'vitest';

import {
  CuposCantidadMaximaError,
  CuposContextoSucursalError,
  CuposPermisoDenegadoError,
  CuposPlacaConSuscripcionActivaError,
  CuposSubscripcionNoEncontradaError,
  CuposTipoIncompatibleError,
  CuposTipoPlanIncompatibleError,
  CuposVehiculoInscritoNoEncontradoError,
  CuposVehiculoYaInscritoError,
  mapCuposHttpError,
} from '../hooks/cuposErrors';
import { esClienteEstandar, excluirClienteEstandar } from './clienteEstandar';
import { cuposErrorMessage } from './cuposErrorMessage';

// Same behavior as the real `t` with a defaultValue and no resources loaded.
const t = (_key: string, opts?: Record<string, unknown>): string =>
  String(opts?.defaultValue ?? _key);

describe('cuposErrorMessage (PT-2)', () => {
  const cases: Array<[string, unknown, RegExp]> = [
    ['permission_denied', new CuposPermisoDenegadoError(), /supervisor/i],
    ['400 missing_sucursal_context', new CuposContextoSucursalError(400, 'missing_sucursal_context'), /sucursal/i],
    ['403 unauthorized_sucursal_context', new CuposContextoSucursalError(403, 'unauthorized_sucursal_context'), /acceso/i],
    ['subscripcion_no_encontrada', new CuposSubscripcionNoEncontradaError(), /ya no está activa/i],
    ['vehiculo_inscrito_no_encontrado', new CuposVehiculoInscritoNoEncontradoError(), /ya no está inscrito/i],
    ['vehiculo_ya_inscrito', new CuposVehiculoYaInscritoError('ABC123'), /ABC123.*ya está inscrita/i],
    ['placa_con_suscripcion_activa', new CuposPlacaConSuscripcionActivaError('ZZZ999', 'x'), /ZZZ999.*otra suscripción activa/i],
    ['tipo_vehiculo_plan_incompatible', new CuposTipoPlanIncompatibleError('moto', ['carro']), /moto.*carro/i],
    ['tipo_vehiculo_incompatible', new CuposTipoIncompatibleError(['a']), /mismo tipo/i],
    ['cantidad_maxima_excedida', new CuposCantidadMaximaError(2), /cantidad máxima/i],
  ];

  it.each(cases)('%s -> readable Spanish message (not the raw code)', (_name, err, rx) => {
    const msg = cuposErrorMessage(err, t);
    expect(msg).toMatch(rx);
    expect(msg).not.toMatch(/^[a-z_]+$/);
  });

  it('unknown errors fall back to a generic message', () => {
    expect(cuposErrorMessage(new Error('boom'), t)).toMatch(/No se pudo completar/);
  });
});

describe('mapCuposHttpError', () => {
  it('maps status+code pairs and ignores mismatched ones', () => {
    const body = (error: string, extra: object = {}): string => JSON.stringify({ detail: { error, ...extra } });
    expect(mapCuposHttpError(403, body('permission_denied'))).toBeInstanceOf(CuposPermisoDenegadoError);
    expect(mapCuposHttpError(409, body('placa_con_suscripcion_activa', { placa: 'AAA111' }))).toBeInstanceOf(
      CuposPlacaConSuscripcionActivaError,
    );
    // code with the wrong status is NOT a business error
    expect(mapCuposHttpError(500, body('permission_denied'))).toBeNull();
    expect(mapCuposHttpError(400, 'not json')).toBeNull();
    expect(mapCuposHttpError(400, JSON.stringify({ detail: 'plain text' }))).toBeNull();
  });
});

describe('clienteEstandar', () => {
  it('detects the standard customer by document or by name', () => {
    expect(esClienteEstandar({ numero_identificacion: '222222222222' })).toBe(true);
    expect(esClienteEstandar({ numero_identificacion: '222.222.222.222' })).toBe(true);
    // a real client merely NAMED like it is not hidden
    expect(esClienteEstandar({ numero_identificacion: '900123456', nombre: 'Consumidor', apellido: 'final' })).toBe(false);
    expect(esClienteEstandar({ numero_identificacion: '900123456', nombre: 'ACME' })).toBe(false);
    expect(esClienteEstandar(null)).toBe(false);
  });

  it('excluirClienteEstandar removes it from client-bearing rows', () => {
    const rows = [
      { id: 1, cliente: { numero_identificacion: '222222222222' } },
      { id: 2, cliente: { numero_identificacion: '900123456' } },
    ];
    expect(excluirClienteEstandar(rows).map((r) => r.id)).toEqual([2]);
  });
});

import { coincideBusqueda, normalizarBusqueda } from './busquedaSuscripcion';

describe('busquedaSuscripcion (defecto 7.5)', () => {
  it('normaliza mayúsculas, acentos y espacios', () => {
    expect(normalizarBusqueda('  JOSÉ Núñez ')).toBe('jose nunez');
  });
  it('coincide por nombre completo, apellido o identificación', () => {
    const c = { nombre: 'Juan', apellido: 'Pérez', numero_identificacion: '1001' };
    expect(coincideBusqueda(c, 'juan')).toBe(true);
    expect(coincideBusqueda(c, 'PEREZ')).toBe(true);
    expect(coincideBusqueda(c, 'juan perez')).toBe(true);
    expect(coincideBusqueda(c, '100')).toBe(true);
    expect(coincideBusqueda(c, 'maria')).toBe(false);
    expect(coincideBusqueda(c, '   ')).toBe(true);
  });
  it('tolera nulos', () => {
    expect(coincideBusqueda({ nombre: null, apellido: null, numero_identificacion: null }, 'x')).toBe(false);
  });
});
