/**
 * `useEmpresa` — SWR hook para el singleton Empresa
 * (HU-F15.2 de `plan.md:3537`).
 *
 * Empresa es un singleton tenant-global: una sola fila vigente. La
 * SWR key es estable (`'empresa-singleton'`) y el hook expone
 * `empresa` (la fila o `null` si todavía no se sembró), `isLoading`,
 * `error` y `refresh`.
 *
 * Mismo patrón que `useTarifasList` (`features/tarifas/hooks/`):
 * deduping 5min, 401 → logout defensivo, sin refreshInterval.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { getEmpresa, type Empresa } from '../api/empresaApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;
const SWR_KEY = 'empresa-singleton';

export interface UseEmpresaReturn {
  empresa: Empresa | null;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<Empresa | null | undefined>;
}

export function useEmpresa(): UseEmpresaReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<Empresa | null>(
    accessToken ? SWR_KEY : null,
    async () => getEmpresa(),
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
    empresa: data ?? null,
    isLoading,
    error,
    refresh: async () => mutate(),
  };
}
