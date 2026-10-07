/**
 * `useSuscripcionesProximasVencer.test.ts` — SWR hook tests
 * (HU-F9.2 REQ-OPS-181, corrected for PT-3).
 *
 * Coverage:
 *   T0: calls the REAL endpoint `/clientes/subscripciones/proximas-vencer`
 *       (the old `/suscripciones-cliente/proximas-vencer` never existed).
 *   T1: the backend is authoritative: `dias_restantes` / `puede_renovar` pass
 *       through and expired rows (dias_restantes < 0) are kept, flagged `vencida`.
 *   T2: sort by `fecha_vencimiento` ASCENDING.
 *   T3: empty array from backend -> `data === []`.
 *   T4: an unexpected payload degrades to `[]` (never breaks the dashboard).
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

import { createElement, type ReactNode } from 'react';
import { renderHook as rtlRenderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';

// The SWR key no longer carries the sucursal, so every test needs its own cache.
const wrapper = ({ children }: { children: ReactNode }): JSX.Element =>
  createElement(SWRConfig, { value: { provider: () => new Map() } }, children);
const renderHook = <T,>(cb: () => T): ReturnType<typeof rtlRenderHook<T, unknown>> =>
  rtlRenderHook(cb, { wrapper });

import {
  computeProximasVencer,
  useSuscripcionesProximasVencer,
} from './useSuscripcionesProximasVencer';

const row = (over: Record<string, unknown>): Record<string, unknown> => ({
  uuid: '00000000-0000-0000-0000-000000000001',
  cliente_nombre: 'Cliente Alpha',
  plan_nombre: 'Mensual',
  placas: ['ABC123'],
  fecha_vencimiento: '2030-01-01',
  dias_restantes: 5,
  dias_alerta_pre_vencimiento: 7,
  puede_renovar: true,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useSuscripcionesProximasVencer — REQ-OPS-181 (PT-3)', () => {
  it('T0: calls /clientes/subscripciones/proximas-vencer', async () => {
    mockFetch.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useSuscripcionesProximasVencer('uuid-suc-t0'));
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockFetch.mock.calls[0]?.[0]).toBe('/api/v1/clientes/subscripciones/proximas-vencer');
  });

  it('T1: backend fields pass through; expired rows are kept and flagged', async () => {
    mockFetch.mockResolvedValueOnce([
      row({ uuid: '00000000-0000-0000-0000-00000000000a', dias_restantes: 3 }),
      row({
        uuid: '00000000-0000-0000-0000-00000000000b',
        fecha_vencimiento: '2020-01-01',
        dias_restantes: -4,
        puede_renovar: true,
      }),
    ]);
    const { result } = renderHook(() => useSuscripcionesProximasVencer('uuid-suc-t1'));
    await waitFor(() => expect(result.current.data).toBeDefined());

    expect(result.current.data).toHaveLength(2);
    const vencida = result.current.data?.find((d) => d.dias_restantes === -4);
    expect(vencida?.vencida).toBe(true);
    expect(vencida?.puede_renovar).toBe(true);
    const proxima = result.current.data?.find((d) => d.dias_restantes === 3);
    expect(proxima?.vencida).toBe(false);
    expect(proxima?.dias_alerta_pre_vencimiento).toBe(7);
  });

  it('T2: sort by fecha_vencimiento ASCENDING', async () => {
    mockFetch.mockResolvedValueOnce([
      row({ uuid: '00000000-0000-0000-0000-000000000003', fecha_vencimiento: '2030-12-01', cliente_nombre: 'late' }),
      row({ uuid: '00000000-0000-0000-0000-000000000002', fecha_vencimiento: '2030-06-01', cliente_nombre: 'middle' }),
      row({ uuid: '00000000-0000-0000-0000-000000000001', fecha_vencimiento: '2030-01-01', cliente_nombre: 'early' }),
    ]);
    const { result } = renderHook(() => useSuscripcionesProximasVencer('uuid-suc-t2'));
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.map((d) => d.cliente_nombre)).toEqual(['early', 'middle', 'late']);
  });

  it('T3: backend returns [] -> data is []', async () => {
    mockFetch.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useSuscripcionesProximasVencer('uuid-suc-t3'));
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data).toEqual([]);
  });

  it('T4: an unexpected payload degrades to []', async () => {
    mockFetch.mockResolvedValueOnce({ unexpected: true });
    const { result } = renderHook(() => useSuscripcionesProximasVencer('uuid-suc-t4'));
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data).toEqual([]);
  });

  it('computeProximasVencer does no date arithmetic (pure pass-through + sort)', () => {
    const out = computeProximasVencer([
      {
        uuid: '00000000-0000-0000-0000-000000000001',
        cliente_nombre: 'A',
        plan_nombre: 'P',
        placas: [],
        fecha_vencimiento: '2031-01-01',
        dias_restantes: 999,
        puede_renovar: false,
      },
    ]);
    expect(out[0]?.dias_restantes).toBe(999);
    expect(out[0]?.puede_renovar).toBe(false);
    expect(out[0]?.dias_alerta_pre_vencimiento).toBeNull();
  });
});
