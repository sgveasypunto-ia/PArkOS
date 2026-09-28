/**
 * `useConfiguracionSeguridad()` — SWR hook para la configuración de
 * seguridad (max intentos login, minutos de bloqueo, etc.).
 *
 * Mismo patrón que ``useConfiguracionTolerancias`` — deduping 5min,
 * 401 → logout defensivo. Sin fallback hardcoded: la configuración de
 * seguridad es OPERACIONALMENTE SENSIBLE (cambiar ``max_intentos_login``
 * afecta a TODOS los operadores en TODAS las sucursales cuando es el
 * global default). Un fallback estático induciría a error de lockout.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  listConfiguracionSeguridad,
  type ConfiguracionSeguridad,
} from '../api/configuracionSeguridadApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

export interface UseConfiguracionSeguridadReturn {
  rows: ConfiguracionSeguridad[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<ConfiguracionSeguridad[] | undefined>;
}

export function useConfiguracionSeguridad(): UseConfiguracionSeguridadReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<ConfiguracionSeguridad[]>(
    accessToken ? '/api/v1/configuracion/configuracion-seguridad' : null,
    () => listConfiguracionSeguridad({ limit: 200 }),
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
