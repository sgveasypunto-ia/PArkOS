/**
 * useAuth — SWR-backed hook that fuses the token-bearing authStore
 * (Zustand) with the `/auth/me` profile fetch.
 *
 * Design (DEC-FETCH-07):
 *   - Zustand owns the small, sync, frequently-updated tokens.
 *   - SWR owns the large, async, infrequently-fetched profile data.
 *   - `refreshInterval: REFRESH_INTERVAL_MS` (50 min, F3.2) revalidates per
 *     `DEC-SUC-03` verbatim (plan.md:418) — 10min safety margin vs
 *     `ACCESS_TOKEN_TTL=3600` in backend auth.py:71.
 *   - When there is no accessToken the SWR key is `null`, so SWR skips
 *     the fetch entirely (no redundant network on first render).
 *   - 401 from `/auth/me` triggers `useAuthStore.clear()` AND fires the
 *     `parkos:auth:cleared` window event so the SPA router can redirect
 *     to /login (F3.1 listener).
 *   - `shouldRetryOnError` excludes ParkosHttpError 401 (refresh failed
 *     → already handled by `onError`).
 */
import useSWR from 'swr';

import { parkosFetch, ParkosHttpError } from '../fetch/parkosFetch';
import { useAuthStore } from '../store/authStore';

/**
 * SWR refresh interval en ms (50min). DEC-SUC-03 verbatim (plan.md:418).
 * Exportado para testabilidad determinista (no magic numbers).
 *
 * Safety margin: ACCESS_TOKEN_TTL=3600s (auth.py:71) - REFRESH_INTERVAL_MS=3000s
 * = 600s = 10min entre refresh y TTL real. Cubre network latency + clock skew.
 */
export const REFRESH_INTERVAL_MS = 50 * 60 * 1000;

export interface AuthUser {
  /**
   * REQ-OPS-131 (qa-2026-09-17 bug 1): backend canonical identity is
   * ``UserItem.uuid`` (``schemas/auth.py``) — the F3.1 contract was a
   * pre-bug ``id`` field that produced Zod silent rejects in
   * ``AbrirTurno`` because the AbrirTurno schema's
   * ``uuid_usuario: uuid_lib.UUID`` validation failed on an empty
   * UUID derived from ``user.id ?? ''``. Renaming to ``uuid``
   * aligns the ui-kit surface with the backend canonical field and
   * stops the silent 422.
   *
   * Breaking change (workspace-internal): all in-tree consumers must
   * read ``user?.uuid`` instead of ``user?.id``. ``apps/ui-kit``
   * package version bumped to ``0.3.0``.
   */
  uuid: string;
  email: string;
  /**
   * 2026-09-25 (rediseño visual, pedido operador): el backend
   * (`UserItem`, `schemas/auth.py`) ya envía `nombre`/`apellido` en
   * `GET /auth/me` — "Mirrors the columns the operator UI needs to
   * render the avatar/name panel", literal del docstring — pero esta
   * interfaz nunca los declaraba, así que el header de `electron-sucursal`
   * derivaba un nombre falso del prefijo del email en vez de usar el
   * dato real. Opcionales (no solo nullable): el backend los permite
   * `None`, y así los mocks/fixtures existentes en tests de todo el
   * monorepo que construyen un `AuthUser` sin estos 2 campos siguen
   * compilando sin tocarlos uno por uno.
   */
  nombre?: string | null;
  apellido?: string | null;
}

export interface SucursalItem {
  uuid: string;
  nombre: string | null;
  /**
   * 2026-09-25: idem `nombre`/`apellido` de arriba — el backend
   * (`schemas/auth.py:293`) ya envía `prefijo_nombre` (código corto de
   * sucursal, ej. "BOG-CEN") pero esta interfaz no lo declaraba. Opcional
   * por la misma razón que `nombre`/`apellido` de `AuthUser`.
   */
  prefijo_nombre?: string | null;
}

export interface AuthMeResponse {
  user: AuthUser;
  sucursal: SucursalItem | null;
  sucursales_permitidas: SucursalItem[];
  permisos: string[];
  expires_at: string | null;
}

export interface UseAuthReturn {
  user: AuthUser | null;
  sucursal: SucursalItem | null;
  sucursalesPermitidas: SucursalItem[];
  permisos: string[];
  expiresAt: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<AuthMeResponse | undefined>;
}

export function useAuth(): UseAuthReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<AuthMeResponse>(
    accessToken ? '/auth/me' : null,
    parkosFetch,
    {
      refreshInterval: REFRESH_INTERVAL_MS,
      revalidateOnFocus: true,
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
    user: data?.user ?? null,
    sucursal: data?.sucursal ?? null,
    sucursalesPermitidas: data?.sucursales_permitidas ?? [],
    permisos: data?.permisos ?? [],
    expiresAt: data?.expires_at ?? null,
    isAuthenticated: !!accessToken,
    isLoading,
    error,
    refresh: mutate,
  };
}
