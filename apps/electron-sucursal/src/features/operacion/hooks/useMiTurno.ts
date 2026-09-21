/**
 * `useMiTurno()` — SWR hook for the per-turn KPI aggregate (HU-F12.1).
 *
 * Polls `GET /api/v1/operacion/mi-turno?uuid_sesion=X` every 15s via
 * SWR (REQ-OPS-188, AD-3 — operator-live turn metrics justify the 2x
 * cadence vs F11.x 30s) with a 5s deduping window so two mounts of
 * `<MiTurnoPanel />` on the same screen share the SWR key.
 *
 * SWR key gating — `null` when:
 *   - `uuid_sesion` is `null` (consumer did not resolve the active
 *     turno yet, e.g. pre-`useSesionActiva()` hydration), OR
 *   - `accessToken` is missing (operator not authenticated).
 *
 * `onError` policy (REQ-OPS-188, F2.2 invariants):
 *   - 401 -> delegated to `useAuthStore.clear()` + `parkos:auth:cleared`
 *     event (precedent F11.1, F11.2, F3.3).
 *   - 403/404/5xx -> `console.warn` only. The renderer keeps the last
 *     `data` (SWR keeps `data` populated across errors) and the panel
 *     renders its zero-state fallback.
 *
 * `shouldRetryOnError` excludes 401 (let auth store react), 403
 * (forbidden terminal — sesion_cross_branch_forbidden), and 404
 * (sesion_not_found terminal). All other errors are retried by SWR's
 * default schedule.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { getMiTurno } from '../api/miTurnoApi';
import { emptyMiTurno, type MiTurnoRead } from '../types';

/**
 * 15_000 ms (REQ-OPS-188, AD-3). Per-turn metrics are operator-live:
 * the renderer wants near-real-time visibility while a single sesion
 * is open. SUM cardinality is bounded to 1 active sesion per operator
 * by the `prod.sesion` partial unique index (R-F12.1-4 mitigation).
 */
export const MI_TURNO_REFRESH_INTERVAL_MS = 15_000;

/** 5_000 ms deduping window — mirrors F4.3 / F11.x pattern. */
export const MI_TURNO_DEDUPING_INTERVAL_MS = 5_000;

function buildKey(
  uuid_sesion: string | null,
  accessToken: string | null,
): string | null {
  if (!uuid_sesion) return null;
  if (!accessToken) return null;
  return `/operacion/mi-turno?uuid_sesion=${uuid_sesion}`;
}

export interface UseMiTurnoReturn {
  /**
   * Always non-null — the hook returns the all-zero fallback whenever
   * SWR has not populated yet (REQ-OPS-188, DA-F12.1-4). The panel can
   * read fields unconditionally without skeleton-on-zero.
   */
  data: MiTurnoRead;
  error: Error | undefined;
  /** True when data is populated AND the most recent poll errored. */
  isStale: boolean;
  refresh: () => Promise<MiTurnoRead | undefined>;
}

export function useMiTurno(uuid_sesion: string | null): UseMiTurnoReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = buildKey(uuid_sesion, accessToken);

  const { data, error, mutate } = useSWR<MiTurnoRead>(
    key,
    () => getMiTurno(uuid_sesion as string) as Promise<MiTurnoRead>,
    {
      refreshInterval: MI_TURNO_REFRESH_INTERVAL_MS,
      dedupingInterval: MI_TURNO_DEDUPING_INTERVAL_MS,
      shouldRetryOnError: (err) => {
        if (err instanceof ParkosHttpError) {
          return err.status !== 401 && err.status !== 403 && err.status !== 404;
        }
        return true;
      },
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('parkos:auth:cleared'));
          }
          return;
        }
        console.warn('[useMiTurno] polling failed', err);
      },
    },
  );

  // Zero-state fallback (REQ-OPS-188, DA-F12.1-4): the hook returns
  // the all-zero payload whenever SWR has not yet populated, so the
  // panel renders zeros without skeleton / error UI on cold boot,
  // loading, or after a recoverable 5xx. The `MiTurnoRead` shape is
  // preserved so consumers can read fields unconditionally.
  const effectiveData: MiTurnoRead =
    data ?? (emptyMiTurno(uuid_sesion, null) as MiTurnoRead);
  const isStale = data !== undefined && error !== undefined;

  return {
    data: effectiveData,
    error,
    isStale,
    refresh: async () => mutate(),
  };
}