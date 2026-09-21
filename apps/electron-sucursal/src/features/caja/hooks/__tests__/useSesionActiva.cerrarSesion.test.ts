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
 * These 5 RED scenarios MUST FAIL on master because `cerrarSesion` is
 * not yet a method on the hook. After Commit 2 lands the helper, they
 * go GREEN.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';

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
const cerrarSesionApiMock = vi.fn();
vi.mock('../api/sesionActivaApi', () => ({
  cerrarSesion: (...args: unknown[]) => cerrarSesionApiMock(...args),
  SesionAlreadyClosedError: class SesionAlreadyClosedError extends Error {
    readonly name = 'SesionAlreadyClosedError';
    constructor(
      public readonly status: number,
      public override readonly body: string,
      public readonly url: string,
    ) {
      super('sesion_not_found');
    }
  },
}));

// Mock SWR — the hook uses SWR for the GET leg; for the new helper
// test we only care about `useSesionActiva().cerrarSesion(...)` which
// is a plain async method, not an SWR key. Provide a minimal mock.
let capturedFetcher: (() => Promise<unknown>) | undefined;
let capturedKey: string | null | undefined;
vi.mock('swr', () => ({
  default: (
    key: string | null | undefined,
    fetcher: () => Promise<unknown>,
  ) => {
    capturedKey = key;
    capturedFetcher = fetcher;
    return {
      data: undefined,
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    };
  },
}));

// Capture the SWR `onError` so we can drive the 401 branch if needed.
let capturedOnError: ((err: unknown) => void) | undefined;
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

// Re-import AFTER mocks are registered.
import { useSesionActiva } from '../useSesionActiva';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

beforeEach(() => {
  clearMock.mockReset();
  cerrarSesionApiMock.mockReset();
  dispatchEventSpy.mockClear();
  capturedOnError = undefined;
});

afterEach(() => {
  vi.clearAllMocks();
});

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

    const { cerrarSesion } = useSesionActiva();
    const result = await cerrarSesion('sess-uuid-1', {
      valor_final_efectivo: 75_000,
      valor_final_datafono: 25_000,
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
    expect(result).toEqual({ ok: true, status: 200, sesion: sesionCerrada });
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

    const { cerrarSesion } = useSesionActiva();
    const result = await cerrarSesion('sess-uuid-1', {
      valor_final_efectivo: 0,
      valor_final_datafono: 0,
    });

    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.status).toBe(409);
      expect(result.error).toBeInstanceOf(ParkosHttpError);
    }
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

    const { cerrarSesion } = useSesionActiva();
    const result = await cerrarSesion('sess-uuid-1', {
      valor_final_efectivo: 0,
      valor_final_datafono: 0,
    });

    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.status).toBe(401);
    }
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

    const { cerrarSesion } = useSesionActiva();
    const result = await cerrarSesion('sess-uuid-1', {
      valor_final_efectivo: 0,
      valor_final_datafono: 0,
    });

    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.status).toBe(0);
      expect(result.error).toBeInstanceOf(TypeError);
    }
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

    const { cerrarSesion } = useSesionActiva();
    const result = await cerrarSesion('sess-uuid-1', {
      valor_final_efectivo: 0,
      valor_final_datafono: 0,
    });

    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.status).toBe(500);
      expect(result.error).toBeInstanceOf(ParkosHttpError);
    }
    expect(clearMock).not.toHaveBeenCalled();
    expect(dispatchEventSpy).not.toHaveBeenCalled();
  });
});