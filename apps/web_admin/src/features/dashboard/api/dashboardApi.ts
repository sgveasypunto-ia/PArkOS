/**
 * `dashboardApi.ts` — HTTP client for the executive dashboard (HU-F17.1).
 *
 * Endpoints consumed (admin API):
 *   - GET /api/v1/admin/sucursales/{uuid}/dashboard
 *   - GET /api/v1/admin/dashboard/resumen?sucursales=X,Y,Z
 *
 * Thin transport only — SWR caching + key-building lives in
 * `hooks/useResumenKpi.ts` and `hooks/useSucursalKpi.ts`, same split as
 * `features/reporteria`.
 */
import { parkosFetchRaw } from '@/lib/fetch';

import {
  sucursalDashboardSchema,
  dashboardResumenSchema,
  type SucursalDashboard,
  type DashboardResumen,
} from './dashboardSchema';

async function fetchJson<T>(input: string): Promise<T> {
  const res = await parkosFetchRaw(input, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`dashboardApi: GET ${input} -> ${res.status}: ${body.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function fetchSucursalDashboard(uuidSucursal: string): Promise<SucursalDashboard> {
  const raw = await fetchJson<unknown>(`/api/v1/admin/sucursales/${uuidSucursal}/dashboard`);
  return sucursalDashboardSchema.parse(raw);
}

export async function fetchDashboardResumen(
  sucursales: readonly string[],
): Promise<DashboardResumen> {
  const params = new URLSearchParams();
  if (sucursales.length > 0) {
    params.set('sucursales', sucursales.join(','));
  }
  const qs = params.toString();
  const url = qs ? `/api/v1/admin/dashboard/resumen?${qs}` : '/api/v1/admin/dashboard/resumen';
  const raw = await fetchJson<unknown>(url);
  return dashboardResumenSchema.parse(raw);
}
