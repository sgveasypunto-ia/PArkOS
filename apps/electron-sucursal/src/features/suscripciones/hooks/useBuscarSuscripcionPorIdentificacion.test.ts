/**
 * `useBuscarSuscripcionPorIdentificacion.test.ts` — on-demand search
 * hook tests (HU-F9.2 realineada, paso 2 del Sheet).
 *
 * Coverage:
 *   T1: trigger(numero) → GET with the querystring, returns the parsed detalle.
 *   T2: backend returns null (200) → trigger resolves to null (not an error).
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

import { useBuscarSuscripcionPorIdentificacion } from './useBuscarSuscripcionPorIdentificacion';
import { useAuthStore } from '@parkos/ui-kit/store';

const DETALLE = {
  uuid: '00000000-0000-0000-0000-000000000001',
  cliente: { uuid: '00000000-0000-0000-0000-000000000002', nombre: 'Cupos', apellido: 'DeTest', numero_identificacion: '9998887771' },
  plan: { uuid: '00000000-0000-0000-0000-000000000003', tipo: 'MENSUAL_EMPRESA', valor: '800000', cantidad_maxima_vehiculos: 10, mismo_tipo_vehiculo: false },
  fecha_inicio_cobertura: '2026-09-24',
  fecha_vencimiento: '2026-10-24',
  cupo_maximo: 10,
  cupo_disponible: 8,
  vehiculos: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useBuscarSuscripcionPorIdentificacion — HU-F9.2 realineada', () => {
  it('T1: trigger(numero) → GET with querystring, returns parsed detalle', async () => {
    mockFetch.mockResolvedValueOnce(DETALLE);
    const { result } = renderHook(() => useBuscarSuscripcionPorIdentificacion());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger('9998887771');
    });

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/clientes/subscripciones-activas/buscar?numero_identificacion=9998887771',
    );
    expect((data as { uuid: string }).uuid).toBe('00000000-0000-0000-0000-000000000001');
  });

  it('T2: backend returns null → trigger resolves to null', async () => {
    mockFetch.mockResolvedValueOnce(null);
    const { result } = renderHook(() => useBuscarSuscripcionPorIdentificacion());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger('000000');
    });

    expect(data).toBeNull();
  });

  it('T3: 401 → useAuthStore.clear() + parkos:auth:cleared event', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      return origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(401, '{"error":"token_expired"}', '/api/v1/clientes/subscripciones-activas/buscar'),
    );
    const { result } = renderHook(() => useBuscarSuscripcionPorIdentificacion());

    await act(async () => {
      await result.current.trigger('9998887771').catch(() => undefined);
    });

    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});
