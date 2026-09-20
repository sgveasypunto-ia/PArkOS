/**
 * Tests for `useReintentarFE` SWR mutation hook (HU-F8.2, REQ-OPS-168 + 169).
 *
 * Composition mirrors `useRegistrarSalida.ts` (F7.2) and
 * `useRegistrarPago.ts` (F8.1):
 *   - `parkosFetch` for the canonical wire transport.
 *   - `buildIdempotencyKey` (F7.2 lib/idempotency.ts) for the
 *     SHA-256 RFC 8785 closure header (DEC-SUC-04 + DEC-IDEM-01).
 *   - `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *     event on 401 (preserved F3.1 invariant — REQ-OPS-107..110).
 *   - `NumeracionAgotadaError` typed class on 409
 *     `numeracion_agotada` (F1.10 — range exhaustion).
 *   - `mutate('/facturacion/factura-electronica/{uuid}')` after 201
 *     so SWR resumes the 30s polling loop with the new chain tip
 *     (`pendiente` is non-terminal).
 *
 * Coverage:
 *   R1: trigger → 201 → returns new `{uuid_envio, estado:'pendiente',
 *       uuid_envio_padre}`. The Idempotency-Key header MUST be the
 *       SHA-256 hex digest of `POST|path|body`.
 *   R2: 409 `numeracion_agotada` → hook MUST throw
 *       `NumeracionAgotadaError` with `status=409` +
 *       `code='numeracion_agotada'`.
 *   R3: 401 → defensive logout fired (clear + parkos:auth:cleared),
 *       preserving the F3.1 invariant shared across all SWR mutations.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type * as SwrType from 'swr';

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
const mockMutate = vi.fn().mockResolvedValue(undefined);

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: (...args: unknown[]) => mockFetch(...args),
  ParkosHttpError: class extends Error {
    public readonly status: number;
    public readonly body: string;
    public readonly url: string;
    constructor(status: number, body = '', url = '') {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
}));

// Mock SWR's `mutate` (cache invalidation) so R1 can assert the cache
// was revalidated after a successful POST.
vi.mock('swr', async () => {
  const actual = await vi.importActual<typeof SwrType>('swr');
  return {
    ...actual,
    mutate: (...args: unknown[]) => mockMutate(...args),
  };
});

import { renderHook, act } from '@testing-library/react';

import { useReintentarFE, NumeracionAgotadaError } from './useReintentarFE';

const UUID_FE = '00000000-0000-0000-0000-0000000000fe';

const reintentarResponse = {
  uuid_envio: '00000000-0000-0000-0000-0000000000a1',
  estado: 'pendiente',
  uuid_envio_padre: '00000000-0000-0000-0000-0000000000a0',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
  mockMutate.mockReset();
  mockMutate.mockResolvedValue(undefined);
});

describe('useReintentarFE — REQ-OPS-168/169 FE retry chain', () => {
  it('R1: trigger → POST 201 → returns new uuid_envio + estado=pendiente + mutate(cache) revalidates polling', async () => {
    mockFetch.mockResolvedValueOnce(reintentarResponse);

    const { result } = renderHook(() => useReintentarFE());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger(UUID_FE);
    });

    // POST went out with the canonical /reintentar path and an
    // Idempotency-Key SHA-256 hex header.
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe(
      `/api/v1/facturacion/factura-electronica/${UUID_FE}/reintentar`,
    );
    const headers = (mockFetch.mock.calls[0]?.[1] as { headers: Record<string, string> }).headers;
    expect(headers['Idempotency-Key']).toMatch(/^[a-f0-9]{64}$/);
    expect(headers['Idempotency-Key']).toHaveLength(64);

    // Cache revalidated after 201 so polling re-engages with new tip.
    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate.mock.calls[0]?.[0]).toBe(
      `/facturacion/factura-electronica/${UUID_FE}`,
    );

    // Resolved payload contract.
    expect((data as { uuid_envio: string }).uuid_envio).toBe(reintentarResponse.uuid_envio);
    expect((data as { estado: string }).estado).toBe('pendiente');
    expect((data as { uuid_envio_padre: string }).uuid_envio_padre).toBe(
      reintentarResponse.uuid_envio_padre,
    );
  });

  it('R2: 409 numeracion_agotada → throws NumeracionAgotadaError (REQ-OPS-168)', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(
        409,
        JSON.stringify({ error: 'numeracion_agotada' }),
        `/api/v1/facturacion/factura-electronica/${UUID_FE}/reintentar`,
      ),
    );

    const { result } = renderHook(() => useReintentarFE());

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger(UUID_FE);
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(NumeracionAgotadaError);
    expect((caught as NumeracionAgotadaError).status).toBe(409);
    expect((caught as NumeracionAgotadaError).code).toBe('numeracion_agotada');

    // No cache mutation on the error path.
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it('R3: 401 → useAuthStore.clear() + parkos:auth:cleared event (REQ-OPS-107..110 invariant)', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    const { useAuthStore } = await import('@parkos/ui-kit/store');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(
        401,
        '{"error":"token_expired"}',
        `/api/v1/facturacion/factura-electronica/${UUID_FE}/reintentar`,
      ),
    );

    const { result } = renderHook(() => useReintentarFE());

    await act(async () => {
      await result.current.trigger(UUID_FE).catch(() => undefined);
    });

    // Defensive logout invariant.
    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');

    // No cache mutation on the auth-failure path.
    expect(mockMutate).not.toHaveBeenCalled();
  });
});
