/**
 * parkosFetch — global fetch wrapper for the web_admin PWA.
 *
 * Injects two cross-cutting headers on every request:
 *
 *   1. `Authorization: Bearer <token>` — the `admin-` JWT, read from
 *      `localStorage` (`parkos.auth.token`). The login flow (PR11d) is
 *      responsible for writing the token here; this wrapper just reads.
 *   2. `X-Sucursal-Context: <uuid>` — the currently selected branch,
 *      read from `localStorage` via `getSucursalHeader()` (T-PR10-12).
 *      The admin views (`/admin/sucursales/{uuid}/dashboard`, etc.)
 *      enforce this header against `sucursales_permitidas` (REQ-X2).
 *
 * `setAuthToken()` is exported so the login flow (or future token
 * refresh hook) can persist the JWT without leaking implementation
 * details to callers.
 */
import { getSucursalHeader } from './sucursal-context';

const TOKEN_KEY = 'parkos.auth.token';

function readToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function parkosFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);

  const token = readToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const sucursalHeader = getSucursalHeader();
  for (const [k, v] of Object.entries(sucursalHeader)) {
    headers.set(k, v);
  }

  return fetch(input, { ...init, headers });
}

export function setAuthToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // localStorage unavailable — fail silently; the in-memory auth
    // state (added by future hooks) still works for this session.
  }
}

export function getAuthToken(): string | null {
  return readToken();
}
