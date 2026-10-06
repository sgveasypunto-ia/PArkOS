import { describe, expect, it } from 'vitest';

import { ClientesApiError } from '../api/clientesApi';
import { mapRenovacionError, mapVehiculoError } from './errorMessages';

// Plain translate: returns the Spanish fallback with {{vars}} interpolated.
const t = (_key: string, fallback: string, opts?: Record<string, unknown>): string =>
  fallback.replace(/\{\{(\w+)\}\}/g, (_m, k: string) => String(opts?.[k] ?? ''));

function err(status: number, detail: unknown): ClientesApiError {
  const body = JSON.stringify({ detail });
  return new ClientesApiError(`clientesApi: POST /x -> ${status}: ${body.slice(0, 200)}`, status, body);
}

describe('ClientesApiError', () => {
  it('parses detail.error and the extra fields', () => {
    const e = err(409, { error: 'placa_con_suscripcion_activa', placa: 'ABC123' });
    expect(e.status).toBe(409);
    expect(e.code).toBe('placa_con_suscripcion_activa');
    expect(e.detail.placa).toBe('ABC123');
  });

  it('accepts a string detail and survives a non-JSON body', () => {
    expect(err(403, 'permission_denied').code).toBe('permission_denied');
    expect(new ClientesApiError('m', 500, '<html>').code).toBeNull();
  });
});

describe('mapVehiculoError', () => {
  it('409 placa_con_suscripcion_activa names the plate', () => {
    expect(mapVehiculoError(err(409, { error: 'placa_con_suscripcion_activa', placa: 'ABC123' }), t)).toBe(
      'La placa ABC123 ya está en otra suscripción activa de esta sucursal.',
    );
  });

  it('keeps the legacy alias (plain Error with the code in the message)', () => {
    expect(mapVehiculoError(new Error('... 422: {"error": "placa_con_suscripcion_vigente"}'), t)).toMatch(
      /otra suscripción activa/,
    );
  });

  it('maps the rest of the contract', () => {
    expect(mapVehiculoError(err(403, { error: 'permission_denied' }), t)).toMatch(/supervisor/);
    expect(mapVehiculoError(err(400, { error: 'missing_sucursal_context' }), t)).toMatch(/sucursal/);
    expect(mapVehiculoError(err(403, { error: 'unauthorized_sucursal_context' }), t)).toMatch(/acceso/);
    expect(mapVehiculoError(err(404, { error: 'subscripcion_no_encontrada' }), t)).toMatch(/suscripción/);
    expect(mapVehiculoError(err(404, { error: 'vehiculo_no_encontrado' }), t)).toMatch(/vehículo/);
    expect(mapVehiculoError(err(409, { error: 'vehiculo_ya_inscrito' }), t)).toMatch(/ya está inscrito/);
    expect(
      mapVehiculoError(err(422, { error: 'tipo_vehiculo_plan_incompatible', tipo_plan: 'moto' }), t),
    ).toMatch(/\(moto\)/);
    expect(mapVehiculoError(err(422, { error: 'cantidad_vehiculos_excede_plan' }), t)).toMatch(/cantidad máxima/);
    expect(mapVehiculoError(err(422, { error: 'cantidad_maxima_excedida' }), t)).toMatch(/cantidad máxima/);
    expect(mapVehiculoError(err(422, { error: 'tipo_vehiculo_mixto_no_permitido' }), t)).toMatch(/mismo tipo/);
    expect(mapVehiculoError(err(422, { error: 'tipo_vehiculo_incompatible' }), t)).toMatch(/mismo tipo/);
  });

  it('falls back to a generic message for unknown errors', () => {
    expect(mapVehiculoError(new Error('boom'), t)).toBe('No se pudo agregar el vehículo.');
  });
});

describe('mapRenovacionError', () => {
  it('renovacion_fuera_de_ventana interpolates dias_restantes and ventana_dias', () => {
    const msg = mapRenovacionError(
      err(409, { error: 'renovacion_fuera_de_ventana', dias_restantes: 25, ventana_dias: 10 }),
      t,
    );
    expect(msg).toMatch(/25 días/);
    expect(msg).toMatch(/10 días o menos/);
  });

  it.each([
    ['idempotency_key_requerido', /intento de renovación/],
    ['voucher_requerido', /voucher/],
    ['suscripcion_no_renovable', /no se puede renovar/],
    ['plan_no_vigente', /plan.*no está vigente/],
    ['idempotency_key_conflict', /ya fue procesado/],
    ['suscripcion_sin_vehiculos', /no tiene vehículos/],
    ['vehiculo_no_resuelto', /resolver/],
    ['placa_con_suscripcion_vigente', /otra suscripción vigente/],
    ['plan_duracion_dias_invalido', /duración válida/],
    ['iva_no_configurado', /IVA/],
    ['permission_denied', /permiso/],
    ['missing_sucursal_context', /sucursal/],
    ['subscripcion_no_encontrada', /no existe/],
    ['cantidad_maxima_excedida', /cantidad máxima/],
    ['tipo_vehiculo_incompatible', /mismo tipo/],
  ])('maps %s', (code, pattern) => {
    expect(mapRenovacionError(err(400, { error: code }), t)).toMatch(pattern);
  });

  it('falls back to a generic renewal error', () => {
    expect(mapRenovacionError(new Error('boom'), t)).toMatch(/No se pudo renovar/);
  });
});
