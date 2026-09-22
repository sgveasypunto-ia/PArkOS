/**
 * Tests for `tiposVehiculoApi.ts` — REGRESSION test for the pagination-unwrap
 * bug discovered in PR-B smoke test (2026-09-22).
 *
 * Before the fix: `parkosFetch<TipoVehiculo[]>` assumed a flat array; the
 * backend actually returns `{items: TipoVehiculo[], next_cursor: string | null}`
 * (paginated cursor shape per `ReadListBase<T>` in `schemas/common.py`).
 * The previous code then ran `raw.filter(...)` over the object — which
 * returned `[]` — and `useTiposVehiculo` ended up with no data, breaking
 * `<IngresoSinPlacaPanel />` (HU-INGRESO-SIN-PLACA).
 *
 * After the fix: `getTiposVehiculo()` defensively unwraps either shape.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';

import { getTiposVehiculo } from './tiposVehiculoApi';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: vi.fn(),
  ParkosHttpError: class ParkosHttpError extends Error {
    constructor(
      public status: number,
      message: string,
      public path?: string,
    ) {
      super(message);
      this.name = 'ParkosHttpError';
    }
  },
}));

const mockParkosFetch = vi.mocked(parkosFetch);

const sampleCarro = {
  uuid: '11111111-1111-1111-1111-111111111111',
  tipo: 'carro',
  vigente_desde: '2026-01-01T00:00:00Z',
  vigente_hasta: null,
  estado: 'activo',
};

const sampleBici = {
  uuid: '22222222-2222-2222-2222-222222222222',
  tipo: 'bicicleta',
  vigente_desde: '2026-01-01T00:00:00Z',
  vigente_hasta: null,
  estado: 'activo',
};

const sampleNullTipo = {
  uuid: '33333333-3333-3333-3333-333333333333',
  tipo: null,
  vigente_desde: '2026-01-01T00:00:00Z',
  vigente_hasta: null,
  estado: 'activo',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('getTiposVehiculo() — pagination unwrap (regression)', () => {
  it('returns the items array when backend returns the paginated {items, next_cursor} shape (PRIMARY case)', async () => {
    mockParkosFetch.mockResolvedValueOnce({
      items: [sampleCarro, sampleBici],
      next_cursor: null,
    });

    const result = await getTiposVehiculo();

    expect(result).toEqual([sampleCarro, sampleBici]);
    expect(mockParkosFetch).toHaveBeenCalledWith('/api/v1/catalogos/tipos-vehiculo');
  });

  it('returns the array directly when backend returns a flat array (defensive fallback)', async () => {
    mockParkosFetch.mockResolvedValueOnce([sampleCarro, sampleBici]);

    const result = await getTiposVehiculo();

    expect(result).toEqual([sampleCarro, sampleBici]);
  });

  it('returns [] when paginated response has empty items', async () => {
    mockParkosFetch.mockResolvedValueOnce({ items: [], next_cursor: null });

    const result = await getTiposVehiculo();

    expect(result).toEqual([]);
  });

  it('returns [] when items key is missing in the paginated response', async () => {
    mockParkosFetch.mockResolvedValueOnce({ next_cursor: null });

    const result = await getTiposVehiculo();

    expect(result).toEqual([]);
  });

  it('filters out rows with tipo: null before returning (DEC-F4.1-09)', async () => {
    mockParkosFetch.mockResolvedValueOnce({
      items: [sampleCarro, sampleNullTipo, sampleBici],
      next_cursor: null,
    });

    const result = await getTiposVehiculo();

    expect(result).toEqual([sampleCarro, sampleBici]);
    expect(result.find((t) => t.tipo === null)).toBeUndefined();
  });

  it('returns [] when the backend responds with 404 (sucursal nueva sin tipos)', async () => {
    mockParkosFetch.mockRejectedValueOnce(new ParkosHttpError(404, 'Not Found', '/api/v1/catalogos/tipos-vehiculo'));

    const result = await getTiposVehiculo();

    expect(result).toEqual([]);
  });

  it('rethrows non-404 ParkosHttpError so SWR can handle auth/network errors', async () => {
    mockParkosFetch.mockRejectedValueOnce(new ParkosHttpError(500, 'Internal Server Error', '/api/v1/catalogos/tipos-vehiculo'));

    await expect(getTiposVehiculo()).rejects.toThrow(ParkosHttpError);
  });
});
