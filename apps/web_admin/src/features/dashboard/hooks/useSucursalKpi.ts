/**
 * `useSucursalKpi.ts` — branch-scoped KPI data (HU-F17.1, post-split).
 *
 * The 3 cards that genuinely belong to a single selected branch --
 * INGRESOS, FACTURAS, MONTO TOTAL. Fetched from
 * `/admin/sucursales/{selected}/dashboard`. The selected UUID comes
 * from `<RequireSucursal>` upstream, so the hook assumes a non-null
 * `selected` (it short-circuits with `null` SWR key when it is null,
 * same dedup-friendly pattern the old combined hook used).
 *
 * The 6 cross-branch KPIs (ocupacion, suscripciones, medios de pago,
 * top sucursales, sync agregado, alertas) now live in
 * `useResumenKpi.ts` and are consumed by the global HQ at `/`, not by
 * the branch-scoped `/dashboard`.
 */
import useSWR from 'swr';

import { fetchSucursalDashboard } from '../api/dashboardApi';
import type { SucursalDashboard } from '../api/dashboardSchema';

const STALE = { revalidateOnFocus: false, dedupingInterval: 30_000 } as const;

export function dashboardKey(uuid: string): string {
  return `/api/v1/admin/sucursales/${uuid}/dashboard`;
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

export interface UseSucursalKpiResult {
  ingresos: KpiCardState<number>;
  facturas: KpiCardState<number>;
  montoTotal: KpiCardState<number>;
  /** Raw payload, kept for callers that want derived metrics (e.g. lastSync). */
  raw: SucursalDashboard | undefined;
}

export function useSucursalKpi(selected: string | null): UseSucursalKpiResult {
  const branch = useSWR(
    selected ? dashboardKey(selected) : null,
    () => fetchSucursalDashboard(selected as string),
    STALE,
  );

  return {
    ingresos: cardState(branch.data?.ingresos_count, branch.isLoading, branch.error),
    facturas: cardState(branch.data?.facturas_emitidas_count, branch.isLoading, branch.error),
    montoTotal: cardState(branch.data?.ingresos_monto_total, branch.isLoading, branch.error),
    raw: branch.data,
  };
}
