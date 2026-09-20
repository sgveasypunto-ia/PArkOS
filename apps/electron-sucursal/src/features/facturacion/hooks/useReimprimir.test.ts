/**
 * Tests for `useReimprimir` SWR mutation hook (HU-F8.3, REQ-OPS-173).
 *
 * Coverage (3 tests):
 *   T1: trigger → 201 → returns parsed `ReimpresionTicketRead`
 *       (discriminated union on `workflow_estado`; `uuid_factura`
 *       nullable per DEC-TKT-04).
 *   T2: motivo <10 chars → ZodError BEFORE the POST fires
 *       (defense in depth — never trust client validation, but
 *       pre-validate to avoid round-trips).
 *   T3: 401 → `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *       event (preserved F3.1 invariant from REQ-OPS-107..110;
 *       mirrors `useRegistrarPago` + `useReintentarFE`).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

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

import { useReimprimir } from './useReimprimir';
import { useAuthStore } from '@parkos/ui-kit/store';

const UUID_INGRESO = '00000000-0000-0000-0000-000000000001';
const UUID_REIMPRESION = '00000000-0000-0000-0000-0000000000aa';

const reimpresionRead = {
  uuid: UUID_REIMPRESION,
  workflow_estado: 'autorizada',
  uuid_reimpresion_padre: null,
  uuid_ingreso: UUID_INGRESO,
  uuid_factura: null,
  motivo: 'Cliente solicita reimpresion por deterioro del tiquete original',
  created_at: '2026-09-19T11:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
  (useAuthStore.getState().clear as ReturnType<typeof vi.fn>).mockClear();
});

describe('useReimprimir — REQ-OPS-173 (F1.11 reimpresion-ticket POST + Idempotency-Key)', () => {
  it('T1: trigger → 201 → returns parsed ReimpresionTicketRead', async () => {
    mockFetch.mockResolvedValueOnce(reimpresionRead);

    const { result } = renderHook(() => useReimprimir());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger({
        uuidIngreso: UUID_INGRESO,
        motivo: 'Cliente solicita reimpresion por deterioro del original',
        tipo: 'entrada',
      });
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe(
      `/api/v1/workflows/reimpresion-ticket/${UUID_INGRESO}/reimprimir`,
    );
    expect(mockFetch.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
      headers: { 'Idempotency-Key': expect.any(String) },
    });
    expect((data as { uuid: string }).uuid).toBe(UUID_REIMPRESION);
    expect((data as { workflow_estado: string }).workflow_estado).toBe('autorizada');
    expect((data as { uuid_factura: string | null }).uuid_factura).toBeNull();
  });

  it('T2: motivo <10 chars → ZodError before POST fires', async () => {
    const { result } = renderHook(() => useReimprimir());

    let captured: unknown;
    await act(async () => {
      try {
        await result.current.trigger({
          uuidIngreso: UUID_INGRESO,
          motivo: 'corto', // 5 chars
          tipo: 'entrada',
        });
      } catch (err) {
        captured = err;
      }
    });

    expect(captured).toBeInstanceOf(ZodError);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('T3: 401 → useAuthStore.clear() + parkos:auth:cleared event', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(401, '{"error":"token_expired"}', '/api/v1/workflows/reimpresion-ticket'),
    );

    const { result } = renderHook(() => useReimprimir());

    await act(async () => {
      await result.current
        .trigger({
          uuidIngreso: UUID_INGRESO,
          motivo: 'Cliente solicita reimpresion por error de operario',
          tipo: 'salida',
        })
        .catch(() => undefined);
    });

    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});
