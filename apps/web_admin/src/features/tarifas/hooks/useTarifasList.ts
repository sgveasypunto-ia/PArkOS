/**
 * `useTarifasList()` — SWR hook para el listado vigente de tarifas de
 * una sucursal (wrapper de ``GET /api/v1/empresa/tarifas-sucursal``).
 *
 * Mismo patrón que ``useTarifasByKey``: deduping 5min, 401 → logout
 * defensivo, sin refreshInterval activo (catálogo reference data).
 *
 * Devuelve un array vacío mientras el admin no carga la página o el
 * endpoint no está disponible. Sin fallback hardcoded — el listado
 * vigente es lo que se muestra al operador y un fallback estático
 * induciría a error de cálculo de cotización.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { listTarifas, type Tarifa } from '../api/tarifasApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

export interface UseTarifasListReturn {
  tarifas: Tarifa[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<Tarifa[] | undefined>;
}

export function useTarifasList(sucursal: string | null): UseTarifasListReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<Tarifa[]>(
    accessToken && sucursal ? ['tarifas-list', sucursal] : null,
    async () => {
      if (!sucursal) return [];
      return listTarifas({ limit: 200 });
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
    tarifas: data ?? [],
    isLoading,
    error,
    refresh: async () => {
      const result = await mutate();
      return result ?? [];
    },
  };
}
