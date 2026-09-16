/**
 * `useSesionActiva()` — SWR hook para consultar sesión de caja activa.
 *
 * F3.3 — T1. Segundo hook genuinely reusable del feature `caja` (primer
 * consumer F3.3; forward F4.x/F5.x/F6.x/F7.x/F8.x/F9.x/F10.x/F11.x/F12.x
 * para scoped queries per `sesion.uuid_sucursal` + `sesion.uuid_usuario`).
 *
 * DEC-F3.3-04 verbatim — alinea con precedent F3.1 `useAuth` (F2.2 baseline):
 *   - SWR key `accessToken ? '/caja-sesion/sesion/me' : null` (key null sin
 *     token, idéntico pattern F3.1 useAuth:67). Sin fetch cuando operador
 *     no autenticado — gate crítico contra 401 noise en cold-boot pre-login.
 *   - `refreshInterval: REFRESH_INTERVAL_MS` (50min, DEC-SUC-03 verbatim
 *     plan.md:418 heredado de F3.2). 10min safety margin vs ACCESS_TOKEN_TTL=3600s.
 *   - `dedupingInterval: 10 * 1000` — Dashboard + CerrarTurno consumen
 *     en paralelo; deduplica requests concurrentes.
 *   - `shouldRetryOnError: err.status !== 404` — operador sin turno NO
 *     es error; no retry spam.
 *   - `onError` con `status === 401` dispara `useAuthStore.clear()` +
 *     `parkos:auth:cleared` window event (forward hook AuthGuard F3.x+).
 *
 * F3.3 contribution al gating transversal:
 *   - Sin F3.3, F4.x+ (catálogos + ocupación) no pueden arrancar
 *     (pending.md §5 forward hooks explícitos).
 *   - Defense in depth XR6 layer 4 contract: este hook + Zod local + backend
 *     Pydantic + partial unique index 0023 (F1.3).
 */
import useSWR from 'swr';

import { REFRESH_INTERVAL_MS } from '@parkos/ui-kit/hooks';
import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { getSesionActiva, type SesionRead } from '../api/sesionActivaApi';

const SESION_KEY = '/caja-sesion/sesion/me';
const DEDUPING_INTERVAL_MS = 10 * 1000;

export interface UseSesionActivaReturn {
  sesion: SesionRead | null;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<SesionRead | undefined>;
}

/**
 * Hook SWR para consultar sesión de caja activa del operador autenticado.
 *
 * Retorna `{ sesion, isLoading, error, refresh }`. `error` se omite cuando
 * status===404 (operador sin sesión activa, estado válido REQ-OPS-120 S3) —
 * consumers no necesitan filtrar.
 */
export function useSesionActiva(): UseSesionActivaReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<SesionRead | null>(
    accessToken ? SESION_KEY : null,
    () => getSesionActiva(),
    {
      refreshInterval: REFRESH_INTERVAL_MS,
      dedupingInterval: DEDUPING_INTERVAL_MS,
      shouldRetryOnError: (err) => {
        return !(err instanceof ParkosHttpError && err.status === 404);
      },
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('parkos:auth:cleared'));
          }
        }
      },
    },
  );

  const normalizedError =
    error instanceof ParkosHttpError && error.status === 404 ? undefined : error;

  return {
    sesion: data ?? null,
    isLoading,
    error: normalizedError,
    refresh: mutate,
  };
}