/**
 * `loginApi.ts` — HTTP layer para autenticación (F3.1 — DEC-F3.1-03/04/05/08).
 *
 * DEC-F3.1-03: `credentials:'include'` mandatory para cookie httpOnly round-trip
 *              (HttpOnly flag blinda XSS, SameSite=Lax blinda CSRF).
 * DEC-F3.1-04: Login vía HTTP directo en renderer (NO IPC bridge). El navegador
 *              gestiona la cookie jar — IPC sería over-engineering.
 * DEC-F3.1-05: `fetch` raw (NO parkosFetch) — no Authorization Bearer pre-login,
 *              leer Retry-After header en 429, error mapping custom.
 * DEC-F3.1-08: anti-enumeración — 401 colapsa a `InvalidCredentialsError` único
 *              (backend auth.py:159-191, 248-251 matchea).
 *
 * Endpoints consumidos (HU-F1.2 shipped Fase 1, READ-ONLY):
 *   - POST /api/v1/auth/login  → 200 TokenPair + Set-Cookie parkos_session
 *                                 401 invalid_credentials → InvalidCredentialsError
 *                                 429 account_locked + Retry-After → AccountLockedError
 */
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const LOGIN_PATH = '/api/v1/auth/login';

/**
 * Response de POST /api/v1/auth/login (HU-F1.2 shipped, schemas/auth.py).
 * Coincide 1:1 con backend `TokenPair` Pydantic schema.
 */
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'Bearer';
  expires_in: number;
}

/**
 * 401 — Credenciales inválidas (DEC-F3.1-08 anti-enumeración).
 * Backend colapsa email-no-existe + password-incorrecta + cuenta-deshabilitada
 * a este único error. Frontend muestra `t('invalidCredentials')`.
 */
export class InvalidCredentialsError extends Error {
  readonly name = 'InvalidCredentialsError';
}

/**
 * 429 — Cuenta bloqueada por N intentos fallidos (DEC-F3.1-08).
 * Header `Retry-After: <segundos>`. F3.2 hook consumirá
 * `retryAfterSeconds` para countdown UI; F3.1 solo surfacea el error.
 */
export class AccountLockedError extends Error {
  readonly name = 'AccountLockedError';
  constructor(public readonly retryAfterSeconds: number) {
    super(`Account locked. Retry after ${retryAfterSeconds} seconds.`);
  }
}

/**
 * Parsea el header `Retry-After` (RFC 7231 §7.1.3) a un entero en segundos.
 * Retorna 0 si el header falta o no es parseable (forward-compatible: el
 * operador no se queda bloqueado para siempre si el backend omite el header).
 */
function parseRetryAfter(headerValue: string | null): number {
  if (headerValue === null) return 0;
  const parsed = Number(headerValue);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * POST /api/v1/auth/login con `credentials:'include'`.
 *
 * Errores mapeados:
 *   - 401 → `InvalidCredentialsError` (DEC-F3.1-08)
 *   - 429 → `AccountLockedError(retryAfterSeconds)` (DEC-F3.1-08)
 *   - 5xx / 4xx no listados / network → `ParkosHttpError` o `Error`
 */
export async function postLogin(email: string, password: string): Promise<TokenPair> {
  const res = await fetch(LOGIN_PATH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include', // CRITICAL: cookie httpOnly round-trip (DEC-F3.1-03)
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new InvalidCredentialsError();
    }
    if (res.status === 429) {
      const retryAfterSeconds = parseRetryAfter(res.headers.get('Retry-After'));
      throw new AccountLockedError(retryAfterSeconds);
    }
    throw new ParkosHttpError(res.status, await res.text().catch(() => ''), res.url);
  }

  return (await res.json()) as TokenPair;
}