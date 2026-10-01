/**
 * `useTarifasList()` — SWR hook para el listado global de tarifas
 * vigentes de TODAS las sucursales (el admin necesita ver
 * cross-branch). Wrapper de ``GET /api/v1/empresa/tarifas-sucursal``,
 * que el factory emite sin filtro de sucursal (sólo ``vigente_hasta
 * IS NULL``).
 *
 * El parámetro ``sucursal`` queda en la firma por compatibilidad con
 * posibles callers futuros que quieran filtrar client-side; por ahora
 * se ignora (el hook siempre lista todas).
 *
 * Mismo patrón que ``useTarifasByKey``: deduping 5min, 401 → logout
 * defensivo, sin refreshInterval activo.
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

export function useTarifasList(_sucursal?: string | null): UseTarifasListReturn {
  // The factory handler does not filter by sucursal; the hook always
  // lists all vigentes across branches. The parameter is kept for
  // future client-side filtering and to match the by-key hook's
  // signature (so a caller can swap without plumbing changes).
  void _sucursal;

  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<Tarifa[]>(
    accessToken ? 'tarifas-list' : null,
    () => listTarifas({ limit: 200 }),
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
