/**
 * Unit tests for `getIngresosByPlaca` + `getIngresoEstado` Zod parsing
 * (HU-F6.1, T2).
 *
 * The contract is purely about Zod validation of the wire shape — we
 * mock `parkosFetch` and assert that valid wire shapes parse and
 * malformed shapes throw. The HTTP behaviour (auth headers, retry,
 * 401 refresh) is exercised by `parkosFetch`'s own test suite; we do
 * NOT re-test it here.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { parkosFetch } from '@parkos/ui-kit/fetch';

import { getIngresoEstado, getIngresosByPlaca } from './ingresoActivoApi';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: vi.fn(),
}));

const mockFetch = parkosFetch as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});

describe('getIngresosByPlaca', () => {
  it('returns parsed Ingreso[] for a valid 200 response', async () => {
    const wire = [
      {
        uuid: '11111111-1111-1111-1111-111111111111',
        uuid_sucursal: '22222222-2222-2222-2222-222222222222',
        placa: 'ABC123',
        fecha_ingreso: '2026-09-17T10:00:00Z',
        uuid_subscripcion_cliente: null,
      },
    ];
    mockFetch.mockResolvedValueOnce(wire);
    const result = await getIngresosByPlaca('ABC123');
    expect(result).toEqual(wire);
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/operacion/ingresos?placa=ABC123',
    );
  });

  it('returns [] for an empty list (valid 200 with [] body)', async () => {
    mockFetch.mockResolvedValueOnce([]);
    const result = await getIngresosByPlaca('ABC999');
    expect(result).toEqual([]);
  });

  it('throws ZodError when the wire shape drops a required field', async () => {
    // Missing `fecha_ingreso` — schema rejects.
    mockFetch.mockResolvedValueOnce([
      {
        uuid: '11111111-1111-1111-1111-111111111111',
        uuid_sucursal: '22222222-2222-2222-2222-222222222222',
        placa: 'ABC123',
        uuid_subscripcion_cliente: null,
      },
    ]);
    await expect(getIngresosByPlaca('ABC123')).rejects.toThrow();
  });

  it('accepts a non-null `uuid_subscripcion_cliente` (mensualidad indicator)', async () => {
    const wire = [
      {
        uuid: '11111111-1111-1111-1111-111111111111',
        uuid_sucursal: '22222222-2222-2222-2222-222222222222',
        placa: 'ABC123',
        fecha_ingreso: '2026-09-17T10:00:00Z',
        uuid_subscripcion_cliente: '33333333-3333-3333-3333-333333333333',
      },
    ];
    mockFetch.mockResolvedValueOnce(wire);
    const result = await getIngresosByPlaca('ABC123');
    expect(result[0]?.uuid_subscripcion_cliente).toBe(
      '33333333-3333-3333-3333-333333333333',
    );
  });
});

describe('getIngresoEstado', () => {
  it('parses a valid abierto estado', async () => {
    mockFetch.mockResolvedValueOnce({
      uuid: '11111111-1111-1111-1111-111111111111',
      estado: 'abierto',
    });
    const result = await getIngresoEstado('11111111-1111-1111-1111-111111111111');
    expect(result.estado).toBe('abierto');
  });

  it('rejects an unknown estado string', async () => {
    mockFetch.mockResolvedValueOnce({
      uuid: '11111111-1111-1111-1111-111111111111',
      estado: 'unknown',
    });
    await expect(
      getIngresoEstado('11111111-1111-1111-1111-111111111111'),
    ).rejects.toThrow();
  });
});
