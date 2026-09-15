/**
 * useAuth — SWR-backed hook that fuses the token-bearing authStore
 * (Zustand) with the `/auth/me` profile fetch.
 *
 * Design (DEC-FETCH-07):
 *   - Zustand owns the small, sync, frequently-updated tokens.
 *   - SWR owns the large, async, infrequently-fetched profile data.
 *   - `refreshInterval: 5 * 60 * 1000` revalidates every 5 minutes per
 *     `plan.md:1208` — balance between freshness and bandwidth.
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

export interface AuthUser {
  id: string;
  email: string;
}

export interface SucursalItem {
  uuid: string;
  nombre: string | null;
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
      refreshInterval: 5 * 60 * 1000,
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
