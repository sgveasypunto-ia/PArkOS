/**
 * `useCantidadList()` — SWR hook para el listado global de cupos
 * vigentes de TODAS las sucursales (admin cross-branch).
 *
 * Mismo patrón que ``useTarifasList`` después del fix D-02.3. El
 * factory handler no filtra por sucursal (sólo ``vigente_hasta IS
 * NULL``).
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

export function useCantidadList(_sucursal?: string | null): UseCantidadListReturn {
  void _sucursal;

  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<Cupo[]>(
    accessToken ? 'cupos-list' : null,
    () => listCupos({ limit: 200 }),
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
