/**
 * API health-polling service (F2.3 — T2, DEC-UPD-05/06).
 *
 * Polls `${httpUrl}` every `intervalMs` (default 30 s) with a per-request
 * timeout of `timeoutMs` (default 5 s) implemented via `AbortController`.
 *
 * `getApiStatus()` returns the latest cached `ApiStatusValue`. The
 * renderer never fetches directly — it consumes
 * `window.bridge.apiStatus.get()` which calls into this module through
 * the IPC handler registered in `main.ts`.
 */

/** Minimal logger interface — accepts electron-log's default export. */
export interface LogLike {
  info: (...args: unknown[]) => void;
  warn: (...args: unknown[]) => void;
  debug: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
}

/** Health status snapshot returned by `getApiStatus()`. */
export interface ApiStatusValue {
  /** `true` only if the backend responded with 2xx. */
  ok: boolean;
  /** Round-trip latency in ms; `-1` for the initial cache or a timeout. */
  latency_ms: number;
  /** HTTP status code if reachable (2xx/4xx/5xx); undefined for network errors / timeouts. */
  code?: number;
}

export interface ApiStatusHandle {
  dispose(): void;
}

/** Default polling cadence — DEC-UPD-05. */
export const DEFAULT_INTERVAL_MS = 30_000;

/** Default per-request timeout — DEC-UPD-06. */
export const DEFAULT_TIMEOUT_MS = 5_000;

/** Latency threshold above which the status is considered "slow" (yellow). */
export const SLOW_THRESHOLD_MS = 1_000;

/**
 * Initial cache value returned before the first ping completes.
 * Signaled as `{ok:false, code:undefined, latency_ms:-1}` so the renderer
 * renders 🔴 until the first successful poll.
 */
const INITIAL_RESULT: ApiStatusValue = { ok: false, latency_ms: -1, code: undefined };

let lastResult: ApiStatusValue = { ...INITIAL_RESULT };

async function ping(httpUrl: string, timeoutMs: number, log: LogLike): Promise<ApiStatusValue> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = Date.now();

  try {
    const res = await fetch(httpUrl, { signal: controller.signal });
    const latency_ms = Date.now() - startedAt;
    if (res.ok) {
      if (latency_ms > SLOW_THRESHOLD_MS) {
        log.warn('api-status.slow', { latency_ms, code: res.status });
      }
      return { ok: true, latency_ms, code: res.status };
    }
    return { ok: false, latency_ms, code: res.status };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const elapsed = Date.now() - startedAt;
    log.warn('api-status.error', { err: message });
    return {
      ok: false,
      latency_ms: elapsed >= timeoutMs ? -1 : elapsed,
      code: undefined,
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

export function initApiStatus(
  httpUrl: string,
  intervalMs: number = DEFAULT_INTERVAL_MS,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
  log: LogLike,
): ApiStatusHandle {
  const tick = async (): Promise<void> => {
    const result = await ping(httpUrl, timeoutMs, log);
    lastResult = result;
  };

  void tick();
  const intervalId = setInterval(() => {
    void tick();
  }, intervalMs);

  log.info('api-status.init', { httpUrl, intervalMs, timeoutMs });

  return {
    dispose(): void {
      clearInterval(intervalId);
    },
  };
}

export function getApiStatus(): ApiStatusValue {
  return lastResult;
}