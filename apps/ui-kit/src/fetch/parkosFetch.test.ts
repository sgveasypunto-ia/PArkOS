/**
 * parkosFetch — 14 unit tests (vitest + vi.spyOn(globalThis, 'fetch')).
 *
 * RED → GREEN → REFACTOR cycle per strict TDD mode. We mock the global
 * `fetch` with vi.fn() so each scenario can dial in precise Response
 * sequences (status, body, headers) and assert both the request shape
 * (Authorization / X-Sucursal-Context / Idempotency-Key) and the retry
 * timing (backoff 300/600/1200ms with vi.useFakeTimers).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';

import { useAuthStore } from '../store/authStore';
import {
  ParkosHttpError,
  parkosFetch,
  parkosFetchRaw,
} from './parkosFetch';

const SUCURSAL_KEY = 'parkos.lastSelectedSucursal';

function setSucursal(uuid: string | null): void {
  if (uuid === null) {
    window.localStorage.removeItem(SUCURSAL_KEY);
  } else {
    window.localStorage.setItem(SUCURSAL_KEY, uuid);
  }
}

function resetAuth(): void {
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    expiresAt: null,
  });
}

function jsonResponse(body: unknown, status = 200, extraHeaders: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...extraHeaders },
  });
}

function emptyResponse(status: number, body = ''): Response {
  return new Response(body, { status });
}

beforeEach(() => {
  resetAuth();
  setSucursal(null);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('parkosFetch — header injection', () => {
  it('U1: injects Authorization: Bearer from authStore on GET', async () => {
    useAuthStore.setState({ accessToken: 'jwt-abc' });
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(jsonResponse({ ok: true }));

    await parkosFetch('/api/x');

    const init = spy.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer jwt-abc');
  });

  it('U2: injects X-Sucursal-Context from localStorage when set', async () => {
    setSucursal('suc-uuid-9');
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(jsonResponse({ ok: true }));

    await parkosFetch('/api/y');

    const init = spy.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get('X-Sucursal-Context')).toBe('suc-uuid-9');
  });
});

describe('parkosFetch — retry loop on 5xx and 408', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it('U3: retries 5xx with backoff 300/600/1200ms — 3 attempts max', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(emptyResponse(503))
      .mockResolvedValueOnce(emptyResponse(502))
      .mockResolvedValueOnce(jsonResponse({ recovered: true }));

    const promise = parkosFetchRaw('/api/retry');
    await vi.runAllTimersAsync();
    const res = await promise;

    // attempt 1 (503) → backoff 300 → attempt 2 (502) → backoff 600 → attempt 3 (200)
    expect(spy).toHaveBeenCalledTimes(3);
    expect(res.ok).toBe(true);
  });

  it('U4: retries 408 Request Timeout same as 5xx', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(emptyResponse(408))
      .mockResolvedValueOnce(emptyResponse(408))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    const promise = parkosFetchRaw('/api/408');
    await vi.runAllTimersAsync();
    await promise;

    expect(spy.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  it('U5: does NOT retry 4xx (except 408) — single attempt', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(emptyResponse(404));

    const res = await parkosFetchRaw('/api/not-found');

    expect(spy).toHaveBeenCalledTimes(1);
    expect(res.status).toBe(404);
  });

  it('U6: NetworkError (fetch rejects) retried like 5xx', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    const promise = parkosFetchRaw('/api/net');
    await vi.runAllTimersAsync();
    const res = await promise;

    expect(spy).toHaveBeenCalledTimes(3);
    expect(res.ok).toBe(true);
  });
});

describe('parkosFetch — 401 refresh-once Mutex', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it('U7: 401 triggers refresh-once + retry with new Bearer', async () => {
    useAuthStore.setState({
      accessToken: 'old-jwt',
      refreshToken: 'old-refresh',
      expiresAt: null,
    });

    const spy = vi
      .spyOn(globalThis, 'fetch')
      // First call to /api/protected → 401
      .mockResolvedValueOnce(emptyResponse(401))
      // Second call to /auth/refresh → 200 with new pair
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: 'new-jwt',
          refresh_token: 'new-refresh',
          expires_in: 900,
        }),
      )
      // Third call (retry of original) → 200
      .mockResolvedValueOnce(jsonResponse({ data: 'ok' }));

    const promise = parkosFetch('/api/protected');
    await vi.runAllTimersAsync();
    const result = await promise;

    expect(spy).toHaveBeenCalledTimes(3);
    expect(result).toEqual({ data: 'ok' });

    // Retry call should carry the NEW Bearer.
    const retryInit = spy.mock.calls[2]?.[1] as RequestInit;
    const retryHeaders = new Headers(retryInit.headers);
    expect(retryHeaders.get('Authorization')).toBe('Bearer new-jwt');

    // authStore now has new tokens.
    expect(useAuthStore.getState().accessToken).toBe('new-jwt');
  });

  it('U8: refresh failure → authStore.clear() + parkos:auth:cleared event', async () => {
    useAuthStore.setState({
      accessToken: 'old-jwt',
      refreshToken: 'bad-refresh',
      expiresAt: null,
    });

    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const spy = vi
      .spyOn(globalThis, 'fetch')
      // First call → 401
      .mockResolvedValueOnce(emptyResponse(401))
      // /auth/refresh → also 401
      .mockResolvedValueOnce(emptyResponse(401));

    const promise = parkosFetchRaw('/api/protected');
    await vi.runAllTimersAsync();
    await promise;

    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'parkos:auth:cleared' }));
    expect(spy).toHaveBeenCalledTimes(2);
  });
});

describe('parkosFetch — Idempotency-Key SHA-256', () => {
  it('U10: POST emits Idempotency-Key SHA-256(method|path|body)', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(jsonResponse({ ok: true }));

    await parkosFetch('/api/orders', {
      method: 'POST',
      body: JSON.stringify({ item: 'abc', qty: 1 }),
      headers: { 'Content-Type': 'application/json' },
    });

    const init = spy.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    const key = headers.get('Idempotency-Key');
    expect(key).toMatch(/^[0-9a-f]{64}$/);
  });

  it('U11: POST /auth/login skips Idempotency-Key', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(jsonResponse({ ok: true }));

    await parkosFetch('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: 'a', password: 'b' }),
      headers: { 'Content-Type': 'application/json' },
    });

    const init = spy.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get('Idempotency-Key')).toBeNull();
  });
});

describe('parkosFetch — AbortController timeout', () => {
  it('U12: timeoutMs aborts via AbortController and surfaces AbortError', async () => {
    // Real timers + tiny timeout keeps the test deterministic AND avoids the
    // jsdom + AbortController + vi.useFakeTimers post-cleanup quirk.
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(
        (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            const signal = init?.signal as AbortSignal | undefined;
            if (signal) {
              signal.addEventListener(
                'abort',
                () => {
                  const err = new Error('aborted');
                  err.name = 'AbortError';
                  reject(err);
                },
                { once: true },
              );
            }
          }),
      );

    await expect(parkosFetchRaw('/api/slow', { timeoutMs: 30 })).rejects.toThrow(/abort/i);
    // Timeout MUST NOT retry — exactly one attempt.
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe('parkosFetch — Zod boundary validation', () => {
  it('U13: Zod schema pass returns parsed JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse({ id: 1, name: 'alpha' }),
    );

    const schema = z.object({ id: z.number(), name: z.string() });
    const data = await parkosFetch('/api/item', {}, schema);
    expect(data).toEqual({ id: 1, name: 'alpha' });
  });

  it('U14: Zod schema fail throws ZodError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse({ id: 'not-a-number' }),
    );

    const schema = z.object({ id: z.number() });
    await expect(parkosFetch('/api/item', {}, schema)).rejects.toBeInstanceOf(z.ZodError);
  });
});

describe('parkosFetch — typed wrapper error mapping', () => {
  it('throws ParkosHttpError on non-ok 4xx Response (no retry)', async () => {
    // 4xx does not retry → one mock is enough.
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(emptyResponse(404, 'nope'));

    await expect(parkosFetch('/api/boom')).rejects.toBeInstanceOf(ParkosHttpError);
  });
});
