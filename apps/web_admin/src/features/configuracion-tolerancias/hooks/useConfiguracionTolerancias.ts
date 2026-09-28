/**
 * `useConfiguracionTolerancias()` — SWR hook para el listado de
 * configuraciones de tolerancia (global default + per-branch override).
 *
 * Sin ``/efectiva?uuid_sucursal=...`` dedicated endpoint — la UI resuelve
 * client-side: la fila con ``uuid_sucursal === requested`` gana; si no
 * existe, usa la fila con ``uuid_sucursal === null`` (global default).
 *
 * Mismo patrón de fallback/deduping/401 que el resto de los hooks.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  listConfiguracionTolerancias,
  type ConfiguracionTolerancias,
} from '../api/configuracionToleranciasApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

export interface UseConfiguracionToleranciasReturn {
  rows: ConfiguracionTolerancias[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<ConfiguracionTolerancias[] | undefined>;
}

export function useConfiguracionTolerancias(): UseConfiguracionToleranciasReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<ConfiguracionTolerancias[]>(
    accessToken ? '/api/v1/configuracion/configuracion-tolerancias' : null,
    () => listConfiguracionTolerancias({ limit: 200 }),
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
    rows: data ?? [],
    isLoading,
    error,
    refresh: async () => {
      const result = await mutate();
      return result ?? [];
    },
  };
}
