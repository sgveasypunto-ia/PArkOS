/**
 * `useCantidadByKey()` — SWR hook que recorre la cadena bi-temporal de
 * cupos (cantidad-vehiculos-sucursal) por business key.
 *
 * Análogo a ``useTarifasByKey`` — mismo patrón de fallback, deduping 5min,
 * 401 → logout defensivo. Sin refreshInterval activo (PR-C v2: las
 * cantidades cambian cuando el admin publica un PUT o cuando los
 * ingresos activos cambian, no en tiempo real).
 *
 * El parámetro ``tipo_vehiculo`` es opcional — el factory acepta NULL
 * (cupos sin tipo discriminado). ``sucursal`` es requerido.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { listCuposByKey, type Cupo } from '../api/cuposApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

export interface UseCantidadByKeyReturn {
  versiones: Cupo[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<Cupo[] | undefined>;
}

export function useCantidadByKey(
  sucursal: string | null,
  tipo_vehiculo?: string | null,
): UseCantidadByKeyReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const key =
    accessToken && sucursal
      ? ['/api/v1/empresa/cantidad-vehiculos-sucursal/by-key', sucursal, tipo_vehiculo ?? null]
      : null;

  const { data, error, isLoading, mutate } = useSWR<Cupo[]>(
    key,
    async () => {
      if (!sucursal) return [];
      return listCuposByKey({ sucursal, tipo_vehiculo });
    },
    {
      dedupingInterval: DEDUPING_INTERVAL_MS,
      shouldRetryOnError: (err) =>
        !(err instanceof ParkosHttpError && err.status === 404),
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
    versiones: data ?? [],
    isLoading,
    error,
    refresh: async () => {
      const result = await mutate();
      return result ?? [];
    },
  };
}
