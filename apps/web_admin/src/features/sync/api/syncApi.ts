/**
 * `syncApi.ts` — HTTP client for the HU-F19.2 sync dashboard (web_admin),
 * consuming the 3 real HU-F19.1 endpoints (already merged to `dev`,
 * `backend/.../api/v1/admin_views.py`):
 *
 *   - GET /api/v1/admin/sync/log?uuid_sucursal=&desde=&hasta=&cursor=&limit=
 *   - GET /api/v1/admin/sync/conflict?uuid_sucursal=&cursor=&limit=
 *   - GET /api/v1/admin/sync/estado
 *
 * Thin transport only, same convention as `reporteriaApi.ts` /
 * `adminUsuariosApi.ts`: build the URL, fetch, parse with Zod. SWR
 * caching lives in `hooks/useSync.ts`.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@/lib/fetch';

import {
  syncLogListResponseSchema,
  syncConflictListResponseSchema,
  syncEstadoAgregadoResponseSchema,
  type SyncLogListResponse,
  type SyncConflictListResponse,
  type SyncEstadoAgregadoResponse,
  type SyncLogQuery,
  type SyncConflictQuery,
} from './syncSchema';

const LOG_PATH = '/api/v1/admin/sync/log';
const CONFLICT_PATH = '/api/v1/admin/sync/conflict';
const ESTADO_PATH = '/api/v1/admin/sync/estado';

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `syncApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

/**
 * 400 `missing_sucursal_context` -- the actor has zero permitted
 * branches at all (distinct from `items: []`, which means the actor
 * HAS permitted branches but none are currently `vigente`). Both are
 * "no sucursales" for the dashboard's empty state (plan.md HU-F19.2:
 * "Sin sucursales sincronizando aún"), but only this one is an HTTP
 * error rather than a normal empty success response.
 */
export class SyncMissingSucursalContextError extends Error {
  constructor() {
    super('No hay sucursales permitidas para este administrador.');
    this.name = 'SyncMissingSucursalContextError';
  }
}

export async function fetchSyncLog(query: SyncLogQuery): Promise<SyncLogListResponse> {
  const params = new URLSearchParams();
  if (query.uuid_sucursal) params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.desde) params.set('desde', query.desde);
  if (query.hasta) params.set('hasta', query.hasta);
  if (query.cursor) params.set('cursor', query.cursor);
  params.set('limit', String(query.limit ?? 50));
  const url = `${LOG_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return syncLogListResponseSchema.parse(raw);
}

export async function fetchSyncConflict(
  query: SyncConflictQuery,
): Promise<SyncConflictListResponse> {
  const params = new URLSearchParams();
  if (query.uuid_sucursal) params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.cursor) params.set('cursor', query.cursor);
  params.set('limit', String(query.limit ?? 50));
  const url = `${CONFLICT_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return syncConflictListResponseSchema.parse(raw);
}

export async function fetchSyncEstado(): Promise<SyncEstadoAgregadoResponse> {
  const res = await parkosFetchRaw(ESTADO_PATH, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (res.ok) {
    return syncEstadoAgregadoResponseSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 400 && bodyText.includes('missing_sucursal_context')) {
    throw new SyncMissingSucursalContextError();
  }
  throw new Error(`syncApi: GET ${ESTADO_PATH} -> ${res.status}: ${bodyText.slice(0, 200)}`);
}
