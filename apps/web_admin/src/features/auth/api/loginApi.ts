/**
 * `loginApi.ts` — HTTP layer for `web_admin` admin authentication
 * (IT-1.10).
 *
 * Mirrors the pattern from `apps/electron-sucursal/src/features/auth/api/loginApi.ts`
 * but is OWNED by `web_admin` (shared-on-ui-kit deferred — see
 * `loginSchema.ts` rationale).
 *
 * Differences vs the electron-sucursal version:
 *   - Uses **fetch raw** (not `parkosFetch`) because:
 *     (a) `parkosFetch` would attach `Authorization: Bearer <jwt>` from
 *         the authStore, which we do NOT want pre-login (no JWT yet),
 *     (b) `parkosFetch` would attach an `Idempotency-Key` header on
 *         POST, which we explicitly skip on `/auth/login` (the BE
 *         would not accept the same key for re-attempts after a
 *         credentials failure — `auth.py` rejects duplicate body),
 *     (c) `parkosFetch`'s 401 path fires `parkos:auth:cleared` which
 *         would clobber a fresh `authStore` we are trying to populate.
 *   - Uses `credentials: 'include'` so the BE can set a future
 *     httpOnly cookie alongside the JWT pair returned in the body
 *     (F2.2 convention; the BE currently returns the pair in body only,
 *     but the surface is ready for cookie).
 *
 * Endpoints consumed (HU-F1.2 shipped Fase 1):
 *   - POST /api/v1/auth/login
 *       200 → LoginResponse (must_change_password flag discriminates the
 *             shape; see HU-F16 must-change enforcement, migration 0065)
 *       401 → InvalidCredentialsError (DEC-LOGIN-08 anti-enumeration)
 *       429 → AccountLockedError with `Retry-After` seconds
 *
 * Error mapping (DEC-LOGIN-08):
 *   The BE collapses "email does not exist", "wrong password", and
 *   "account disabled" into ONE 401 with body
 *   `{ detail: "invalid_credentials" }`. The form renders
 *   `auth.invalidCredentials` regardless of which one actually fired.
 */
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const LOGIN_PATH = '/api/v1/auth/login';

/**
 * HU-F16 must-change enforcement: the login endpoint returns a UNION
 * shape -- either a normal pair or a temporary credential. The
 * discriminator is ``must_change_password``: when True, the frontend
 * routes to ``<CambiarPasswordForm>`` and exchanges the temporary
 * token at ``POST /auth/cambiar-password`` before treating the
 * operator as logged in.
 *
 * Both access_token / refresh_token / temporary_token are nullable to
 * model the union: a must-change response has no normal pair, a
 * normal response has no temporary token. ``must_change_password``
 * itself is REQUIRED (boolean) because the backend always sets it
 * (default ``False``). The container at :class:`pages/Login.tsx`
 * branches on it before deciding which fields to read.
 */
export interface LoginResponse {
  access_token: string | null;
  refresh_token: string | null;
  temporary_token: string | null;
  token_type: 'Bearer';
  expires_in: number | null;
  must_change_password: boolean;
}

export class InvalidCredentialsError extends Error {
  override readonly name = 'InvalidCredentialsError';
}

export class AccountLockedError extends Error {
  override readonly name = 'AccountLockedError';
  constructor(public readonly retryAfterSeconds: number) {
    super(`Account locked. Retry after ${retryAfterSeconds} seconds.`);
  }
}

/**
 * POST /api/v1/auth/login — exchange email+password for a token pair
 * (or, after an admin reset, a temporary credential that the operator
 * must exchange at ``POST /auth/cambiar-password``).
 *
 * Throws:
 *   - `InvalidCredentialsError` on 401 (DEC-LOGIN-08 single message).
 *   - `AccountLockedError` on 429 with `Retry-After: <seconds>`.
 *   - The underlying `ParkosHttpError` on any other 4xx/5xx — surfaced
 *     to the form as a generic error message; the user retries.
 *
 * The success shape is the union ``LoginResponse`` above. The caller
 * is responsible for branching on ``must_change_password``.
 */
export async function postLogin(email: string, password: string): Promise<LoginResponse> {
  let response: Response;
  try {
    response = await fetch(LOGIN_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, password }),
    });
  } catch (networkError) {
    // NetworkError / AbortError — surface as ParkosHttpError with
    // status 0 so the form treats it like a generic retryable error.
    throw new ParkosHttpError(
      0,
      networkError instanceof Error ? networkError.message : 'network_error',
      LOGIN_PATH,
    );
  }

  if (response.status === 401) {
    throw new InvalidCredentialsError();
  }

  if (response.status === 429) {
    const retryAfter = Number.parseInt(response.headers.get('Retry-After') ?? '60', 10);
    throw new AccountLockedError(Number.isFinite(retryAfter) ? retryAfter : 60);
  }

  if (!response.ok) {
    let bodyText = '';
    try {
      bodyText = await response.text();
    } catch {
      /* ignore */
    }
    throw new ParkosHttpError(response.status, bodyText, LOGIN_PATH);
  }

  return (await response.json()) as LoginResponse;
}
