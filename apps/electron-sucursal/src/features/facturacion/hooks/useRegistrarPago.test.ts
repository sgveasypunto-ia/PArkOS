/**
 * Tests for `useRegistrarPago` SWR mutation hook (HU-F8.1, REQ-OPS-167).
 *
 * Coverage (4 tests):
 *   P1: trigger → 201 → returns parsed `FacturaRead` (discriminated
 *       union by `medio_pago`); the parser enforces the FE toggle +
 *       nit/email invariants (DEC-SUC-04 + BR7 + Email RFC 5322).
 *   P2: trigger in-flight → `isMutating=true` observable between the
 *       fetch start and the 201 response.
 *   P3: 401 → `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *       event (preserved F3.1 invariant; mirrors `useRegistrarSalida`).
 *   P4: doble trigger with same body → SAME Idempotency-Key SHA-256
 *       header on both calls (server-side `IdempotencyKeyMiddleware`
 *       F1.6 dedups the second POST).
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

import { useRegistrarPago } from './useRegistrarPago';
import { useAuthStore } from '@parkos/ui-kit/store';

const UUID_INGRESO = '00000000-0000-0000-0000-000000000001';
const UUID_FACTURA = '00000000-0000-0000-0000-0000000000aa';

const facturaEfectivoRead = {
  uuid: UUID_FACTURA,
  uuid_sucursal: '00000000-0000-0000-0000-0000000000a2',
  uuid_ingreso: UUID_INGRESO,
  created_at: '2026-09-19T11:00:00Z',
  medio_pago: 'efectivo',
  monto_recibido_cents: 50000,
  total_cents: 41000,
  vuelto_cents: 9000,
  numero_recibo: 'sucursal-20260919-000001',
  cliente: {
    nit: '222222222222222',
    nombre: 'Consumidor final',
    email: null,
  },
  factura_electronica: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useRegistrarPago — REQ-OPS-167 (FE consumidor final + Idempotency-Key)', () => {
  it('P1: trigger → 201 → returns parsed FacturaRead with FE consumidor final default', async () => {
    mockFetch.mockResolvedValueOnce(facturaEfectivoRead);

    const { result } = renderHook(() => useRegistrarPago());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger({
        uuid_ingreso: UUID_INGRESO,
        medio_pago: 'efectivo',
        monto_recibido_cents: 50000,
        total_cents: 41000,
        cliente: {
          nit: '222222222222222',
          nombre: 'Consumidor final',
        },
      });
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe('/api/v1/facturacion/factura');
    expect(mockFetch.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
    });
    expect((data as { uuid: string }).uuid).toBe(UUID_FACTURA);
    expect((data as { medio_pago: string }).medio_pago).toBe('efectivo');
    expect((data as { numero_recibo: string }).numero_recibo).toMatch(
      /^sucursal-\d{8}-\d{6}$/,
    );
    expect(result.current.isMutating).toBe(false);
  });

  it('P2: trigger in-flight → isMutating=true observable during the POST', async () => {
    // Resolve the POST on the next microtask so we can observe
    // isMutating === true synchronously after the trigger call.
    let resolveFn: (v: unknown) => void = () => undefined;
    const pending = new Promise<unknown>((res) => {
      resolveFn = res;
    });
    mockFetch.mockReturnValueOnce(pending);

    const { result } = renderHook(() => useRegistrarPago());

    let triggerPromise: Promise<unknown> = Promise.resolve();
    act(() => {
      triggerPromise = result.current.trigger({
        uuid_ingreso: UUID_INGRESO,
        medio_pago: 'efectivo',
        monto_recibido_cents: 50000,
        total_cents: 41000,
        cliente: {
          nit: '222222222222222',
          nombre: 'Consumidor final',
        },
      });
    });
    // Yield to React so useSWRMutation flips isMutating to true.
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.isMutating).toBe(true);

    await act(async () => {
      resolveFn(facturaEfectivoRead);
      await triggerPromise;
    });
    expect(result.current.isMutating).toBe(false);
  });

  it('P3: 401 → useAuthStore.clear() + parkos:auth:cleared event', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(401, '{"error":"token_expired"}', '/api/v1/facturacion/factura'),
    );

    const { result } = renderHook(() => useRegistrarPago());

    await act(async () => {
      await result.current
        .trigger({
          uuid_ingreso: UUID_INGRESO,
          medio_pago: 'efectivo',
          monto_recibido_cents: 50000,
          total_cents: 41000,
          cliente: { nit: '222222222222222', nombre: 'Consumidor final' },
        })
        .catch(() => undefined);
    });

    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });

  it('P4: doble trigger with same body → SAME Idempotency-Key header (server dedup)', async () => {
    mockFetch.mockResolvedValue(facturaEfectivoRead);

    const { result } = renderHook(() => useRegistrarPago());

    await act(async () => {
      await result.current.trigger({
        uuid_ingreso: UUID_INGRESO,
        medio_pago: 'efectivo',
        monto_recibido_cents: 50000,
        total_cents: 41000,
        cliente: { nit: '222222222222222', nombre: 'Consumidor final' },
      });
    });
    await act(async () => {
      await result.current.trigger({
        uuid_ingreso: UUID_INGRESO,
        medio_pago: 'efectivo',
        monto_recibido_cents: 50000,
        total_cents: 41000,
        cliente: { nit: '222222222222222', nombre: 'Consumidor final' },
      });
    });

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const headers1 = (mockFetch.mock.calls[0]?.[1] as { headers: Record<string, string> }).headers;
    const headers2 = (mockFetch.mock.calls[1]?.[1] as { headers: Record<string, string> }).headers;
    expect(headers1['Idempotency-Key']).toMatch(/^[a-f0-9]{64}$/);
    expect(headers1['Idempotency-Key']).toBe(headers2['Idempotency-Key']);
  });
});