/**
 * sucursalContext — keeps the `X-Sucursal-Context` header source
 * (`localStorage['parkos.lastSelectedSucursal']`, read by `parkosFetch`)
 * in sync with the session issued at login.
 *
 * Why: a supervisor logs into the branch app with an `admin-` token. The
 * branch API requires `X-Sucursal-Context` for every `admin-` call (writes
 * without it answer 400 `missing_sucursal_context`). Operator (`operador-`)
 * tokens are pinned to one branch by the backend and never need the header.
 *
 * The JWT payload is only DECODED here (no verification, no trust): the
 * backend re-validates the header against the token and the DB on every
 * call. Nothing new is persisted beyond the existing storage key.
 */
export const SUCURSAL_STORAGE_KEY = 'parkos.lastSelectedSucursal';

interface JwtClaims {
  iss?: unknown;
  sucursal?: unknown;
}

/** Decodes the (unverified) payload of a JWT; `null` when malformed. */
export function decodeJwtClaims(token: string): JwtClaims | null {
  const parts = token.split('.');
  if (parts.length < 2 || !parts[1]) return null;
  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const json = decodeURIComponent(
      Array.from(atob(padded))
        .map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`)
        .join(''),
    );
    const parsed = JSON.parse(json) as unknown;
    return typeof parsed === 'object' && parsed !== null ? (parsed as JwtClaims) : null;
  } catch {
    return null;
  }
}

/**
 * Applies the branch context implied by a freshly issued access token.
 *   - `admin-` token with a `sucursal` claim -> stores it so `parkosFetch`
 *     sends `X-Sucursal-Context` on every call.
 *   - any other token -> removes a stale value left by a previous
 *     supervisor session.
 *
 * Returns the stored branch uuid (or `null`).
 */
export function syncSucursalContextFromAccessToken(accessToken: string): string | null {
  if (typeof window === 'undefined') return null;
  const claims = decodeJwtClaims(accessToken);
  const iss = typeof claims?.iss === 'string' ? claims.iss : '';
  const sucursal = typeof claims?.sucursal === 'string' ? claims.sucursal : '';
  try {
    if (iss.startsWith('admin-') && sucursal) {
      window.localStorage.setItem(SUCURSAL_STORAGE_KEY, sucursal);
      return sucursal;
    }
    window.localStorage.removeItem(SUCURSAL_STORAGE_KEY);
  } catch {
    /* storage unavailable: header simply is not sent */
  }
  return null;
}
