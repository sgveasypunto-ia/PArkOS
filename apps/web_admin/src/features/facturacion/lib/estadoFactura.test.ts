/**
 * `estadoFactura.test.ts` — unit tests for the `deriveEstadoFactura`
 * heuristic (REQ-X-02 MVP shim).
 *
 * The MVP heuristic: if the most-recent log row for the factura has
 * `accion === 'anular'` AND `tabla_afectada === 'anulaciones'`, state
 * is `anulada`; otherwise `vigente`. When the BE exposes
 * `V_FACTURA_ESTADO` as a real endpoint, this shim is removed.
 */
import { describe, expect, it } from 'vitest';
import { deriveEstadoFactura, FACTURA_ESTADOS } from './estadoFactura';
import type { LogTransaccionalItem } from '../api/facturacionAdminSchema';

function row(overrides: Partial<LogTransaccionalItem>): LogTransaccionalItem {
  return {
    uuid: '00000000-0000-0000-0000-000000000000',
    timestamp_evento: '2026-10-13T00:00:00',
    uuid_usuario: null,
    uuid_sucursal: null,
    uuid_referencia: null,
    accion: 'login',
    tabla_afectada: 'login',
    hash_anterior: null,
    hash_actual: 'aaaa',
    ...overrides,
  };
}

describe('deriveEstadoFactura', () => {
  it('returns "vigente" for an empty list', () => {
    expect(deriveEstadoFactura([])).toBe('vigente');
  });

  it('returns "vigente" when the head row is a non-anular action', () => {
    expect(
      deriveEstadoFactura([
        row({ accion: 'crear', tabla_afectada: 'facturas' }),
        row({ accion: 'login' }),
      ]),
    ).toBe('vigente');
  });

  it('returns "anulada" when the head row matches the anular signature', () => {
    expect(
      deriveEstadoFactura([
        row({ accion: 'anular', tabla_afectada: 'anulaciones' }),
        row({ accion: 'crear', tabla_afectada: 'facturas' }),
      ]),
    ).toBe('anulada');
  });

  it('returns "vigente" when accion="anular" but tabla_afectada is unrelated', () => {
    // Defensive: the `anular` accion is only meaningful on the
    // `anulaciones` workflow table. Other tables that happen to carry
    // an "anular" string don't count.
    expect(
      deriveEstadoFactura([
        row({ accion: 'anular', tabla_afectada: 'facturas' }),
      ]),
    ).toBe('vigente');
  });

  it('FACTURA_ESTADOS exposes the closed enum', () => {
    expect(FACTURA_ESTADOS).toEqual(['vigente', 'anulada']);
  });
});
