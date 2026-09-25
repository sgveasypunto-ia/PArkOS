/**
 * `useQuitarVehiculoSuscripcion.test.ts` — SWR mutation hook tests
 * (HU-F9.2 realineada, paso 3 del Sheet: quitar un vehículo inscrito).
 *
 * Coverage:
 *   T1: 200 → PUT to the {uuid}/quitar path, returns parsed detalle.
 *   T2: 404 → throws CuposVehiculoInscritoNoEncontradoError.
 *   T3: 401 → useAuthStore.clear() + parkos:auth:cleared event.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@parkos/ui-kit/store', () => {
  const state = { accessToken: 'tok-abc', clear: vi.fn() };
  return {
    useAuthStore: Object.assign(
      (sel: (s: typeof state) => unknown) => sel(state),
      { getState: () => state },
    ),
  };
});

const mockFetch = vi.fn();
vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: (...args: unknown[]) => mockFetch(...args),
  ParkosHttpError: class extends Error {
    public readonly status: number;
    public readonly body: string;
    constructor(status: number, body = '') {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
      this.body = body;
    }
  },
}));

import { act, renderHook } from '@testing-library/react';

import {
  useQuitarVehiculoSuscripcion,
  CuposVehiculoInscritoNoEncontradoError,
} from './useQuitarVehiculoSuscripcion';
import { useAuthStore } from '@parkos/ui-kit/store';

const DETALLE = {
  uuid: '00000000-0000-0000-0000-000000000001',
  cliente: { uuid: '00000000-0000-0000-0000-000000000002', nombre: 'Cupos', apellido: 'DeTest', numero_identificacion: '9998887771' },
  plan: { uuid: '00000000-0000-0000-0000-000000000003', tipo: 'MENSUAL_EMPRESA', valor: '800000', cantidad_maxima_vehiculos: 10, mismo_tipo_vehiculo: false },
  fecha_inicio_cobertura: '2026-09-24',
  fecha_vencimiento: '2026-10-24',
  cupo_maximo: 10,
  cupo_disponible: 9,
  vehiculos: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useQuitarVehiculoSuscripcion — HU-F9.2 realineada', () => {
  it('T1: 200 → PUT to the {uuid}/quitar path, returns parsed detalle', async () => {
    mockFetch.mockResolvedValueOnce(DETALLE);
    const { result } = renderHook(() => useQuitarVehiculoSuscripcion());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger('00000000-0000-0000-0000-000000000021');
    });

    expect(mockFetch.mock.calls[0]?.[0]).toBe(
      '/api/v1/clientes/subscripcion-vehiculos/00000000-0000-0000-0000-000000000021/quitar',
    );
    expect(mockFetch.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({ method: 'PUT' }),
    );
    expect((data as { cupo_disponible: number }).cupo_disponible).toBe(9);
  });

  it('T2: 404 → throws CuposVehiculoInscritoNoEncontradoError', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(404, JSON.stringify({ error: 'vehiculo_inscrito_no_encontrado' }), 'x'),
    );
    const { result } = renderHook(() => useQuitarVehiculoSuscripcion());

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger('00000000-0000-0000-0000-000000000021');
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(CuposVehiculoInscritoNoEncontradoError);
  });

  it('T3: 401 → useAuthStore.clear() + parkos:auth:cleared event', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      return origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(new ParkosHttpError(401, '{"error":"token_expired"}', 'x'));
    const { result } = renderHook(() => useQuitarVehiculoSuscripcion());

    await act(async () => {
      await result.current.trigger('00000000-0000-0000-0000-000000000021').catch(() => undefined);
    });

    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});
