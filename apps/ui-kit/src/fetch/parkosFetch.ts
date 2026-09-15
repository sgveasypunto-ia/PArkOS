/**
 * parkosFetch — cross-app HTTP wrapper for web_admin + electron-sucursal.
 *
 * Cross-cutting headers (decoration order = auth → context → idempotency):
 *   1. `Authorization: Bearer <jwt>` from `useAuthStore().accessToken`.
 *   2. `X-Sucursal-Context: <uuid>` from `localStorage['parkos.lastSelectedSucursal']`.
 *   3. `Idempotency-Key: <sha256>` on POST/PUT/PATCH/DELETE (skip on /auth/login).
 *   4. `Content-Type: application/json` default when `init.body` is present.
 *
 * Retry policy (DEC-FETCH-02):
 *   - 5xx, 408, and NetworkError → up to 3 attempts total, backoff 300/600/1200 ms.
 *   - 4xx (except 408) → no retry.
 *   - 401 → refresh-once via Mutex singleton (DEC-FETCH-03); on refresh failure
 *     clear authStore + emit `parkos:auth:cleared` window event.
 *
 * Timeout (DEC-FETCH-04): `AbortController` fires after `init.timeoutMs`
 * (default 30_000) and rejects with an AbortError.
 *
 * Boundary (DEC-FETCH-05): the typed wrapper `parkosFetch<T>` validates
 * the JSON response against an optional Zod schema; on schema mismatch
 * a ZodError is thrown for callers to inspect.
 */
import type { z } from 'zod';

import { useAuthStore } from '../store/authStore';

const BACKOFF_MS: readonly number[] = [300, 600, 1200];
const DEFAULT_TIMEOUT_MS = 30_000;
const SUCURSAL_STORAGE_KEY = 'parkos.lastSelectedSucursal';

export interface ParkosFetchInit extends Omit<RequestInit, 'signal'> {
  /** Timeout en ms. Default 30_000. AbortController dispara AbortError. */
  timeoutMs?: number;
  /** Override del AbortController (útil para tests con vi.useFakeTimers). */
  signal?: AbortSignal;
  /** Skip Idempotency-Key (default false; auto true para POST /auth/login). */
  skipIdempotencyKey?: boolean;
}

export class ParkosHttpError extends Error {
  public readonly status: number;
  public readonly body: string;
  public readonly url: string;

  constructor(status: number, body: string, url: string) {
    super(`parkosFetch ${status} ${url}: ${body.slice(0, 200)}`);
    this.name = 'ParkosHttpError';
    this.status = status;
    this.body = body;
    this.url = url;
  }
}

function readSucursalHeader(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(SUCURSAL_STORAGE_KEY);
  } catch {
    return null;
  }
}

async function idempotencyKey(
  method: string,
  url: string,
  body: BodyInit | null | undefined,
): Promise<string> {
  const enc = new TextEncoder();
  const data = enc.encode(
    `${method.toUpperCase()}|${url}|${JSON.stringify(body ?? null)}`,
  );
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function buildInit(
  input: RequestInfo | URL,
  init?: ParkosFetchInit,
): Promise<RequestInit> {
  const headers = new Headers(init?.headers);
  const url = typeof input === 'string' ? input : input.toString();
  const method = (init?.method ?? 'GET').toUpperCase();

  // (1) Authorization Bearer desde authStore
  const { accessToken } = useAuthStore.getState();
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  // (2) X-Sucursal-Context desde localStorage
  const sucHeader = readSucursalHeader();
  if (sucHeader) {
    headers.set('X-Sucursal-Context', sucHeader);
  }

  // (3) Idempotency-Key para mutacionales, skip para /auth/login
  const isMutational = ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method);
  const isLoginEndpoint = url.includes('/auth/login');
  if (isMutational && !init?.skipIdempotencyKey && !isLoginEndpoint) {
    headers.set('Idempotency-Key', await idempotencyKey(method, url, init?.body));
  }

  // (4) Content-Type default si body y no header
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  return { ...init, headers };
}

// ─── Mutex singleton para refresh-once (DEC-FETCH-03) ────────────────
let refreshPromise: Promise<string | null> | null = null;

interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const { refreshToken } = useAuthStore.getState();
      if (!refreshToken) return null;
      const res = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const pair = (await res.json()) as TokenPair;
      useAuthStore
        .getState()
        .setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
      return pair.access_token;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

async function handle401(
  input: RequestInfo | URL,
  init: ParkosFetchInit | undefined,
  res: Response,
  attempt: number,
): Promise<Response> {
  // Solo UN refresh-once por cadena de parkosFetchRaw
  if (attempt > 1) return res;
  const newToken = await refreshAccessToken();
  if (!newToken) {
    useAuthStore.getState().clear();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('parkos:auth:cleared'));
    }
    return res;
  }
  return parkosFetchRaw(input, init, attempt + 1);
}

/**
 * parkosFetchRaw — bajo nivel (returns Response, no parse).
 *
 * Implementa el loop de retry+refresh+timeout sin validación de schema.
 * Usado por `parkosFetch` (typed wrapper) y directamente por callers
 * que necesitan inspeccionar el status antes de parsear.
 */
export async function parkosFetchRaw(
  input: RequestInfo | URL,
  init?: ParkosFetchInit,
  attempt: number = 1,
): Promise<Response> {
  const finalInit = await buildInit(input, init);
  const controller = new AbortController();
  const timeoutMs = init?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const res = await fetch(input, { ...finalInit, signal: controller.signal });

    if (res.ok) return res;

    // 4xx no-retry (excepto 408 que sí retry)
    if (res.status >= 400 && res.status < 500 && res.status !== 408) {
      if (res.status === 401) {
        return handle401(input, init, res, attempt);
      }
      return res;
    }

    // 5xx o 408 → retry hasta 3 intentos totales
    if (attempt >= 3) return res;
    const backoff = BACKOFF_MS[attempt - 1] ?? 1200;
    await delay(backoff);
    return parkosFetchRaw(input, init, attempt + 1);
  } catch (err) {
    // Timeout abort (caller-induced) NO se reintenta — caller quiere abortar.
    // NetworkError (fetch rejected) sí se reintenta como 5xx transient.
    if (timedOut || attempt >= 3) throw err;
    const backoff = BACKOFF_MS[attempt - 1] ?? 1200;
    await delay(backoff);
    return parkosFetchRaw(input, init, attempt + 1);
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * parkosFetch — typed wrapper que valida con Zod schema opcional.
 *
 * - `res.ok === false` → throws `ParkosHttpError` con status + body + url.
 * - Schema provided → `schema.parse(json)` (throws `ZodError` on mismatch).
 * - Schema omitted → retorna JSON as-is con cast `T`.
 */
export async function parkosFetch<T>(
  input: RequestInfo | URL,
  init?: ParkosFetchInit,
  schema?: z.ZodType<T>,
): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    throw new ParkosHttpError(res.status, await res.text(), String(input));
  }
  const json = await res.json();
  return schema ? schema.parse(json) : (json as T);
}
