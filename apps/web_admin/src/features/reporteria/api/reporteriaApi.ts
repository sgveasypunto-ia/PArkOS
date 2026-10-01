/**
 * `reporteriaApi.ts` — HTTP client for the HU-F17.1 operational reports
 * (web_admin).
 *
 * Endpoints consumed (branch API):
 *   - GET /api/v1/operacion/ingresos?uuid_sucursal=&placa=&activo=&limit=
 *   - GET /api/v1/operacion/salidas?uuid_sucursal=&placa=&fecha_salida__gte=&fecha_salida__lte=&limit=
 *   - GET /api/v1/operacion/ocupacion?uuid_sucursal=
 *
 * All three are wrapped by ``auth/tenancy.py::require_branch_scope``
 * (PR-A): the response is already restricted to the caller's
 * permitted branches when the X-Sucursal-Context header is present,
 * which `parkosFetch` injects from `parkos.lastSelectedSucursal`.
 *
 * This module is a thin transport. SWR caching lives in
 * `useReporteriaIngresos` / `useReporteriaSalidas` / `useReporteriaOcupacion`
 * so the keys, the revalidation policy and the per-tab activation live
 * in one place — the same split `features/audit` uses.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@/lib/fetch';
import { z } from 'zod';

import {
  ingresoReadSchema,
  salidaListReadSchema,
  ocupacionResponseSchema,
  reporteOperacionalResponseSchema,
  type IngresoRead,
  type SalidaListRead,
  type OcupacionResponse,
  type ReporteOperacionalResponse,
  type ReporteriaQuery,
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
}): Promise<ReporteOperacionalResponse> {
  const params = new URLSearchParams();
  params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.fecha_desde) params.set('fecha_desde', query.fecha_desde);
  if (query.fecha_hasta) params.set('fecha_hasta', query.fecha_hasta);
  const url = `${OPER_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return reporteOperacionalResponseSchema.parse(raw);
}