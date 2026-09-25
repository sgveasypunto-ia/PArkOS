/**
 * `useSuscripcionesActivas.test.tsx` — SWR hook tests (HU-F9.2
 * realineada, paso 1 del Sheet).
 *
 * Mirrors `useSuscripcionesProximasVencer.test.ts` / `useVentaSuscripcion.test.ts`
 * for the auth-store + parkosFetch mocks.
 *
 * Each test wraps `renderHook` in its own `<SWRConfig provider={() =>
 * new Map()}>` — this hook uses a STATIC key (branch-scoped
 * server-side, no per-branch key variation), so without a fresh cache
 * per test, a later test's fetch would read the FIRST test's cached
 * value/error instead of actually re-fetching (real gotcha hit while
 * writing T3: the 401 test silently reused T1's successful cache entry
 * and never called `onError`).
 *
 * Coverage:
 *   T1: calls the real dedicated endpoint (no uuid_sucursal query
 *       param — branch-scoped server-side) and unwraps `{items}`.
 *   T2: null uuid_sucursal → SWR key gated to null, no fetch.
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

import type { ReactNode } from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';

import { useSuscripcionesActivas } from './useSuscripcionesActivas';
import { useAuthStore } from '@parkos/ui-kit/store';

function freshCacheWrapper({ children }: { children: ReactNode }): JSX.Element {
  return <SWRConfig value={{ provider: () => new Map() }}>{children}</SWRConfig>;
}

const ITEM = {
  uuid: '00000000-0000-0000-0000-000000000001',
  cliente: { uuid: '00000000-0000-0000-0000-000000000002', nombre: 'Cupos', apellido: 'DeTest', numero_identificacion: '9998887771' },
  plan: { uuid: '00000000-0000-0000-0000-000000000003', tipo: 'MENSUAL_EMPRESA', valor: '800000', cantidad_maxima_vehiculos: 10, mismo_tipo_vehiculo: false },
  fecha_inicio_cobertura: '2026-09-24',
  fecha_vencimiento: '2026-10-24',
  cupo_maximo: 10,
  vehiculos_inscritos: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useSuscripcionesActivas — HU-F9.2 realineada', () => {
  it('T1: calls the dedicated endpoint (no query param) and unwraps items', async () => {
    mockFetch.mockResolvedValueOnce({ items: [ITEM] });

    const { result } = renderHook(() => useSuscripcionesActivas('suc-1'), {
      wrapper: freshCacheWrapper,
    });

    await waitFor(() => expect(result.current.data).toBeDefined());

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/clientes/subscripciones-activas');
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0]?.cupo_maximo).toBe(10);
    expect(result.current.data?.[0]?.vehiculos_inscritos).toBe(2);
  });

  it('T2: null uuid_sucursal gates the SWR key — no fetch fires', async () => {
    renderHook(() => useSuscripcionesActivas(null), { wrapper: freshCacheWrapper });
    await new Promise((r) => setTimeout(r, 0));
    expect(mockFetch).not.toHaveBeenCalled();
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
      new ParkosHttpError(401, '{"error":"token_expired"}', '/api/v1/clientes/subscripciones-activas'),
    );

    renderHook(() => useSuscripcionesActivas('suc-1'), { wrapper: freshCacheWrapper });

    await waitFor(() => {
      expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    });
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});
