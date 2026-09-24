/**
 * Tests for `useAnularSalidaNoPagada` SWR mutation hook
 * (HU-F8.1-anular-salida-no-pagada, 2026-09-23).
 *
 * Coverage (3 tests):
 *   A1: trigger → 201 → POST path includes the uuid_salida path
 *       param + body matches `AnularSalidaNoPagadaPayload`
 *       contract (`{ motivo }` with min 10 chars) +
 *       Idempotency-Key SHA-256 header on the wire.
 *   A2: doble trigger with same uuid_salida → SAME Idempotency-Key
 *       header (server-side cache dedup, no duplicate annulment).
 *   A3: 401 → `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *       event (preserved F3.1 invariant).
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

import {
  useAnularSalidaNoPagada,
  MOTIVO_AUTO_ANULACION_SALIDA,
} from './useAnularSalidaNoPagada';
import { useAuthStore } from '@parkos/ui-kit/store';

const UUID_SALIDA = '00000000-0000-0000-0000-0000000000bb';
const EXPECTED_PATH = `/api/v1/operacion/salidas/${UUID_SALIDA}/anular-no-pagada`;

const annulationRead = {
  uuid: '00000000-0000-0000-0000-0000000000cc',
  uuid_sucursal: '00000000-0000-0000-0000-0000000000a2',
  tipo_anulable: 'salida',
  uuid_salida: UUID_SALIDA,
  motivo: MOTIVO_AUTO_ANULACION_SALIDA,
  created_at: '2026-09-23T18:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useAnularSalidaNoPagada — F8.1-b (auto-annul salida on close-without-pay)', () => {
  it('A1: trigger → 201 → POST path includes uuid_salida + body matches AnularSalidaNoPagadaPayload + Idempotency-Key SHA-256', async () => {
    mockFetch.mockResolvedValueOnce(annulationRead);

    const { result } = renderHook(() => useAnularSalidaNoPagada());

    await act(async () => {
      await result.current.trigger({ uuid_salida: UUID_SALIDA });
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe(EXPECTED_PATH);
    const reqInit = mockFetch.mock.calls[0]?.[1] as {
      method: string;
      body: string;
      headers: Record<string, string>;
    };
    expect(reqInit.method).toBe('POST');
    const parsedBody = JSON.parse(reqInit.body) as Record<string, unknown>;
    expect(parsedBody.motivo).toBe(MOTIVO_AUTO_ANULACION_SALIDA);
    expect((parsedBody.motivo as string).length).toBeGreaterThanOrEqual(10);
    // uuid_salida is in the path, not the body (custom endpoint
    // contract — AnularSalidaNoPagadaPayload does not carry it).
    expect('uuid_salida' in parsedBody).toBe(false);
    expect('tipo_anulable' in parsedBody).toBe(false);
    // Idempotency-Key SHA-256 hex (64 chars).
    expect(reqInit.headers['Idempotency-Key']).toMatch(/^[a-f0-9]{64}$/);
  });

  it('A2: doble trigger with same uuid_salida → SAME Idempotency-Key header (server dedup)', async () => {
    mockFetch.mockResolvedValue(annulationRead);

    const { result } = renderHook(() => useAnularSalidaNoPagada());

    await act(async () => {
      await result.current.trigger({ uuid_salida: UUID_SALIDA });
    });
    await act(async () => {
      await result.current.trigger({ uuid_salida: UUID_SALIDA });
    });

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const headers1 = (mockFetch.mock.calls[0]?.[1] as { headers: Record<string, string> }).headers;
    const headers2 = (mockFetch.mock.calls[1]?.[1] as { headers: Record<string, string> }).headers;
    expect(headers1['Idempotency-Key']).toBe(headers2['Idempotency-Key']);
  });

  it('A3: 401 → useAuthStore.clear() + parkos:auth:cleared event', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(401, '{"error":"token_expired"}', EXPECTED_PATH),
    );

    const { result } = renderHook(() => useAnularSalidaNoPagada());

    await act(async () => {
      await result.current
        .trigger({ uuid_salida: UUID_SALIDA })
        .catch(() => undefined);
    });

    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});
