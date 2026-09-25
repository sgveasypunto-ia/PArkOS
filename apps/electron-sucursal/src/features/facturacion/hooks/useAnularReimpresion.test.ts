/**
 * Tests for `useAnularReimpresion` SWR mutation hook
 * (HU-F8.3, REQ-OPS-174).
 *
 * Coverage (2 tests):
 *   A1: trigger → 201 → returns parsed `ReimpresionTicketRead` with
 *       `workflow_estado='rechazada'` + `uuid_reimpresion_padre=<original>`
 *       (F1.11 DEC-TKT-03 insert-only invariant — backend INSERTs a
 *       NEW row, NEVER UPDATEs the original).
 *   A2: motivo_anulacion <10 chars → ZodError BEFORE the POST fires.
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

import { useAnularReimpresion } from './useAnularReimpresion';

const UUID_REIMPRESION_ORIGINAL = '00000000-0000-0000-0000-000000000099';
const UUID_REIMPRESION_NEW = '00000000-0000-0000-0000-0000000000bb';
const UUID_INGRESO = '00000000-0000-0000-0000-000000000001';

/**
 * F1.11 DEC-TKT-03 — the anulación response carries the NEW row's
 * uuid + `workflow_estado='rechazada'` + `uuid_reimpresion_padre`
 * pointing at the original chain tip.
 */
const anulacionRead = {
  uuid: UUID_REIMPRESION_NEW,
  workflow_estado: 'rechazada',
  uuid_reimpresion_padre: UUID_REIMPRESION_ORIGINAL,
  uuid_ingreso: UUID_INGRESO,
  uuid_factura: null,
  costo_aplicado: 5000,
  motivo: 'Original reimpresion authorized correctly',
  motivo_anulacion: 'Error operativo: se reimprimio por error administrativo',
  created_at: '2026-09-19T12:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useAnularReimpresion — REQ-OPS-174 (F1.11 insert-only chain)', () => {
  it('A1: trigger → 201 → returns parsed ReimpresionTicketRead with workflow_estado=rechazada + uuid_reimpresion_padre', async () => {
    mockFetch.mockResolvedValueOnce(anulacionRead);

    const { result } = renderHook(() => useAnularReimpresion());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger({
        uuidReimpresion: UUID_REIMPRESION_ORIGINAL,
        motivo_anulacion: 'Error operativo: se reimprimio por error administrativo',
      });
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe(
      `/api/v1/workflows/reimpresion-ticket/${UUID_REIMPRESION_ORIGINAL}/anular`,
    );
    expect(mockFetch.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
      headers: { 'Idempotency-Key': expect.any(String) },
    });
    expect((data as { uuid: string }).uuid).toBe(UUID_REIMPRESION_NEW);
    expect((data as { workflow_estado: string }).workflow_estado).toBe('rechazada');
    expect((data as { uuid_reimpresion_padre: string }).uuid_reimpresion_padre).toBe(
      UUID_REIMPRESION_ORIGINAL,
    );
  });

  it('A2: motivo_anulacion <10 chars → ZodError before POST fires', async () => {
    const { result } = renderHook(() => useAnularReimpresion());

    let captured: unknown;
    await act(async () => {
      try {
        await result.current.trigger({
          uuidReimpresion: UUID_REIMPRESION_ORIGINAL,
          motivo_anulacion: 'corto', // 5 chars
        });
      } catch (err) {
        captured = err;
      }
    });

    expect(captured).toBeInstanceOf(ZodError);
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
