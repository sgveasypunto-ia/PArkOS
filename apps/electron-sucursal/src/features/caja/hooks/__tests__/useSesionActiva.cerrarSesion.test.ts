/**
 * `useSesionActiva.cerrarSesion.test.ts` — Strict-TDD RED scaffold for
 * HU-F10.2 (REQ-OPS-160, AD-4).
 *
 * Verifies the new `cerrarSesion` method on `useSesionActiva()`:
 *   - Wraps `sesionActivaApi.cerrarSesion(uuid, payload)`.
 *   - On 200: clears authStore + dispatches `parkos:auth:cleared` and
 *     returns `{ ok: true, status: 200, sesion }`. The helper owns
 *     the F3.3 logout-on-success trifecta (DEC-F3.3-03 + Engram #1899)
 *     so the orchestrator only has to `navigate`.
 *   - On 4xx/5xx: returns `{ ok: false, status, error }` preserving
 *     the typed exception. The helper does NOT clear the authStore —
 *     the caller decides based on the status (e.g. 401 falls into the
 *     helper too per F3.3 fallback).
 *
 * Drift anchor: REQ-OPS-160 + AD-4 + AD-5 (logout preserved verbatim).
 * Uses `renderHook` from `@testing-library/react` (canonical pattern
 * in this codebase for hook unit tests — see useRegistrarPago.test.ts
 * precedent). Mocks SWR so the GET leg doesn't fire and the hook
 * cleanly returns `{ sesion: null, cerrarSesion, ... }`.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Mock the auth store so we can inspect `clear` + the
// `parkos:auth:cleared` window event without touching real Zustand.
const clearMock = vi.fn();
const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true);

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (_selector: unknown) => undefined,
    { getState: () => ({ clear: clearMock }) },
  ),
}));

// Mock sesionActivaApi so we can drive the helper from tests.
// NB: this test lives in `hooks/__tests__/`, so the relative path to
// `features/caja/api/sesionActivaApi.ts` is `../../api/sesionActivaApi`
// (from `hooks/__tests__/`). Using the wrong relative path silently
// lets the mock miss the production import — the production code
// keeps the real module and the test fails with status=0 / wrong args.
const cerrarSesionApiMock = vi.fn();
vi.mock('../../api/sesionActivaApi', () => ({
  cerrarSesion: (...args: unknown[]) => cerrarSesionApiMock(...args),
  getSesionActiva: vi.fn().mockResolvedValue(null),
  SesionAlreadyClosedError: class SesionAlreadyClosedError extends Error {
    override readonly name = 'SesionAlreadyClosedError';
    constructor(
      public readonly status: number,
      public readonly body: string,
      public readonly url: string,
    ) {
      super('sesion_not_found');
    }
  },
}));

// Mock SWR — the GET leg must not fire during these unit tests.
vi.mock('swr', () => ({
  default: () => ({
    data: undefined,
    error: undefined,
    isLoading: false,
    mutate: vi.fn(),
  }),
}));

vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class ParkosHttpError extends Error {
    public readonly status: number;
    public readonly body: string;
    public readonly url: string;
    constructor(status: number, body = '{}', url = '/api/v1/x') {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
}));

beforeEach(() => {
  clearMock.mockReset();
  cerrarSesionApiMock.mockReset();
  dispatchEventSpy.mockClear();
});

afterEach(() => {
  vi.clearAllMocks();
});

// Re-import AFTER mocks are registered.
import { useSesionActiva } from '../useSesionActiva';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

describe('HU-F10.2 — useSesionActiva().cerrarSesion helper (REQ-OPS-160, AD-4)', () => {
  // ────────────────────────────────────────────────────────────────────
  // helper-1-200-clear-event — happy path clears authStore + fires event
  // ────────────────────────────────────────────────────────────────────
  it('helper-1: 200 OK → useAuthStore.clear() + parkos:auth:cleared event + { ok: true, status: 200, sesion }', async () => {
    const sesionCerrada = {
      uuid: 'sess-uuid-1',
      timestamp_cierre: '2026-09-21T18:00:00Z',
    };
    cerrarSesionApiMock.mockResolvedValueOnce(sesionCerrada);

    const { result } = renderHook(() => useSesionActiva());
    expect(typeof result.current.cerrarSesion).toBe('function');

    let resolved: unknown;
    await act(async () => {
      resolved = await result.current.cerrarSesion('sess-uuid-1', {
        valor_final_efectivo: 75_000,
        valor_final_datafono: 25_000,
      });
    });

    // Helper awaits the API with the same wire body.
    expect(cerrarSesionApiMock).toHaveBeenCalledWith('sess-uuid-1', {
      valor_final_efectivo: 75_000,
      valor_final_datafono: 25_000,
    });

    // F3.3 logout-on-success trifecta — the helper owns it.
    expect(clearMock).toHaveBeenCalledTimes(1);
    expect(dispatchEventSpy).toHaveBeenCalledWith(expect.any(Event));
    const event = dispatchEventSpy.mock.calls[0]?.[0] as Event;
    expect(event?.type).toBe('parkos:auth:cleared');

    // Result is the typed `ok: true` envelope.
    expect(resolved).toEqual({ ok: true, status: 200, sesion: sesionCerrada });
  });

  // ────────────────────────────────────────────────────────────────────
  // helper-2 — 409 sesion_ya_cerrada → { ok: false, status: 409 } NO clear
  // ────────────────────────────────────────────────────────────────────
  it('helper-2: 409 sesion_ya_cerrada → { ok: false, status: 409, error } WITHOUT clearing authStore', async () => {
    cerrarSesionApiMock.mockRejectedValueOnce(
      new ParkosHttpError(
        409,
        '{"error":"sesion_ya_cerrada"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    );

    const { result } = renderHook(() => useSesionActiva());

    let resolved: unknown;
    await act(async () => {
      resolved = await result.current.cerrarSesion('sess-uuid-1', {
        valor_final_efectivo: 0,
        valor_final_datafono: 0,
      });
    });

    expect(resolved).toMatchObject({ ok: false, status: 409 });
    // Critically: NO clear, NO event — the operator stays on route.
    expect(clearMock).not.toHaveBeenCalled();
    expect(dispatchEventSpy).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // helper-3 — 401 → F3.3 fallback: clear + event (preserved verbatim)
  // ────────────────────────────────────────────────────────────────────
  it('helper-3: 401 mid-flow → F3.3 fallback: clear() + parkos:auth:cleared event + { ok: false, status: 401 }', async () => {
    cerrarSesionApiMock.mockRejectedValueOnce(
      new ParkosHttpError(
        401,
        '{"error":"unauthorized"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    );

    const { result } = renderHook(() => useSesionActiva());

    let resolved: unknown;
    await act(async () => {
      resolved = await result.current.cerrarSesion('sess-uuid-1', {
        valor_final_efectivo: 0,
        valor_final_datafono: 0,
      });
    });

    expect(resolved).toMatchObject({ ok: false, status: 401 });
    // F3.3 fallback: clear + event fire even on 401.
    expect(clearMock).toHaveBeenCalledTimes(1);
    expect(dispatchEventSpy).toHaveBeenCalledWith(expect.any(Event));
    const event = dispatchEventSpy.mock.calls[0]?.[0] as Event;
    expect(event?.type).toBe('parkos:auth:cleared');
  });

  // ────────────────────────────────────────────────────────────────────
  // helper-4 — network error → { ok: false, error } NO clear, NO event
  // ────────────────────────────────────────────────────────────────────
  it('helper-4: network error (TypeError on fetch) → { ok: false, error } WITHOUT clearing authStore', async () => {
    cerrarSesionApiMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));

    const { result } = renderHook(() => useSesionActiva());

    let resolved: unknown;
    await act(async () => {
      resolved = await result.current.cerrarSesion('sess-uuid-1', {
        valor_final_efectivo: 0,
        valor_final_datafono: 0,
      });
    });

    expect(resolved).toMatchObject({ ok: false, status: 0 });
    expect(clearMock).not.toHaveBeenCalled();
    expect(dispatchEventSpy).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // helper-5 — 5xx → { ok: false, status: 5xx } NO clear, NO event
  // ────────────────────────────────────────────────────────────────────
  it('helper-5: 5xx server error → { ok: false, status: 500, error } WITHOUT clearing authStore', async () => {
    cerrarSesionApiMock.mockRejectedValueOnce(
      new ParkosHttpError(
        500,
        '{"error":"server_error"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    );

    const { result } = renderHook(() => useSesionActiva());

    let resolved: unknown;
    await act(async () => {
      resolved = await result.current.cerrarSesion('sess-uuid-1', {
        valor_final_efectivo: 0,
        valor_final_datafono: 0,
      });
    });

    expect(resolved).toMatchObject({ ok: false, status: 500 });
    expect(clearMock).not.toHaveBeenCalled();
    expect(dispatchEventSpy).not.toHaveBeenCalled();
  });
});