/**
 * `useSuscripcionesProximasVencer.test.ts` — SWR hook tests
 * (HU-F9.2, REQ-OPS-181).
 *
 * Mirrors `useVentaSuscripcion.test.ts` (F9.1) and
 * `useSesionActiva.test.ts` (F3.3) for the auth-store + parkosFetch
 * mocks.
 *
 * Coverage (3 hook tests):
 *   T1: filter excludes items with `dias_para_vencer < 0` (vencidas).
 *   T2: sort by `fecha_vencimiento` ASCENDING.
 *   T3: empty array from backend → `data === []`.
 *
 * The tests use `fecha_vencimiento` values that are far in the past
 * (<0 days) or far in the future (>>0 days) so the assertion is
 * deterministic against the actual `Date.now()` at test execution
 * time — no `Date.now()` mocking required.
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

import { renderHook, waitFor } from '@testing-library/react';

import { useSuscripcionesProximasVencer } from './useSuscripcionesProximasVencer';

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useSuscripcionesProximasVencer — REQ-OPS-181', () => {
  it('T1: filter excludes items with dias_para_vencer < 0 (vencidas)', async () => {
    mockFetch.mockResolvedValueOnce([
      {
        uuid: 'a',
        placa: 'ABC123',
        fecha_vencimiento: '2030-01-01',
        cliente_nombre: 'Cliente Alpha',
        plan_nombre: 'Mensual',
        estado: 'activa',
      },
      {
        uuid: 'b',
        placa: 'DEF456',
        fecha_vencimiento: '2030-06-01',
        cliente_nombre: 'Cliente Beta',
        plan_nombre: 'Mensual',
        estado: 'activa',
      },
      {
        uuid: 'c',
        placa: 'GHI789',
        fecha_vencimiento: '2020-01-01',
        cliente_nombre: 'Cliente Vencida',
        plan_nombre: 'Mensual',
        estado: 'vencida',
      },
    ]);

    const { result } = renderHook(() =>
      useSuscripcionesProximasVencer('uuid-suc-t1'),
    );

    await waitFor(() => expect(result.current.data).toBeDefined());

    expect(result.current.data).toHaveLength(2);
    expect(
      result.current.data?.some((d) => d.placa === 'GHI789'),
    ).toBe(false);
    // The two surviving items are sorted ASC by fecha_vencimiento.
    expect(result.current.data?.map((d) => d.placa)).toEqual([
      'ABC123',
      'DEF456',
    ]);
  });

  it('T2: sort by fecha_vencimiento ASCENDING', async () => {
    mockFetch.mockResolvedValueOnce([
      {
        uuid: 'late',
        placa: 'LATE',
        fecha_vencimiento: '2030-12-01',
        cliente_nombre: 'X',
        plan_nombre: 'P',
        estado: 'activa',
      },
      {
        uuid: 'middle',
        placa: 'MIDDLE',
        fecha_vencimiento: '2030-06-01',
        cliente_nombre: 'X',
        plan_nombre: 'P',
        estado: 'activa',
      },
      {
        uuid: 'early',
        placa: 'EARLY',
        fecha_vencimiento: '2030-01-01',
        cliente_nombre: 'X',
        plan_nombre: 'P',
        estado: 'activa',
      },
    ]);

    const { result } = renderHook(() =>
      useSuscripcionesProximasVencer('uuid-suc-t2'),
    );

    await waitFor(() => expect(result.current.data).toBeDefined());

    expect(result.current.data?.map((d) => d.placa)).toEqual([
      'EARLY',
      'MIDDLE',
      'LATE',
    ]);
  });

  it('T3: backend returns [] → data is []', async () => {
    mockFetch.mockResolvedValueOnce([]);

    const { result } = renderHook(() =>
      useSuscripcionesProximasVencer('uuid-suc-t3'),
    );

    await waitFor(() => expect(result.current.data).toBeDefined());

    expect(result.current.data).toEqual([]);
  });
});
