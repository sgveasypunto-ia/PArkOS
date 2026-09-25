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
import { useCallback } from 'react';
import useSWR from 'swr';

import { REFRESH_INTERVAL_MS } from '@parkos/ui-kit/hooks';
import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  cerrarSesion as sesionActivaCerrarSesion,
  getSesionActiva,
  SesionAlreadyClosedError,
  type SesionCerrarRequest,
  type SesionRead,
} from '../api/sesionActivaApi';

export const SESION_KEY = '/caja-sesion/sesion/me';
const DEDUPING_INTERVAL_MS = 10 * 1000;

export interface UseSesionActivaReturn {
  sesion: SesionRead | null;
  isLoading: boolean;
  error: Error | undefined;
  // The SWR key/fetcher is `SesionRead | null` (a 404 GET resolves to
  // `null` — "no active session" is a valid state, REQ-OPS-120 S3), so
  // `mutate()`'s real resolved type includes `null`, not just
  // `undefined` (revalidation-skipped/error). Omitting `| null` here
  // does not match the actual `KeyedMutator<SesionRead | null>` this
  // hook returns as `refresh` below.
  refresh: () => Promise<SesionRead | null | undefined>;
  /**
   * HU-F10.2 (REQ-OPS-160, AD-4) — encapsulates the F3.3 logout-on-success
   * trifecta (`useAuthStore.clear()` + `parkos:auth:cleared` event) so
   * callers (`<CerrarTurno>` now, F11.x worker UI later) don't re-derive
   * the contract. On 200: clears authStore + fires the event. On 401
   * (F3.3 fallback): also clears + fires. On any other non-2xx or
   * network error: returns `{ ok: false, status, error }` without
   * touching authStore.
   */
  cerrarSesion: (
    uuid: string,
    payload: SesionCerrarRequest,
  ) => Promise<CerrarSesionResult>;
}

/**
 * Discriminated union returned by `useSesionActiva().cerrarSesion(...)`.
 * Mirrors the F3.3 contract with the typed-error envelope; the helper
 * `cerrarSesion` does the F3.3 logout-on-success trifecta so callers
 * only have to `navigate` on `ok: true`.
 */
export type CerrarSesionResult =
  | { ok: true; status: 200; sesion: SesionRead }
  | { ok: false; status: number; error: SesionAlreadyClosedError | ParkosHttpError | unknown };

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
      // 404 = "no hay sesión activa" (operador sin turno, REQ-OPS-120 S3) —
      // estado válido, NO error. 422 = backend bug temporal (path matchea
      // /{uuid} antes que /me) — tratar como "no hay sesión" para no romper UX.
      shouldRetryOnError: (err) => {
        return !(err instanceof ParkosHttpError && (err.status === 404 || err.status === 422));
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
    error instanceof ParkosHttpError && (error.status === 404 || error.status === 422)
      ? undefined
      : error;

  // HU-F10.2 (REQ-OPS-160, AD-4) — the F3.3 logout-on-success
  // trifecta (`clear()` + `parkos:auth:cleared` event) is encapsulated
  // inside the helper so callers (orchestrators) do not re-derive the
  // contract. F3.30 e2e scenarios E3 + A1 in `e2e/caja/turno.spec.ts`
  // assert the contract verbatim; F10.2 keeps it bit-identical.
  const cerrarSesionHelper = useCallback(
    async (
      uuid: string,
      payload: SesionCerrarRequest,
    ): Promise<CerrarSesionResult> => {
      const doLogout = (): void => {
        useAuthStore.getState().clear();
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('parkos:auth:cleared'));
        }
      };
      try {
        const sesion = await sesionActivaCerrarSesion(uuid, payload);
        doLogout();
        return { ok: true, status: 200, sesion };
      } catch (err) {
        // F3.3 DEC-F3.3-03 fallback: 401 mid-flow (refresh failed)
        // behaves like success for consistency with the historical
        // logout-on-success flow.
        if (err instanceof ParkosHttpError && err.status === 401) {
          doLogout();
          return { ok: false, status: 401, error: err };
        }
        // 5xx / 4xx / network / SesionAlreadyClosedError: the helper
        // does NOT clear — the caller decides. The status of a network
        // failure is 0 (the helper reports `0` so the caller can branch
        // on `result.status === 0` if needed).
        const status =
          err instanceof ParkosHttpError
            ? err.status
            : err instanceof SesionAlreadyClosedError
              ? err.status
              : 0;
        return { ok: false, status, error: err };
      }
    },
    [],
  );

  return {
    sesion: data ?? null,
    isLoading,
    error: normalizedError,
    refresh: mutate,
    cerrarSesion: cerrarSesionHelper,
  };
}