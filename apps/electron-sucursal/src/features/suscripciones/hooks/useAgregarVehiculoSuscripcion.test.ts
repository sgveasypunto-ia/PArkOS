/**
 * `useAgregarVehiculoSuscripcion.test.ts` — SWR mutation hook tests
 * (HU-F9.2 realineada, paso 3 del Sheet: agregar un vehículo).
 *
 * Mirrors `useVentaSuscripcion.test.ts` composition (parkosFetch +
 * Idempotency-Key + typed 4xx error mapping + 401 auth-clear).
 *
 * Coverage:
 *   T1: 201 → returns parsed SubscripcionCupoDetalle.
 *   T2: 404 subscripcion_no_encontrada → throws CuposSubscripcionNoEncontradaError.
 *   T3: 409 vehiculo_ya_inscrito → throws CuposVehiculoYaInscritoError with the placa.
 *   T4: 422 cantidad_maxima_excedida → throws CuposCantidadMaximaError with max.
 *   T5: 422 tipo_vehiculo_incompatible → throws CuposTipoIncompatibleError.
 *   T6: 401 → useAuthStore.clear() + parkos:auth:cleared event.
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
  useAgregarVehiculoSuscripcion,
  CuposCantidadMaximaError,
  CuposSubscripcionNoEncontradaError,
  CuposTipoIncompatibleError,
  CuposVehiculoYaInscritoError,
} from './useAgregarVehiculoSuscripcion';
import { useAuthStore } from '@parkos/ui-kit/store';

const INPUT = { uuid_subscripcion_cliente: '00000000-0000-0000-0000-000000000001', placa: 'CUP003' };

const DETALLE = {
  uuid: '00000000-0000-0000-0000-000000000001',
  cliente: { uuid: '00000000-0000-0000-0000-000000000002', nombre: 'Cupos', apellido: 'DeTest', numero_identificacion: '9998887771' },
  plan: { uuid: '00000000-0000-0000-0000-000000000003', tipo: 'MENSUAL_EMPRESA', valor: '800000', cantidad_maxima_vehiculos: 10, mismo_tipo_vehiculo: false },
  fecha_inicio_cobertura: '2026-09-24',
  fecha_vencimiento: '2026-10-24',
  cupo_maximo: 10,
  cupo_disponible: 7,
  vehiculos: [{ uuid: '00000000-0000-0000-0000-000000000023', uuid_vehiculo: '00000000-0000-0000-0000-000000000013', placa: 'CUP003' }],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useAgregarVehiculoSuscripcion — HU-F9.2 realineada', () => {
  it('T1: 201 → returns parsed SubscripcionCupoDetalle', async () => {
    mockFetch.mockResolvedValueOnce(DETALLE);
    const { result } = renderHook(() => useAgregarVehiculoSuscripcion());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger(INPUT);
    });

    expect(mockFetch.mock.calls[0]?.[0]).toBe('/api/v1/clientes/subscripcion-vehiculos/agregar');
    expect((data as { cupo_disponible: number }).cupo_disponible).toBe(7);
  });

  it('T2: 404 subscripcion_no_encontrada → throws CuposSubscripcionNoEncontradaError', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(404, JSON.stringify({ detail: { error: 'subscripcion_no_encontrada' } }), 'x'),
    );
    const { result } = renderHook(() => useAgregarVehiculoSuscripcion());

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger(INPUT);
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(CuposSubscripcionNoEncontradaError);
  });

  it('T3: 409 vehiculo_ya_inscrito → throws CuposVehiculoYaInscritoError with placa', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(409, JSON.stringify({ detail: { error: 'vehiculo_ya_inscrito', placa: 'CUP003' } }), 'x'),
    );
    const { result } = renderHook(() => useAgregarVehiculoSuscripcion());

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger(INPUT);
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(CuposVehiculoYaInscritoError);
    expect((caught as CuposVehiculoYaInscritoError).placa).toBe('CUP003');
  });

  it('T4: 422 cantidad_maxima_excedida → throws CuposCantidadMaximaError with max', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(
        422,
        JSON.stringify({
          detail: { error: 'cantidad_maxima_excedida', cantidad_maxima_vehiculos: 10 },
        }),
        'x',
      ),
    );
    const { result } = renderHook(() => useAgregarVehiculoSuscripcion());

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger(INPUT);
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(CuposCantidadMaximaError);
    expect((caught as CuposCantidadMaximaError).max).toBe(10);
  });

  it('T5: 422 tipo_vehiculo_incompatible → throws CuposTipoIncompatibleError', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(
        422,
        JSON.stringify({
          detail: { error: 'tipo_vehiculo_incompatible', tipos_encontrados: ['a', 'b'] },
        }),
        'x',
      ),
    );
    const { result } = renderHook(() => useAgregarVehiculoSuscripcion());

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger(INPUT);
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(CuposTipoIncompatibleError);
    expect((caught as CuposTipoIncompatibleError).tipos_encontrados).toEqual(['a', 'b']);
  });

  it('T6: 401 → useAuthStore.clear() + parkos:auth:cleared event', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      return origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(new ParkosHttpError(401, '{"error":"token_expired"}', 'x'));
    const { result } = renderHook(() => useAgregarVehiculoSuscripcion());

    await act(async () => {
      await result.current.trigger(INPUT).catch(() => undefined);
    });

    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});
