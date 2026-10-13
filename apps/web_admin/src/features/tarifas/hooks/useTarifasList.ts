/**
 * `useTarifasList()` — SWR hook para el listado de tarifas vigentes de
 * la sucursal activa (admin branch-scoped).
 *
 * Operator-reported bug (2026-10-13): la clave SWR era el string
 * estático ``'tarifas-list'``, pero el handler dedicado
 * ``GET /empresa/tarifas-sucursal`` tiene el dep ``requires_sucursal``
 * y el listener de tenant ``do_orm_execute`` agrega
 * ``uuid_sucursal = :ctx`` server-side, scopeando los rows al
 * ``X-Sucursal-Context`` del header. Resultado: al cambiar de sucursal
 * dentro del ``dedupingInterval`` de 5min, SWR servía los rows de la
 * sucursal anterior y el filtro client-side
 * ``tarifas.filter(t => t.uuid_sucursal === selected)`` daba 0. ``Ctrl+R``
 * limpiaba la cache y "se reflejaban correctamente" — comportamiento
 * intermitente documentado por el operador.
 *
 * La fix es hacer la clave branch-scoped (``['tarifas-list', sucursal]``)
 * para que cada sucursal tenga su propia entrada en el cache; cambiar
 * de sucursal re-dispara el fetch automáticamente (o lee del cache de
 * esa sucursal si seguimos dentro del deduping). Mismo patrón ya
 * aplicado en ``useTarifasByKey`` y ``useTarifasVigentesEn`` (mismo
 * módulo, también branch-scoped) y en ``useResumenKpi`` (dashboard
 * cross-branch).
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

  // Branch-scoped key: la cache tiene una entrada por sucursal para que
  // el cambio de selección re-fetchee (o lea del cache de esa sucursal)
  // sin servir los rows stale de la sucursal anterior. ``null`` cuando
  // todavía no hay sucursal activa.
  const key = accessToken && sucursal ? ['tarifas-list', sucursal] : null;

  const { data, error, isLoading, mutate } = useSWR<Tarifa[]>(
    key,
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
