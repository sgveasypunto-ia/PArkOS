/**
 * Tests for `useFacturaElectronica` (REQ-OPS-132 fetcher-closure + lazy-mount).
 *
 * Coverage:
 *   F1: uuid === null → SWR key is null → fetcher NOT invoked.
 *   F2: uuid set + accessToken set → fetcher invoked with bare UUID
 *       (NOT the SWR key), proving REQ-OPS-132 fetcher-closure.
 *   F3: 401 → defensive logout fired.
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

import { useFacturaElectronica } from './useFacturaElectronica';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useFacturaElectronica — REQ-OPS-132 fetcher-closure + lazy-mount', () => {
  it('F1: uuid=null → key null → fetcher NOT invoked', () => {
    renderHook(() => useFacturaElectronica(null));
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('F2: uuid set → fetcher invoked with canonical /{uuid} URL', async () => {
    mockFetch.mockResolvedValue({
      uuid_factura_electronica: '00000000-0000-0000-0000-000000000010',
      uuid_factura: '00000000-0000-0000-0000-000000000011',
      estado_dian: 'aceptado',
      respuesta_proveedor: null,
      actualizado_en: '2026-09-17T10:00:00Z',
    });

    renderHook(() => useFacturaElectronica('00000000-0000-0000-0000-000000000010'));

    await act(async () => {
      await Promise.resolve();
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const calledUrl = mockFetch.mock.calls[0]?.[0] as string;
    expect(calledUrl).toBe(
      '/api/v1/facturacion/factura-electronica/00000000-0000-0000-0000-000000000010',
    );
  });

  it('F3: 401 from fetcher → defensive logout (clear + parkos:auth:cleared)', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValue(new ParkosHttpError(401));

    renderHook(() => useFacturaElectronica('00000000-0000-0000-0000-000000000012'));

    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });

    expect(dispatched).toContain('parkos:auth:cleared');
  });
});