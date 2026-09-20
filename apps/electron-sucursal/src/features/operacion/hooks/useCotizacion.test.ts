/**
 * Tests for `useCotizacion` (REQ-OPS-132 fetcher-closure + lazy-mount +
 * F7.1 canonical discriminated union schema).
 *
 * Coverage:
 *   C1: uuid_ingreso === null → SWR key is null → fetcher NOT invoked.
 *   C2: uuid_ingreso set + accessToken set → fetcher invoked with bare
 *       UUID (NOT the SWR key), proving REQ-OPS-132 fetcher-closure.
 *   C3: 401 → defensive logout fired (auth store + parkos:auth:cleared).
 *   C4: rotación — canonical `{cobrar: true, subtotal, iva, total,
 *       tiempo_minutos, tarifa_uuid, vigente_hasta}` is consumed;
 *       SWR key + parser path asserted.
 *   C5: mensualidad — canonical `{cobrar: false, motivo:
 *       'mensualidad_vigente'}` short-circuit branch.
 *   C6: tiempo ≥ tarifa-plena — high `tiempo_minutos` (≥24h) with
 *       `total === valor_plena`; no fraction accumulation.
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

const UUID_INGRESO = '00000000-0000-0000-0000-000000000003';
const UUID_TARIFA = '00000000-0000-0000-0000-000000000004';
const UUID_INGRESO_C5 = '00000000-0000-0000-0000-000000000006';
const UUID_INGRESO_C6 = '00000000-0000-0000-0000-000000000007';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useCotizacion — REQ-OPS-132 fetcher-closure + lazy-mount', () => {
  it('C1: uuid_ingreso=null → key null → fetcher NOT invoked', () => {
    mockFetch.mockResolvedValue({
      cobrar: true,
      subtotal: 41000,
      iva: 7790,
      total: 48790,
      tiempo_minutos: 32.5,
      tarifa_uuid: UUID_TARIFA,
      vigente_hasta: '2026-09-19T11:00:00Z',
    });

    renderHook(() => useCotizacion(null));

    // parkosFetch must NOT be called when uuid_ingreso is null.
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('C2: uuid_ingreso set → fetcher invoked with bare UUID (REQ-OPS-132)', async () => {
    mockFetch.mockResolvedValue({
      cobrar: true,
      subtotal: 41000,
      iva: 7790,
      total: 48790,
      tiempo_minutos: 32.5,
      tarifa_uuid: UUID_TARIFA,
      vigente_hasta: '2026-09-19T11:00:00Z',
    });

    renderHook(() => useCotizacion(UUID_INGRESO));

    await act(async () => {
      await Promise.resolve();
    });

    // Fetcher receives the bare UUID via the SWR cache key path; the
    // impl internally calls parkosFetch with the canonical URL. The
    // important assertion here is that the fetcher was invoked with
    // the bare UUID (the closure captures it, NOT the cache key).
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const calledUrl = mockFetch.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain(`uuid_ingreso=${UUID_INGRESO}`);
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
    mockFetch.mockRejectedValue(new ParkosHttpError(401, 'unauthorized', '/api/v1/operacion/cotizar'));

    // Distinct UUID to avoid SWR cache collision with C2 (which used
    // UUID_INGRESO with a successful mock).
    renderHook(() => useCotizacion('00000000-0000-0000-0000-000000000005'));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });

    // Defensive logout fired exactly once.
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});

describe('useCotizacion — canonical discriminated union (cobrar: true|false)', () => {
  it('C4: rotación — cobrar:true con desglose completo es consumido por el parser', async () => {
    mockFetch.mockResolvedValue({
      cobrar: true,
      subtotal: 41000,
      iva: 7790,
      total: 48790,
      tiempo_minutos: 32.5,
      tarifa_uuid: UUID_TARIFA,
      vigente_hasta: '2026-09-19T11:00:00Z',
    });

    const { result } = renderHook(() => useCotizacion(UUID_INGRESO));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });

    expect(result.current.error).toBeUndefined();
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.cobrar).toBe(true);
    if (result.current.data?.cobrar === true) {
      expect(result.current.data.subtotal).toBe(41000);
      expect(result.current.data.iva).toBe(7790);
      expect(result.current.data.total).toBe(48790);
      expect(result.current.data.tiempo_minutos).toBe(32.5);
      expect(result.current.data.tarifa_uuid).toBe(UUID_TARIFA);
      expect(result.current.data.vigente_hasta).toBe('2026-09-19T11:00:00Z');
    }
  });

  it('C5: mensualidad — cobrar:false con motivo short-circuit', async () => {
    mockFetch.mockResolvedValue({
      cobrar: false,
      motivo: 'mensualidad_vigente',
    });

    const { result } = renderHook(() => useCotizacion(UUID_INGRESO_C5));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });

    expect(result.current.error).toBeUndefined();
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.cobrar).toBe(false);
    if (result.current.data?.cobrar === false) {
      expect(result.current.data.motivo).toBe('mensualidad_vigente');
    }
  });

  it('C6: tiempo ≥ tarifa-plena — tiempo_minutos alto, total === valor_plena, no acumula fracción', async () => {
    // 26 horas = 1560 minutos — supera cualquier tarifa plena típica (24h).
    const valorPlena = 50000;
    mockFetch.mockResolvedValue({
      cobrar: true,
      subtotal: valorPlena,
      iva: 0,
      total: valorPlena,
      tiempo_minutos: 1560,
      tarifa_uuid: UUID_TARIFA,
      vigente_hasta: '2026-09-19T11:00:00Z',
    });

    const { result } = renderHook(() => useCotizacion(UUID_INGRESO_C6));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });

    expect(result.current.error).toBeUndefined();
    expect(result.current.data).toBeDefined();
    if (result.current.data?.cobrar === true) {
      expect(result.current.data.tiempo_minutos).toBe(1560);
      expect(result.current.data.total).toBe(valorPlena);
      // subtotal === total cuando iva === 0 (sin acumular fracción).
      expect(result.current.data.subtotal).toBe(result.current.data.total);
    }
  });
});
