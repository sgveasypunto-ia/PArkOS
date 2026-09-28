/**
 * `useCantidadList()` — SWR hook para el listado vigente de cupos
 * de una sucursal (wrapper de ``GET /api/v1/empresa/cantidad-vehiculos-sucursal``).
 *
 * Análogo a ``useTarifasList``. Sin fallback hardcoded.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { listCupos, type Cupo } from '../api/cuposApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

export interface UseCantidadListReturn {
  cupos: Cupo[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<Cupo[] | undefined>;
}

export function useCantidadList(sucursal: string | null): UseCantidadListReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<Cupo[]>(
    accessToken && sucursal ? ['cupos-list', sucursal] : null,
    async () => {
      if (!sucursal) return [];
      return listCupos({ limit: 200 });
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
    cupos: data ?? [],
    isLoading,
    error,
    refresh: async () => {
      const result = await mutate();
      return result ?? [];
    },
  };
}
