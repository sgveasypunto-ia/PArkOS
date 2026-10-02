/**
 * `useReporteria.ts` — SWR hooks for the operational reports
 * (HU-F17.1, web_admin).
 *
 * One hook per endpoint, all keyed on `query.uuid_sucursal` plus the
 * filter fields that affect the wire payload — branch switch invalidates
 * the cache (same trick the AuditDashboard uses via SWR key embedding).
 *
 * `activas` boolean defaults to false: the empty filter set is what an
 * admin reaches on first visit, and showing every historical entry
 * across the day would hide recent activity in a long-running branch.
 *
 * Why three hooks instead of one: each tab fetches on demand (SWR
 * lazy load), so the reportería page can render Ingresos without
 * also pulling Salidas + Ocupacion. The page activates the right
 * tab's hook via the Radix `Tabs` activation callback.
 */
import useSWR from 'swr';

import {
  fetchReporteriaIngresos,
  fetchReporteriaSalidas,
  fetchReporteriaOcupacion,
  fetchReporteriaOperacional,
  fetchReporteriaOcupacionHeatmap,
} from '../api/reporteriaApi';
import type {
  IngresoRead,
  SalidaListRead,
  OcupacionResponse,
  ReporteOperacionalResponse,
  ReporteOcupacionHeatmapResponse,
  ReporteriaQuery,
} from '../api/reporteriaSchema';

const STALE = { revalidateOnFocus: false, dedupingInterval: 30_000 };

export function useReporteriaIngresos(query: ReporteriaQuery | null) {
  return useSWR<IngresoRead[]>(
    query ? reporteriaIngresosKey(query) : null,
    () => fetchReporteriaIngresos(query as ReporteriaQuery),
    STALE,
  );
}

export function useReporteriaSalidas(query: ReporteriaQuery | null) {
  return useSWR<SalidaListRead[]>(
    query ? reporteriaSalidasKey(query) : null,
    () => fetchReporteriaSalidas(query as ReporteriaQuery),
    STALE,
  );
}

export function useReporteriaOcupacion(uuid_sucursal: string | null) {
  return useSWR<OcupacionResponse>(
    uuid_sucursal ? reporteriaOcupacionKey(uuid_sucursal) : null,
    () => fetchReporteriaOcupacion(uuid_sucursal as string),
    { ...STALE, refreshInterval: 0 },
  );
}

export function useReporteriaOperacional(
  query:
    | {
        uuid_sucursal: string;
        fecha_desde?: string;
        fecha_hasta?: string;
      }
    | null,
) {
  return useSWR<ReporteOperacionalResponse>(
    query ? reporteriaOperacionalKey(query) : null,
    () => fetchReporteriaOperacional(query as never),
    STALE,
  );
}

export function reporteriaIngresosKey(q: ReporteriaQuery): string {
  return [
    '/api/v1/operacion/ingresos',
    q.uuid_sucursal,
    q.placa ?? '',
    q.activo === undefined ? '' : String(q.activo),
    q.limit ?? 50,
  ].join('::');
}

export function reporteriaSalidasKey(q: ReporteriaQuery): string {
  return [
    '/api/v1/operacion/salidas',
    q.uuid_sucursal,
    q.placa ?? '',
    q.fecha_desde ?? '',
    q.fecha_hasta ?? '',
    q.limit ?? 50,
  ].join('::');
}

export function reporteriaOcupacionKey(uuid: string): string {
  return `/api/v1/operacion/ocupacion::${uuid}`;
}

export function reporteriaOperacionalKey(q: {
  uuid_sucursal: string;
  fecha_desde?: string;
  fecha_hasta?: string;
}): string {
  return [
    '/api/v1/admin/reporteria/operacional',
    q.uuid_sucursal,
    q.fecha_desde ?? '',
    q.fecha_hasta ?? '',
  ].join('::');
}

// HU-F17.2 -- cross-branch occupancy heatmap. Keyed on the date range
// only (no uuid_sucursal -- the endpoint is cross-branch by nature, same
// reasoning as the executive dashboard's `dashboard/resumen`).
export function useReporteriaOcupacionHeatmap(
  range: { desde?: string; hasta?: string } | null,
) {
  return useSWR<ReporteOcupacionHeatmapResponse>(
    range ? reporteriaOcupacionHeatmapKey(range) : null,
    () => fetchReporteriaOcupacionHeatmap(range as { desde?: string; hasta?: string }),
    STALE,
  );
}

export function reporteriaOcupacionHeatmapKey(r: {
  desde?: string;
  hasta?: string;
}): string {
  return ['/api/v1/admin/reporteria/ocupacion', r.desde ?? '', r.hasta ?? ''].join('::');
}