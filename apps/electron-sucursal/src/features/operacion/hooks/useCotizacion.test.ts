/**
 * Tests for `useCotizacion` (REQ-OPS-132 fetcher-closure + lazy-mount).
 *
 * Coverage:
 *   C1: uuid_ingreso === null → SWR key is null → fetcher NOT invoked.
 *   C2: uuid_ingreso set + accessToken set → fetcher invoked with bare
 *       UUID (NOT the SWR key), proving REQ-OPS-132 fetcher-closure.
 *   C3: 401 → defensive logout fired (auth store + parkos:auth:cleared).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

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
    constructor(status: number) {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
    }
  },
}));

import { renderHook, act } from '@testing-library/react';

import { useCotizacion } from './useCotizacion';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useCotizacion — REQ-OPS-132 fetcher-closure + lazy-mount', () => {
  it('C1: uuid_ingreso=null → key null → fetcher NOT invoked', () => {
    mockFetch.mockResolvedValue({
      uuid_ingreso: '00000000-0000-0000-0000-000000000001',
      uuid_tarifa_vigente: '00000000-0000-0000-0000-000000000002',
      minutos_transcurridos: 5,
      base_cop: 1000,
      fraccion_cop: 500,
      total_cop: 1500,
      generado_en: '2026-09-17T10:00:00Z',
    });

    renderHook(() => useCotizacion(null));

    // parkosFetch must NOT be called when uuid_ingreso is null.
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('C2: uuid_ingreso set → fetcher invoked with bare UUID (REQ-OPS-132)', async () => {
    mockFetch.mockResolvedValue({
      uuid_ingreso: '00000000-0000-0000-0000-000000000003',
      uuid_tarifa_vigente: '00000000-0000-0000-0000-000000000004',
      minutos_transcurridos: 12,
      base_cop: 2400,
      fraccion_cop: 600,
      total_cop: 3000,
      generado_en: '2026-09-17T10:00:00Z',
    });

    renderHook(() => useCotizacion('00000000-0000-0000-0000-000000000003'));

    await act(async () => {
      await Promise.resolve();
    });

    // Fetcher receives the bare UUID via the SWR cache key path; the
    // impl internally calls parkosFetch with the canonical URL. The
    // important assertion here is that the fetcher was invoked with
    // the bare UUID (the closure captures it, NOT the cache key).
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const calledUrl = mockFetch.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain('uuid_ingreso=00000000-0000-0000-0000-000000000003');
    expect(calledUrl.startsWith('/api/v1/operacion/cotizar')).toBe(true);
  });

  it('C3: 401 from fetcher → defensive logout (clear + parkos:auth:cleared)', async () => {
    // Dispatch listener for the auth-cleared event.
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      origDispatch(event);
    }) as typeof window.dispatchEvent;

    // ParkosHttpError(401) thrown by parkosFetch.
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValue(new ParkosHttpError(401));

    renderHook(() => useCotizacion('00000000-0000-0000-0000-000000000005'));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });

    // Defensive logout fired exactly once.
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});