/**
 * `useResumenKpi.ts` — cross-branch KPI data for the global HQ at `/`
 * (HU-F17.1, post-split).
 *
 * Six cards that ONLY make sense aggregated across the operator's
 * permitted branches -- Ocupación agregada, Suscripciones activas,
 * Medios de pago del día, Top sucursales (30d), Estado de
 * sincronización, Alertas por severidad. Plus the raw payload (for
 * the cross-branch charts) and the occupancy-by-hour series (for the
 * heatmap).
 *
 * Independent of the BranchSelector selection by design: ranking or
 * aggregating branches against only the one currently selected would
 * defeat the point of a "top-5" or "aggregated sync" card. The hook
 * reads `permitidas` from `/admin/me`.
 */
import useSWR from 'swr';

import { fetchDashboardResumen } from '../api/dashboardApi';
import type {
  DashboardResumen,
  DashboardTopSucursalItem,
  DashboardOcupacionHorariaItem,
} from '../api/dashboardSchema';

const STALE = { revalidateOnFocus: false, dedupingInterval: 30_000 } as const;

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

export interface UseResumenKpiResult {
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

export function useResumenKpi(permitidas: readonly string[]): UseResumenKpiResult {
  const resumen = useSWR(
    permitidas.length > 0 ? resumenKey(permitidas) : null,
    () => fetchDashboardResumen(permitidas),
    STALE,
  );

  return {
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
