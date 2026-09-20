/**
 * `useSuscripcionesProximasVencer.ts` — SWR polling hook for the
 * "próximas a vencer" banner + panel on the F6.x dashboard
 * (HU-F9.2, REQ-OPS-181).
 *
 * Calls `GET /api/v1/suscripciones-cliente/proximas-vencer?uuid_sucursal=X`
 * with `refreshInterval: 60_000` (60 seconds, OD-1 ratified).
 *
 * Per spec REQ-OPS-181:
 *   - `dias_para_vencer = floor((fecha_vencimiento_ms - NOW_ms) / 86_400_000)`
 *   - Filter out items where `dias_para_vencer < 0` (vencidas do not
 *     appear here; they appear in the listing general as "vencida").
 *   - Sort `fecha_vencimiento` ASCENDING (closest expiry first).
 *   - 401 → `useAuthStore.clear()` + `parkos:auth:cleared` window
 *     event (F3.1 invariant preserved — mirrors F9.1 `useVentaSuscripcion`
 *     and F3.3 `useSesionActiva` precedent).
 *
 * The pure helper `computeProximasVencer(rows, now)` is exported so
 * the filter+sort logic is unit-testable without driving SWR.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const ONE_DAY_MS = 86_400_000;
const REFRESH_INTERVAL_MS = 60_000;
const DEDUPING_INTERVAL_MS = 30_000;

export interface ProximaVencerBackendRow {
  uuid: string;
  placa: string;
  cliente_nombre?: string;
  plan_nombre?: string;
  fecha_vencimiento: string; // ISO YYYY-MM-DD
  estado?: 'activa' | 'vencida' | 'suspendida';
}

export interface ProximaVencer {
  uuid: string;
  placa: string;
  cliente_nombre: string;
  plan_nombre: string;
  fecha_vencimiento: string;
  estado: 'activa' | 'vencida' | 'suspendida';
  dias_para_vencer: number;
}

/**
 * Pure helper — given raw rows from the backend and a `now` Date,
 * compute `dias_para_vencer` per row, filter out vencidas
 * (`dias < 0`), and sort by `fecha_vencimiento` ASC. Exported for
 * testability.
 */
export function computeProximasVencer(
  rows: ProximaVencerBackendRow[],
  now: Date,
): ProximaVencer[] {
  return rows
    .map<ProximaVencer>((r) => {
      const v = new Date(`${r.fecha_vencimiento}T00:00:00Z`).getTime();
      const dias = Math.floor((v - now.getTime()) / ONE_DAY_MS);
      return {
        uuid: r.uuid,
        placa: r.placa,
        cliente_nombre: r.cliente_nombre ?? '',
        plan_nombre: r.plan_nombre ?? '',
        fecha_vencimiento: r.fecha_vencimiento,
        estado: r.estado ?? 'activa',
        dias_para_vencer: dias,
      };
    })
    .filter((it) => it.dias_para_vencer >= 0)
    .sort((a, b) => a.fecha_vencimiento.localeCompare(b.fecha_vencimiento));
}

export interface UseSuscripcionesProximasVencerReturn {
  data: ProximaVencer[] | undefined;
  error: Error | undefined;
  isLoading: boolean;
  refresh: () => Promise<ProximaVencer[] | undefined>;
}

/**
 * SWR hook — `uuid_sucursal === null` or no `accessToken` → key is
 * `null`, SWR skips the fetch (mirrors F6.1 `useIngresoActivo` gate).
 *
 * Returns `{ data, error, isLoading, refresh }`. The dashboard
 * banner + panel react only to `data?.length > 0`; `data === undefined`
 * is the loading state (no banner flash).
 */
export function useSuscripcionesProximasVencer(
  uuid_sucursal: string | null,
): UseSuscripcionesProximasVencerReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key =
    uuid_sucursal && accessToken
      ? `/api/v1/suscripciones-cliente/proximas-vencer?uuid_sucursal=${uuid_sucursal}`
      : null;

  const fetcher = async (k: string): Promise<ProximaVencer[]> => {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = (await parkosFetch<unknown>(k)) as ProximaVencerBackendRow[];
    if (!Array.isArray(raw)) return [];
    return computeProximasVencer(raw, new Date());
  };

  const { data, error, isLoading, mutate } = useSWR<ProximaVencer[]>(
    key,
    fetcher,
    {
      refreshInterval: REFRESH_INTERVAL_MS,
      dedupingInterval: DEDUPING_INTERVAL_MS,
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
        }
      },
    },
  );

  return {
    data,
    error,
    isLoading,
    refresh: async () => mutate(),
  };
}
