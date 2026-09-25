/**
 * `useOcupacion()` — SWR hook for the live occupancy strip (HU-F4.3).
 *
 * Polls `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` every 10s via SWR
 * (DEC-SUC-11 verbatim) with a 5s deduping window so multiple mounts of
 * `<OcupacionStrip />` (F4.4 dashboard, F6.x ingreso, F7.x salida) share
 * the same SWR key and do not issue duplicate fetches.
 *
 * SWR key gating — `null` when:
 *   - `uuid_sucursal` is `null` (consumer did not resolve branch yet), OR
 *   - `accessToken` is missing (operator not authenticated, pre-login).
 *
 * Precedent verbatim F4.1 `useTiposVehiculo` and F3.3 `useSesionActiva`:
 * the key gate avoids 401 noise on cold boot. When the key is `null`,
 * SWR does not fire any request — the consumer sees `data: undefined`,
 * `error: undefined`, `isStale: false`.
 *
 * `onError` policy (DEC-SUC-11 + F2.2 invariants):
 *   - 401 → delegated to `useAuthStore.clear()` + `parkos:auth:cleared`
 *     event (the same defensive logout used by every other hook in this
 *     codebase; precedent F3.3, F4.1).
 *   - 403/404/5xx/network → `console.warn` only. The renderer keeps the
 *     last `data` (SWR keeps `data` populated across errors) and the
 *     componente marks `data-stale="true"` so the operator keeps
 *     situational awareness. We do NOT clear auth on 5xx because that
 *     would log the operator out during a backend hiccup.
 *
 * `shouldRetryOnError` excludes 401 (let auth store react), 403 (forbidden
 * is terminal), and 404 (sucursal UUID typo is not transient). All other
 * errors are retried by SWR's default schedule.
 *
 * No `AbortController` plumbing here — SWR's default fetcher already
 * honors React effect cleanup. The componente wires an explicit
 * `AbortController` only for the `uuid_sucursal` prop-change case
 * (branch switch in admin mode).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  OPERACION_DEDUPING_INTERVAL_MS,
  OPERACION_REFRESH_INTERVAL_MS,
} from '../constants';
import { getOcupacion, type OcupacionResponse } from '../api/ocupacionApi';

/**
 * Returns the SWR key for the current `(uuid_sucursal, accessToken)` pair.
 * `null` disables the fetch — SWR treats a null key as "skip".
 */
function buildKey(
  uuid_sucursal: string | null,
  accessToken: string | null,
): string | null {
  if (!uuid_sucursal) return null;
  if (!accessToken) return null;
  return `/operacion/ocupacion?uuid_sucursal=${uuid_sucursal}`;
}

export interface UseOcupacionReturn {
  data: OcupacionResponse | undefined;
  error: Error | undefined;
  /**
   * `true` when there is a previously successful `data` AND the most
   * recent poll failed. SWR keeps `data` populated across errors; the
   * componente uses this flag to render `data-stale="true"` + AlertCircle.
   */
  isStale: boolean;
  refresh: () => Promise<OcupacionResponse | undefined>;
}

export function useOcupacion(uuid_sucursal: string | null): UseOcupacionReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = buildKey(uuid_sucursal, accessToken);

  // REQ-OPS-132 (qa-2026-09-17 bug 2): the SWR fetcher receives the
  // raw UUID, NOT the cache key. Previously we passed ``getOcupacion``
  // directly as the second argument, so SWR invoked it with the full
  // ``/operacion/ocupacion?uuid_sucursal=...`` key string — that
  // produced a 422 ``placa_formato_invalido`` / 500 on the backend
  // because the helper expected a bare UUID.
  //
  // The closure captures ONLY the UUID (no query-string encoding).
  // This mirrors the established precedent in
  // ``useSesionActiva.ts:55-57`` and ``useIngresoActivo.ts:67-69``:
  // SWR convention is that the key is opaque (used only for cache
  // identity) and the fetcher gets the actual payload argument.
  const { data, error, mutate } = useSWR<OcupacionResponse>(
    key,
    // `key` is `null` whenever `uuid_sucursal` is `null` (see `buildKey`
    // above), so SWR never invokes this fetcher with a null UUID. The
    // assertion mirrors the established precedent in
    // `useMiTurno.ts:73` for the same key-gating shape.
    () => getOcupacion(uuid_sucursal as string),
    {
      refreshInterval: OPERACION_REFRESH_INTERVAL_MS,
      dedupingInterval: OPERACION_DEDUPING_INTERVAL_MS,
      // 401 → let auth store react; 403/404 → terminal, no retry spam.
      shouldRetryOnError: (err) => {
        if (err instanceof ParkosHttpError) {
          return err.status !== 401 && err.status !== 403 && err.status !== 404;
        }
        // Unknown error shape (e.g. network) → retry per SWR defaults.
        return true;
      },
      onError: (err) => {
        // 401 is the only signal that the token is dead — defensive logout
        // mirrors F3.3 / F4.1 behavior. All other errors are operational and
        // MUST NOT log the operator out.
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('parkos:auth:cleared'));
          }
          return;
        }
        // Operational telemetry only — `console.error` would surface as a hard
        // error in production logs even though the failure is recoverable.
        console.warn('[useOcupacion] polling failed', err);
      },
    },
  );

  const isStale = data !== undefined && error !== undefined;

  return {
    data,
    error,
    isStale,
    refresh: async () => mutate(),
  };
}