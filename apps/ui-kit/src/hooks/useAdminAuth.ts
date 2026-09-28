/**
 * useAdminAuth — admin-issuer counterpart to `useAuth`.
 *
 * WHY THIS EXISTS (not a duplicate of `useAuth`):
 *   `useAuth` fetches `/auth/me`, and that endpoint is hardcoded to the
 *   `operador-` issuer:
 *
 *       iss = claims.get("iss", "")
 *       if not iss.startswith("operador-"):
 *           raise HTTPException(status_code=404, detail={"error": "not_found"})
 *
 *   (`api/v1/auth.py::me`, anti-enumeration collapse). `web_admin`
 *   authenticates with `admin-` issuer tokens, so EVERY admin profile
 *   fetch returns 404. `useAuth` therefore resolves, without erroring
 *   visibly, to `user: null` / `permisos: []` / `sucursalesPermitidas:
 *   []` for the whole admin surface — `isAuthenticated` still works
 *   because it is derived from the token in the store, not from the
 *   profile. That silent-empty profile is what makes permission-gated
 *   navigation render nothing.
 *
 *   Rather than teaching `useAuth` to route by issuer (changing the
 *   contract of a hook the operator app depends on), this is a sibling
 *   hook that fetches the endpoint the admin surface actually has:
 *   `GET /api/v1/admin/me` (`api/v1/admin_views.py`, issuer-gated with
 *   `requires_issuer("admin-")`, NO `X-Sucursal-Context` requirement).
 *
 *   It normalizes the response into a shape that mirrors `useAuth` so
 *   shell/nav code can be written once against one interface. The
 *   branch list is exposed as `sucursalUuids: string[]` because
 *   `/admin/me` returns bare UUIDs — fabricating `SucursalItem` objects
 *   with `nombre: null` would be a lie the UI could render.
 *
 * LOGOUT SEMANTICS (see `logoutAdmin`): the backend `/auth/logout`
 * closes the `login` audit row; it does NOT revoke the JWT (there is no
 * denylist for admin tokens). So local state is the only thing that
 * actually ends the session, and the server call is best-effort.
 */
import useSWR from 'swr';

import { parkosFetch, parkosFetchRaw, ParkosHttpError } from '../fetch/parkosFetch';
import { useAuthStore } from '../store/authStore';
import { REFRESH_INTERVAL_MS, type AuthUser } from './useAuth';

export const ADMIN_ME_PATH = '/api/v1/admin/me';
export const ADMIN_LOGOUT_PATH = '/api/v1/auth/logout';

/** Response shape of `GET /api/v1/admin/me`. */
export interface AdminMeResponse {
  actor_uuid: string;
  email: string | null;
  rol: string | null;
  sucursales_permitidas: string[];
  permissions: string[];
}

export interface UseAdminAuthReturn {
  user: AuthUser | null;
  rol: string | null;
  sucursalUuids: string[];
  permisos: string[];
  isAuthenticated: boolean;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<AdminMeResponse | undefined>;
  logout: () => Promise<void>;
}

/**
 * POST /api/v1/auth/logout, then ALWAYS drop local credentials.
 *
 * Best-effort by construction, on purpose:
 *   - A 204 has no body, so `parkosFetch` (which always `res.json()`)
 *     would throw on it; `parkosFetchRaw` is the correct level.
 *   - `get_tenant_ctx` requires `X-Sucursal-Context` for `admin-`
 *     tokens, so this returns 400 when no branch is selected. That is a
 *     missing audit close, NOT a failed logout.
 *   - Offline / 5xx must never trap the operator in a session they asked
 *     to end, so the local clear happens in `finally` unconditionally.
 */
export async function logoutAdmin(): Promise<void> {
  try {
    await parkosFetchRaw(ADMIN_LOGOUT_PATH, { method: 'POST' });
  } catch {
    // Network error after parkosFetchRaw's internal retries. The session
    // still ends locally below; the server-side audit close is lost,
    // which is strictly better than an operator who cannot log out.
  } finally {
    useAuthStore.getState().clear();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('parkos:auth:cleared'));
    }
  }
}

export function useAdminAuth(): UseAdminAuthReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<AdminMeResponse>(
    accessToken ? ADMIN_ME_PATH : null,
    parkosFetch,
    {
      refreshInterval: REFRESH_INTERVAL_MS,
      revalidateOnFocus: false,
      shouldRetryOnError: (err) =>
        !(err instanceof ParkosHttpError && err.status === 401),
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('parkos:auth:cleared'));
          }
        }
      },
    },
  );

  return {
    user: data
      ? { uuid: data.actor_uuid, email: data.email ?? '', nombre: null, apellido: null }
      : null,
    rol: data?.rol ?? null,
    sucursalUuids: data?.sucursales_permitidas ?? [],
    permisos: data?.permissions ?? [],
    isAuthenticated: !!accessToken,
    isLoading,
    error,
    refresh: mutate,
    logout: logoutAdmin,
  };
}
