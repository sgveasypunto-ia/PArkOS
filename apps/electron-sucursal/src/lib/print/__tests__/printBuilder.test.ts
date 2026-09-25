/**
 * Unit tests for `printBuilder.ts::buildEntradaPayloadFromResponse()`.
 *
 * BUGFIX (found while wiring the "Tipo: ROTACIÓN/MENSUALIDAD" ticket
 * field, operator request): `esMensualidad` used to be derived from a
 * `cliente !== null` parameter, but both production call sites
 * (`IngresoPanel.tsx` / `Principal.tsx`) ALWAYS passed `cliente=null`
 * ("cliente metadata not threaded into ESC/POS payload yet" — a
 * separate, unfinished feature). The printed tiquete therefore NEVER
 * showed "MENSUALIDAD" in production, regardless of the vehicle's
 * actual subscription. The fix reads `response.tipo_entrada` (the
 * server-derived, authoritative DEC-SUC-21 field) instead; the dead
 * `cliente` parameter was removed from the signature entirely.
 */
import { describe, it, expect } from 'vitest';

import { buildEntradaPayloadFromResponse, buildReimpresionEntradaPayload } from '../printBuilder';
import type { PostIngresoResponse } from '../../../features/operacion/lib/ingresoApi';
import type { Ingreso } from '../../../features/operacion/api/ingresoActivoApi';

function makeResponse(overrides?: Partial<PostIngresoResponse>): PostIngresoResponse {
  return {
    uuid: '00000000-0000-4000-8000-000000000001',
    tipo_entrada: 'ROTACION',
    uuid_subscripcion_cliente: null,
    consecutivo: null,
    ...overrides,
  };
}

describe('buildEntradaPayloadFromResponse — esMensualidad source of truth', () => {
  it('esMensualidad=true when response.tipo_entrada === "MENSUALIDAD"', () => {
    const response = makeResponse({
      tipo_entrada: 'MENSUALIDAD',
      uuid_subscripcion_cliente: '00000000-0000-4000-8000-000000000099',
    });
    const payload = buildEntradaPayloadFromResponse(response, 'ABC123', {});
    expect(payload.esMensualidad).toBe(true);
  });

  it('esMensualidad=false when response.tipo_entrada === "ROTACION"', () => {
    const response = makeResponse({ tipo_entrada: 'ROTACION' });
    const payload = buildEntradaPayloadFromResponse(response, 'ABC123', {});
    expect(payload.esMensualidad).toBe(false);
  });
});

/**
 * HU-F8.3 (directiva del operador 2026-09-25) — reimpresión de tiquete
 * de entrada a partir de un `Ingreso` HISTÓRICO (búsqueda por
 * placa/cupo), no de un `PostIngresoResponse` fresco.
 */
describe('buildReimpresionEntradaPayload', () => {
  function makeIngreso(overrides?: Partial<Ingreso>): Ingreso {
    return {
      uuid: '00000000-0000-4000-8000-000000000001',
      uuid_sucursal: '00000000-0000-4000-8000-000000000002',
      placa: 'ABC123',
      fecha_ingreso: '2026-09-17T10:00:00Z',
      uuid_subscripcion_cliente: null,
      consecutivo: null,
      uuid_tipo_vehiculo: null,
      ...overrides,
    };
  }

  it('builds a con-placa reimpresion payload with the ORIGINAL fecha_ingreso', () => {
    const ingreso = makeIngreso();
    const payload = buildReimpresionEntradaPayload(ingreso, 'Tiquete mojado, ilegible');

    expect(payload.originalTipo).toBe('entrada');
    expect(payload.motivo).toBe('Tiquete mojado, ilegible');
    expect(payload.folioOriginal).toBe(ingreso.uuid);
    expect(payload.payload.variant).toBe('con-placa');
    if (payload.payload.variant === 'con-placa') {
      expect(payload.payload.placa).toBe('ABC123');
    }
    expect(payload.payload.fechaEntrada).toBe(
      new Date(ingreso.fecha_ingreso as string).toISOString(),
    );
  });

  it('builds a con-consecutivo reimpresion payload for a no-placa vehicle', () => {
    const ingreso = makeIngreso({ placa: null, consecutivo: 'BICICLETA-000001-aaaaaaaa' });
    const payload = buildReimpresionEntradaPayload(ingreso, 'Cupo perdido');

    expect(payload.payload.variant).toBe('con-consecutivo');
    if (payload.payload.variant === 'con-consecutivo') {
      expect(payload.payload.consecutivo).toBe('BICICLETA-000001-aaaaaaaa');
      expect(payload.payload.placa).toBeNull();
    }
  });

  it('esMensualidad=true when the historical ingreso carries uuid_subscripcion_cliente', () => {
    const ingreso = makeIngreso({
      uuid_subscripcion_cliente: '00000000-0000-4000-8000-000000000099',
    });
    const payload = buildReimpresionEntradaPayload(ingreso, 'Motivo de prueba valido');
    expect(payload.payload.esMensualidad).toBe(true);
  });
});
