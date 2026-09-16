/**
 * Unit tests for `electron/services/api-status.ts` (F2.3 — T2, DEC-UPD-05/06).
 *
 * RED → GREEN → REFACTOR coverage:
 *   A1: 2xx response → `{ok:true, latency_ms:N, code:200}`.
 *   A2: 4xx/5xx response → `{ok:false, code:500, latency_ms:N}`.
 *   A3: timeout 5s vía AbortController → `{ok:false, code:undefined, latency_ms:-1}`.
 *   A4: cache `getApiStatus()` antes del primer ping → `{ok:false, latency_ms:-1}`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  initApiStatus,
  getApiStatus,
  type ApiStatusValue,
} from './api-status';

interface LogStub {
  info: ReturnType<typeof vi.fn>;
  warn: ReturnType<typeof vi.fn>;
  debug: ReturnType<typeof vi.fn>;
  error: ReturnType<typeof vi.fn>;
}

function makeLog(): LogStub {
  return { info: vi.fn(), warn: vi.fn(), debug: vi.fn(), error: vi.fn() };
}

describe('api-status service', () => {
  let log: LogStub;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    log = makeLog();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function stubFetch(impl: typeof fetch): void {
    fetchMock = vi.fn(impl);
    vi.stubGlobal('fetch', fetchMock);
  }

  it('A1: 2xx response → ok:true con latency_ms y code:200', async () => {
    stubFetch(async () => new Response('OK', { status: 200 }));
    const handle = initApiStatus('http://localhost:8000/health', 30_000, 5_000, log);
    await vi.runOnlyPendingTimersAsync();
    await Promise.resolve();
    const status: ApiStatusValue = getApiStatus();
    expect(status.ok).toBe(true);
    expect(status.code).toBe(200);
    expect(typeof status.latency_ms).toBe('number');
    handle.dispose();
  });

  it('A2: 5xx response → ok:false con code:500', async () => {
    stubFetch(async () => new Response('boom', { status: 500 }));
    const handle = initApiStatus('http://localhost:8000/health', 30_000, 5_000, log);
    await vi.runOnlyPendingTimersAsync();
    await Promise.resolve();
    const status: ApiStatusValue = getApiStatus();
    expect(status.ok).toBe(false);
    expect(status.code).toBe(500);
    handle.dispose();
  });

  it('A3: timeout vía AbortController → ok:false con latency_ms:-1', async () => {
    // Simulate an AbortError thrown after timeoutMs.
    stubFetch(async (_url, init) => {
      return await new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('aborted', 'AbortError'));
        });
      });
    });
    const handle = initApiStatus('http://localhost:8000/health', 30_000, 100, log);
    // Advance beyond the 100ms timeout to trigger the abort.
    await vi.advanceTimersByTimeAsync(150);
    await Promise.resolve();
    const status: ApiStatusValue = getApiStatus();
    expect(status.ok).toBe(false);
    expect(status.code).toBeUndefined();
    expect(status.latency_ms).toBe(-1);
    handle.dispose();
  });

  it('A4: cache inicial antes del primer ping retorna ok:false con latency_ms:-1', async () => {
    stubFetch(async () => new Response('OK', { status: 200 }));
    const initial: ApiStatusValue = getApiStatus();
    expect(initial.ok).toBe(false);
    expect(initial.latency_ms).toBe(-1);
    expect(initial.code).toBeUndefined();
  });
});