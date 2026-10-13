/**
 * `useCantidadList()` — SWR hook para el listado de cupos vigentes de
 * la sucursal activa (admin branch-scoped).
 *
 * Operator-reported bug (2026-10-13): la clave SWR era el string
 * estático ``'cupos-list'``, pero el handler dedicado
 * ``GET /empresa/cantidad-vehiculos-sucursal`` (HU-F15.1 BR4) tiene
 * el dep ``requires_sucursal`` y el listener de tenant
 * ``do_orm_execute`` agrega ``uuid_sucursal = :ctx`` server-side,
 * scopeando los rows al ``X-Sucursal-Context`` del header. Resultado:
 * al cambiar de sucursal dentro del ``dedupingInterval`` de 5min, SWR
 * servía los rows de la sucursal anterior y el filtro client-side
 * ``cupos.filter(c => c.uuid_sucursal === selected)`` daba 0. ``Ctrl+R``
 * limpiaba la cache y "se reflejaban correctamente" — comportamiento
 * intermitente documentado por el operador.
 *
 * La fix es hacer la clave branch-scoped (``['cupos-list', sucursal]``)
 * para que cada sucursal tenga su propia entrada en el cache; cambiar
 * de sucursal re-dispara el fetch automáticamente (o lee del cache de
 * esa sucursal si seguimos dentro del deduping). Mismo patrón ya
 * aplicado en ``useCantidadByKey`` (mismo módulo, también branch-scoped)
 * y en ``useResumenKpi`` (dashboard cross-branch).
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

  // Branch-scoped key: la cache tiene una entrada por sucursal para que
  // el cambio de selección re-fetchee (o lea del cache de esa sucursal)
  // sin servir los rows stale de la sucursal anterior. ``null`` cuando
  // todavía no hay sucursal activa (el caller debe gate-keepear arriba;
  // el componente <RequireSucursal> lo garantiza en /dashboard).
  const key = accessToken && sucursal ? ['cupos-list', sucursal] : null;

  const { data, error, isLoading, mutate } = useSWR<Cupo[]>(
    key,
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
