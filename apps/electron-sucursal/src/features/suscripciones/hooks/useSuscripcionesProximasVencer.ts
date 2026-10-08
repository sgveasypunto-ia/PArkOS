/**
 * `useSuscripcionesProximasVencer.ts` — SWR polling hook for the
 * "próximas a vencer" banner (HU-F9.2 REQ-OPS-181, corrected in PT-3).
 *
 * Calls `GET /api/v1/clientes/subscripciones/proximas-vencer` (the old
 * `/suscripciones-cliente/proximas-vencer` path never existed) with
 * `refreshInterval: 60_000`.
 *
 * The backend is authoritative: each row already carries
 * `dias_restantes`, `dias_alerta_pre_vencimiento` (per-subscription alert
 * threshold) and `puede_renovar` (any open subscription; there is no anticipation window). The
 * client does NOT recompute dates nor re-filter by a threshold; it only
 * sorts by `fecha_vencimiento` ASC (closest expiry first) and normalizes
 * the shape.
 *
 * 401 -> `useAuthStore.clear()` + `parkos:auth:cleared` window event
 * (F3.1 invariant preserved).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  GET_PROXIMAS_VENCER_PATH,
  SuscripcionVencimientoListSchema,
  type SuscripcionVencimientoItem,
} from '../api/renovacionApi';

const REFRESH_INTERVAL_MS = 60_000;
const DEDUPING_INTERVAL_MS = 30_000;

export interface ProximaVencer {
  uuid: string;
  cliente_nombre: string;
  plan_nombre: string;
  placas: string[];
  fecha_vencimiento: string;
  dias_restantes: number;
  dias_alerta_pre_vencimiento: number | null;
  puede_renovar: boolean;
  /** `true` when `dias_restantes < 0` (already expired). */
  vencida: boolean;
}

/**
 * Pure helper — normalizes backend rows and sorts by `fecha_vencimiento`
 * ASC. Exported for testability (no date arithmetic on purpose).
 */
export function computeProximasVencer(rows: SuscripcionVencimientoItem[]): ProximaVencer[] {
  return rows
    .map<ProximaVencer>((r) => ({
      uuid: r.uuid,
      cliente_nombre: r.cliente_nombre,
      plan_nombre: r.plan_nombre,
      placas: r.placas,
      fecha_vencimiento: r.fecha_vencimiento,
      dias_restantes: r.dias_restantes,
      dias_alerta_pre_vencimiento: r.dias_alerta_pre_vencimiento ?? null,
      puede_renovar: r.puede_renovar,
      vencida: r.dias_restantes < 0,
    }))
    .sort((a, b) => a.fecha_vencimiento.localeCompare(b.fecha_vencimiento));
}

export interface UseSuscripcionesProximasVencerReturn {
  data: ProximaVencer[] | undefined;
  error: Error | undefined;
  isLoading: boolean;
  refresh: () => Promise<ProximaVencer[] | undefined>;
}

/**
 * SWR hook — `uuid_sucursal === null` or no `accessToken` -> key is `null`,
 * SWR skips the fetch. `data === undefined` is the loading state (no banner
 * flash); the banner only renders when `data.length > 0`.
 */
export function useSuscripcionesProximasVencer(
  uuid_sucursal: string | null,
): UseSuscripcionesProximasVencerReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  // Array key: the branch is part of the cache identity (supervisors can switch branch).
  const key = uuid_sucursal && accessToken ? ([GET_PROXIMAS_VENCER_PATH, uuid_sucursal] as const) : null;

  const fetcher = async ([k]: readonly [string, string]): Promise<ProximaVencer[]> => {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = await parkosFetch<unknown>(k);
    const parsed = SuscripcionVencimientoListSchema.safeParse(raw);
    if (!parsed.success) {
      console.warn('[useSuscripcionesProximasVencer] unexpected payload', parsed.error.issues);
      return [];
    }
    return computeProximasVencer(parsed.data);
  };

  const { data, error, isLoading, mutate } = useSWR<ProximaVencer[]>(key, fetcher, {
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
  });

  return {
    data,
    error,
    isLoading,
    refresh: async () => mutate(),
  };
}
