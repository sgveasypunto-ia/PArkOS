/**
 * `reporteriaApi.ts` — HTTP client for the HU-F17.1/HU-F17.2 operational
 * reports (web_admin).
 *
 * Endpoints consumed (branch API, known drift -- see Reporteria.tsx):
 *   - GET /api/v1/operacion/ingresos?uuid_sucursal=&placa=&activo=&limit=
 *   - GET /api/v1/operacion/salidas?uuid_sucursal=&placa=&fecha_salida__gte=&fecha_salida__lte=&limit=
 *   - GET /api/v1/operacion/ocupacion?uuid_sucursal=
 *
 * Endpoints consumed (admin API, dedicated reporteria surface):
 *   - GET /api/v1/admin/reporteria/operacional?uuid_sucursal=&fecha_desde=&fecha_hasta=
 *     &uuid_tipo_vehiculo=&cursor=&limit= (HU-F17.1 totals + HU-F17.2
 *     ``ingresos``/``tiempos_estancia`` additions)
 *   - GET /api/v1/admin/reporteria/ocupacion?desde=&hasta= (HU-F17.2,
 *     cross-branch heatmap + BR2 occupancy ratio)
 *
 * The first three are wrapped by ``auth/tenancy.py::require_branch_scope``
 * (PR-A): the response is already restricted to the caller's
 * permitted branches when the X-Sucursal-Context header is present,
 * which `parkosFetch` injects from `parkos.lastSelectedSucursal`. The
 * admin-reporteria endpoints resolve scope fresh server-side instead
 * (see their own backend docstrings).
 *
 * This module is a thin transport. SWR caching lives in
 * `useReporteriaIngresos` / `useReporteriaSalidas` / `useReporteriaOcupacion` /
 * `useReporteriaOperacional` / `useReporteriaOcupacionHeatmap` so the keys,
 * the revalidation policy and the per-tab activation live in one place —
 * the same split `features/audit` uses.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@/lib/fetch';
import { z } from 'zod';

import {
  ingresoReadSchema,
  salidaListReadSchema,
  ocupacionResponseSchema,
  reporteOperacionalResponseSchema,
  reporteOcupacionHeatmapResponseSchema,
  reporteFacturasResponseSchema,
  reporteFeResponseSchema,
  reportePagosResponseSchema,
  reporteSuscripcionesCohorteResponseSchema,
  type IngresoRead,
  type SalidaListRead,
  type OcupacionResponse,
  type ReporteOperacionalResponse,
  type ReporteOcupacionHeatmapResponse,
  type ReporteriaQuery,
  type ReporteFacturasResponse,
  type ReporteFeResponse,
  type ReportePagosResponse,
  type ReporteSuscripcionesCohorteResponse,
} from './reporteriaSchema';

const ING_PATH = '/api/v1/operacion/ingresos';
const SAL_PATH = '/api/v1/operacion/salidas';
const OCU_PATH = '/api/v1/operacion/ocupacion';

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `reporteriaApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchReporteriaIngresos(
  query: ReporteriaQuery,
): Promise<IngresoRead[]> {
  const params = new URLSearchParams();
  params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.placa) params.set('placa', query.placa);
  if (query.activo !== undefined) params.set('activo', String(query.activo));
  params.set('limit', String(query.limit ?? 50));
  const url = `${ING_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return z.array(ingresoReadSchema).parse(raw);
}

export async function fetchReporteriaSalidas(
  query: ReporteriaQuery,
): Promise<SalidaListRead[]> {
  const params = new URLSearchParams();
  params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.placa) params.set('placa', query.placa);
  if (query.fecha_desde) params.set('fecha_salida__gte', query.fecha_desde);
  if (query.fecha_hasta) params.set('fecha_salida__lte', query.fecha_hasta);
  params.set('limit', String(query.limit ?? 50));
  const url = `${SAL_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return z.array(salidaListReadSchema).parse(raw);
}

export async function fetchReporteriaOcupacion(
  uuid_sucursal: string,
): Promise<OcupacionResponse> {
  const params = new URLSearchParams();
  params.set('uuid_sucursal', uuid_sucursal);
  const url = `${OCU_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return ocupacionResponseSchema.parse(raw);
}

const OPER_PATH = '/api/v1/admin/reporteria/operacional';

export async function fetchReporteriaOperacional(query: {
  uuid_sucursal: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  // HU-F17.2 additions -- all optional, additive to the existing
  // "Totales del periodo" query (see reporteriaSchema.ts for the wire
  // shape these unlock: `ingresos` + `tiempos_estancia`).
  uuid_tipo_vehiculo?: string;
  cursor?: string;
  limit?: number;
}): Promise<ReporteOperacionalResponse> {
  const params = new URLSearchParams();
  params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.fecha_desde) params.set('fecha_desde', query.fecha_desde);
  if (query.fecha_hasta) params.set('fecha_hasta', query.fecha_hasta);
  if (query.uuid_tipo_vehiculo) params.set('uuid_tipo_vehiculo', query.uuid_tipo_vehiculo);
  if (query.cursor) params.set('cursor', query.cursor);
  if (query.limit) params.set('limit', String(query.limit));
  const url = `${OPER_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return reporteOperacionalResponseSchema.parse(raw);
}

const OCU_HEATMAP_PATH = '/api/v1/admin/reporteria/ocupacion';

export async function fetchReporteriaOcupacionHeatmap(query: {
  desde?: string;
  hasta?: string;
}): Promise<ReporteOcupacionHeatmapResponse> {
  const params = new URLSearchParams();
  if (query.desde) params.set('desde', query.desde);
  if (query.hasta) params.set('hasta', query.hasta);
  const url = `${OCU_HEATMAP_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return reporteOcupacionHeatmapResponseSchema.parse(raw);
}

// HU-F17.3 -- reportería financiera (facturas, FE, pagos).
const FACTURAS_PATH = '/api/v1/admin/reporteria/facturas';
const FE_PATH = '/api/v1/admin/reporteria/fe';
const PAGOS_PATH = '/api/v1/admin/reporteria/pagos';

export async function fetchReporteriaFacturas(query: {
  uuid_sucursal: string;
  desde?: string;
  hasta?: string;
  cursor?: string;
  limit?: number;
}): Promise<ReporteFacturasResponse> {
  const params = new URLSearchParams();
  params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.desde) params.set('desde', query.desde);
  if (query.hasta) params.set('hasta', query.hasta);
  if (query.cursor) params.set('cursor', query.cursor);
  if (query.limit) params.set('limit', String(query.limit));
  const url = `${FACTURAS_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return reporteFacturasResponseSchema.parse(raw);
}

export async function fetchReporteriaFe(query: {
  estado?: string;
  cursor?: string;
  limit?: number;
}): Promise<ReporteFeResponse> {
  const params = new URLSearchParams();
  if (query.estado) params.set('estado', query.estado);
  if (query.cursor) params.set('cursor', query.cursor);
  if (query.limit) params.set('limit', String(query.limit));
  const url = `${FE_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return reporteFeResponseSchema.parse(raw);
}

export async function fetchReporteriaPagos(query: {
  uuid_sucursal: string;
  desde?: string;
  hasta?: string;
}): Promise<ReportePagosResponse> {
  const params = new URLSearchParams();
  params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.desde) params.set('desde', query.desde);
  if (query.hasta) params.set('hasta', query.hasta);
  const url = `${PAGOS_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return reportePagosResponseSchema.parse(raw);
}

// HU-F17.4 -- subscription cohort retention heatmap + próximas a vencer.
// Cross-branch (no uuid_sucursal param), same reasoning as the HU-F17.2
// occupancy heatmap / HU-F17.3 FE endpoints.
const SUSCRIPCIONES_COHORTE_PATH = '/api/v1/admin/reporteria/suscripciones/cohorte';

export async function fetchReporteriaSuscripcionesCohorte(query: {
  desde?: string;
  hasta?: string;
}): Promise<ReporteSuscripcionesCohorteResponse> {
  const params = new URLSearchParams();
  if (query.desde) params.set('desde', query.desde);
  if (query.hasta) params.set('hasta', query.hasta);
  const url = `${SUSCRIPCIONES_COHORTE_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return reporteSuscripcionesCohorteResponseSchema.parse(raw);
}