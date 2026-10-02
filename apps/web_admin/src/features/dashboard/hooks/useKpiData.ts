/**
 * `useKpiData.ts` — SWR data for the 9-card executive dashboard grid
 * (HU-F17.1, T3).
 *
 * Design note on "9 claves SWR": the 9 KPI cards are backed by exactly
 * TWO real HTTP requests --
 *
 *   - `/admin/sucursales/{selected}/dashboard`  -> 3 cards (ingresos,
 *     facturas, monto total) for the currently BranchSelector-selected
 *     sucursal -- unchanged from the original `pages/Dashboard.tsx`.
 *   - `/admin/dashboard/resumen?sucursales=...` -> 6 cards (ocupación,
 *     suscripciones, medios de pago, top sucursales, sync, alertas) --
 *     the new cross-branch executive summary (BR2), scoped to every
 *     sucursal the actor is permitted on (independent of `selected`:
 *     ranking/aggregating branches against only the one currently
 *     selected would defeat the point of a "top-5" or "aggregated sync"
 *     card).
 *
 * Each of the 9 returned keys is its OWN SWR cache entry (so each
 * `KpiCard` gets its own independent loading/error state and can mount
 * its skeleton without waiting on its siblings), but the two underlying
 * fetchers are deduped by SWR's key-based cache -- calling this hook
 * from multiple cards never re-fetches the network twice for the same
 * data.
 */
import useSWR from 'swr';

import { fetchSucursalDashboard, fetchDashboardResumen } from '../api/dashboardApi';
import type {
  DashboardResumen,
  DashboardTopSucursalItem,
  DashboardOcupacionHorariaItem,
} from '../api/dashboardSchema';

const STALE = { revalidateOnFocus: false, dedupingInterval: 30_000 } as const;

export function dashboardKey(uuid: string): string {
  return `/api/v1/admin/sucursales/${uuid}/dashboard`;
}

export function resumenKey(sucursales: readonly string[]): string {
  return ['/api/v1/admin/dashboard/resumen', ...[...sucursales].sort()].join('::');
}

export interface KpiCardState<T> {
  value: T | undefined;
  loading: boolean;
  error: boolean;
}

function cardState<T>(
  value: T | undefined,
  isLoading: boolean,
  error: unknown,
): KpiCardState<T> {
  return { value, loading: isLoading, error: Boolean(error) };
}

export interface UseKpiDataResult {
  ingresos: KpiCardState<number>;
  facturas: KpiCardState<number>;
  montoTotal: KpiCardState<number>;
  ocupacion: KpiCardState<{ ocupados: number; capacidad: number; porcentaje: number | null }>;
  suscripciones: KpiCardState<number>;
  mediosPago: KpiCardState<{ medio_pago: string; monto_total: number }[]>;
  topSucursales: KpiCardState<DashboardTopSucursalItem[]>;
  sync: KpiCardState<{
    sucursales_ok: number;
    sucursales_degradadas: number;
    queue_depth_total: number;
    max_lag_seconds: number | null;
  }>;
  alertas: KpiCardState<{ severity: string; count: number }[]>;
  /** Raw resumen payload, for the charts section to reuse without a third fetch. */
  resumen: DashboardResumen | undefined;
  ocupacionHoraria: DashboardOcupacionHorariaItem[];
}

/**
 * @param selected sucursal currently picked in the BranchSelector, or `null`
 *   before the first branch loads.
 * @param permitidas every sucursal uuid the actor is allowed to see -- the
 *   scope of the cross-branch resumen cards (BR2).
 */
export function useKpiData(
  selected: string | null,
  permitidas: readonly string[],
): UseKpiDataResult {
  const branch = useSWR(
    selected ? dashboardKey(selected) : null,
    () => fetchSucursalDashboard(selected as string),
    STALE,
  );
  const resumen = useSWR(
    permitidas.length > 0 ? resumenKey(permitidas) : null,
    () => fetchDashboardResumen(permitidas),
    STALE,
  );

  return {
    ingresos: cardState(branch.data?.ingresos_count, branch.isLoading, branch.error),
    facturas: cardState(branch.data?.facturas_emitidas_count, branch.isLoading, branch.error),
    montoTotal: cardState(branch.data?.ingresos_monto_total, branch.isLoading, branch.error),
    ocupacion: cardState(resumen.data?.ocupacion, resumen.isLoading, resumen.error),
    suscripciones: cardState(
      resumen.data?.suscripciones_activas.count,
      resumen.isLoading,
      resumen.error,
    ),
    mediosPago: cardState(resumen.data?.medios_pago_dia, resumen.isLoading, resumen.error),
    topSucursales: cardState(resumen.data?.top_sucursales, resumen.isLoading, resumen.error),
    sync: cardState(resumen.data?.sync_agregado, resumen.isLoading, resumen.error),
    alertas: cardState(resumen.data?.alertas_por_severidad, resumen.isLoading, resumen.error),
    resumen: resumen.data,
    ocupacionHoraria: resumen.data?.ocupacion_horaria ?? [],
  };
}
