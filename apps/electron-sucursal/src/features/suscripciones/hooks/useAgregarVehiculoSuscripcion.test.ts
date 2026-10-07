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
 *   T7-T11 (PT-2): permission_denied, sucursal context, placa_con_suscripcion_activa,
 *       tipo_vehiculo_plan_incompatible, unknown codes.
 *   T12: per-attempt Idempotency-Key (add/remove/add never replays).
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
import {
  CuposContextoSucursalError,
  CuposPermisoDenegadoError,
  CuposPlacaConSuscripcionActivaError,
  CuposTipoPlanIncompatibleError,
} from './cuposErrors';
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

  // PT-2 error contract -------------------------------------------------
  async function failWith(status: number, detail: Record<string, unknown>): Promise<unknown> {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(new ParkosHttpError(status, JSON.stringify({ detail }), 'x'));
    const { result } = renderHook(() => useAgregarVehiculoSuscripcion());
    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger(INPUT);
      } catch (e) {
        caught = e;
      }
    });
    return caught;
  }

  it('T7: 403 permission_denied → CuposPermisoDenegadoError', async () => {
    const caught = await failWith(403, { error: 'permission_denied', detail: 'gestionar_placas_suscripcion' });
    expect(caught).toBeInstanceOf(CuposPermisoDenegadoError);
  });

  it('T8: 400 missing_sucursal_context / 403 unauthorized_sucursal_context → CuposContextoSucursalError', async () => {
    const a = await failWith(400, { error: 'missing_sucursal_context' });
    expect(a).toBeInstanceOf(CuposContextoSucursalError);
    expect((a as CuposContextoSucursalError).status).toBe(400);
    const b = await failWith(403, { error: 'unauthorized_sucursal_context' });
    expect(b).toBeInstanceOf(CuposContextoSucursalError);
    expect((b as CuposContextoSucursalError).status).toBe(403);
  });

  it('T9: 409 placa_con_suscripcion_activa → typed error with placa + the other subscription', async () => {
    const caught = await failWith(409, {
      error: 'placa_con_suscripcion_activa',
      placa: 'ZZZ999',
      uuid_subscripcion_cliente: 'other-sub',
    });
    expect(caught).toBeInstanceOf(CuposPlacaConSuscripcionActivaError);
    expect((caught as CuposPlacaConSuscripcionActivaError).placa).toBe('ZZZ999');
    expect((caught as CuposPlacaConSuscripcionActivaError).uuid_subscripcion_cliente).toBe(
      'other-sub',
    );
  });

  it('T10: 422 tipo_vehiculo_plan_incompatible → typed error with tipo_plan + tipos_encontrados', async () => {
    const caught = await failWith(422, {
      error: 'tipo_vehiculo_plan_incompatible',
      tipo_plan: 'moto',
      tipos_encontrados: ['carro'],
    });
    expect(caught).toBeInstanceOf(CuposTipoPlanIncompatibleError);
    expect((caught as CuposTipoPlanIncompatibleError).tipo_plan).toBe('moto');
    expect((caught as CuposTipoPlanIncompatibleError).tipos_encontrados).toEqual(['carro']);
  });

  it('T11: unknown error codes are rethrown untouched (transport error)', async () => {
    const caught = await failWith(500, { error: 'boom' });
    expect((caught as { status?: number }).status).toBe(500);
  });

  it('T12: add -> remove -> add of the same plate sends DIFFERENT Idempotency-Keys (no stale replay)', async () => {
    mockFetch.mockResolvedValue(DETALLE);
    const { result } = renderHook(() => useAgregarVehiculoSuscripcion());
    await act(async () => {
      await result.current.trigger(INPUT);
    });
    await act(async () => {
      await result.current.trigger(INPUT);
    });
    const k1 = (mockFetch.mock.calls[0]?.[1] as { headers: Record<string, string> }).headers[
      'Idempotency-Key'
    ];
    const k2 = (mockFetch.mock.calls[1]?.[1] as { headers: Record<string, string> }).headers[
      'Idempotency-Key'
    ];
    expect(k1).toBeTruthy();
    expect(k1).not.toBe(k2);
    // The explicit key must survive parkosFetch's own hashing.
    expect((mockFetch.mock.calls[0]?.[1] as { skipIdempotencyKey?: boolean }).skipIdempotencyKey).toBe(
      true,
    );
  });
});
