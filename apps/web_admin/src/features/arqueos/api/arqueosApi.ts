/**
 * `arqueosApi.ts` -- HTTP client for the F18.2 admin arqueo surface.
 *
 * Endpoints consumed:
 *   - ``GET /api/v1/caja/arqueo?uuid_sucursal=&fecha_desde=&fecha_hasta=&uuid_tipo_arqueo=&limit=&cursor=``
 *     (admin list, F18.1). Returns ``{items: ArqueoRead[], next_cursor: string|null}``.
 *   - ``GET /api/v1/caja-sesion/arqueos/{uuid}/diferencias``
 *     (per-arqueo deltas, exists since F1.13). Returns ``DiferenciasRead``.
 *
 * Why parkosFetchRaw (not SWR inside this file): the data hooks own
 * the SWR cache key + revalidation. Keeping the HTTP layer as a
 * pure fetch helper makes the dependency direction one-way and the
 * hooks unit-testable with the API module stubbed.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  arqueoResumenAdminReadSchema,
  arqueosListResponseSchema,
  diferenciasReadSchema,
  type ArqueoResumenAdminRead,
  type ArqueosListQuery,
  type ArqueosListResponse,
  type DiferenciasRead,
} from './arqueosSchema';

const LIST_PATH = '/api/v1/caja/arqueo';
const DIFERENCIAS_PATH_FRAGMENT = '/api/v1/caja-sesion/arqueos';
const ADMIN_RESUMEN_PATH = '/api/v1/caja/arqueo/resumen-admin';

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `arqueosApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchArqueosAdmin(
  query: ArqueosListQuery,
): Promise<ArqueosListResponse> {
  const params = new URLSearchParams();
  if (query.uuid_sucursal) {
    params.set('uuid_sucursal', query.uuid_sucursal);
  }
  if (query.fecha_desde) {
    params.set('fecha_desde', query.fecha_desde);
  }
  if (query.fecha_hasta) {
    params.set('fecha_hasta', query.fecha_hasta);
  }
  if (query.uuid_tipo_arqueo) {
    params.set('uuid_tipo_arqueo', query.uuid_tipo_arqueo);
  }
  params.set('limit', String(query.limit));
  if (query.cursor) {
    params.set('cursor', query.cursor);
  }
  const url = `${LIST_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return arqueosListResponseSchema.parse(raw);
}

export async function fetchArqueoDiferencias(
  uuidArqueo: string,
): Promise<DiferenciasRead> {
  const url = `${DIFERENCIAS_PATH_FRAGMENT}/${uuidArqueo}/diferencias`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return diferenciasReadSchema.parse(raw);
}

/**
 * ``fetchResumenAdmin`` -- HU-F18.3 admin cross-branch resumen por día.
 *
 * Calls ``GET /api/v1/caja/arqueo/resumen-admin?fecha=YYYY-MM-DD``
 * (admin- issuer + audit_read permission; the path is mounted on
 * the ``caja_arqueo`` admin_router, hence the ``/caja/`` prefix that
 * the parent router already carries). The operator's
 * ``/caja/arqueo/resumen`` keeps working unchanged (per-branch,
 * operador- issuer).
 */
export async function fetchResumenAdmin(
  fecha: string,
): Promise<ArqueoResumenAdminRead> {
  const params = new URLSearchParams({ fecha });
  const url = `${ADMIN_RESUMEN_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return arqueoResumenAdminReadSchema.parse(raw);
}