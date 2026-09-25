/**
 * Tests for `useReimprimir` SWR mutation hook (HU-F8.3, REQ-OPS-173).
 *
 * BUGFIX (2026-09-25, directiva del operador): reescrito — la versión
 * anterior probaba una ruta (`.../{uuid}/reimprimir`) y un body
 * (`{motivo, tipo}`) que el backend real NUNCA implementó. El contrato
 * real (`workflows_reimpresion.py::create_reimpresion_ticket`) es
 * `POST /api/v1/workflows/reimpresion-ticket` (ruta raíz) con body
 * `{uuid_ingreso, motivo, uuid_factura?}` — `tipo` no viaja al backend.
 *
 * Coverage (3 tests):
 *   T1: trigger → 201 → returns parsed `ReimpresionTicketRead`
 *       (incluye `costo_aplicado`, el snapshot de `costos_servicios`).
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
  costo_aplicado: 5000,
  motivo: 'Cliente solicita reimpresion por deterioro del tiquete original',
  created_at: '2026-09-19T11:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
  (useAuthStore.getState().clear as ReturnType<typeof vi.fn>).mockClear();
});

describe('useReimprimir — REQ-OPS-173 (F1.11 reimpresion-ticket POST raíz + Idempotency-Key)', () => {
  it('T1: trigger → 201 → returns parsed ReimpresionTicketRead con costo_aplicado', async () => {
    mockFetch.mockResolvedValueOnce(reimpresionRead);

    const { result } = renderHook(() => useReimprimir());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger({
        uuid_ingreso: UUID_INGRESO,
        motivo: 'Cliente solicita reimpresion por deterioro del original',
      });
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe('/api/v1/workflows/reimpresion-ticket');
    expect(mockFetch.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
      headers: { 'Idempotency-Key': expect.any(String) },
    });
    const sentBody = JSON.parse(
      (mockFetch.mock.calls[0]?.[1] as { body: string }).body,
    ) as Record<string, unknown>;
    expect(sentBody).toEqual({
      uuid_ingreso: UUID_INGRESO,
      motivo: 'Cliente solicita reimpresion por deterioro del original',
    });
    expect((data as { uuid: string }).uuid).toBe(UUID_REIMPRESION);
    expect((data as { workflow_estado: string }).workflow_estado).toBe('autorizada');
    expect((data as { uuid_factura: string | null }).uuid_factura).toBeNull();
    expect((data as { costo_aplicado: number | null }).costo_aplicado).toBe(5000);
  });

  it('T2: motivo <10 chars → ZodError before POST fires', async () => {
    const { result } = renderHook(() => useReimprimir());

    let captured: unknown;
    await act(async () => {
      try {
        await result.current.trigger({
          uuid_ingreso: UUID_INGRESO,
          motivo: 'corto', // 5 chars
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
          uuid_ingreso: UUID_INGRESO,
          motivo: 'Cliente solicita reimpresion por error de operario',
        })
        .catch(() => undefined);
    });

    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});
