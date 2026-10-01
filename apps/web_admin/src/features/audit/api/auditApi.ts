/**
 * `auditApi.ts` — HTTP client for the IT-12 audit-log dashboard.
 *
 * Endpoint consumed (cloud-only):
 *   - GET /api/v1/admin/audit/log?uuid_sucursal=...&limit=...&cursor=...
 *
 * Returns ``{ items: AuditLogItem[], next_cursor: string | null }``
 * (mirror of backend ``schemas/log_transaccional.py``).
 *
 * Why parkosFetchRaw (not SWR inside this file): the dashboard owns
 * SWR caching via the `useAuditLog` hook. Keeping the HTTP client a
 * pure fetch helper lets the hook own the cache key, the
 * revalidation policy, and the "load more" cursor merge logic in
 * one place.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import { auditLogListResponseSchema, type AuditQuery } from './auditSchema';

const PATH = '/api/v1/admin/audit/log';

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `auditApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchAuditLog(query: AuditQuery): Promise<{
  items: ReturnType<typeof auditLogListResponseSchema.parse>['items'];
  next_cursor: string | null;
}> {
  const params = new URLSearchParams();
  if (query.uuid_sucursal) {
    params.set('uuid_sucursal', query.uuid_sucursal);
  }
  if (query.tabla_afectada) {
    params.set('tabla_afectada', query.tabla_afectada);
  }
  params.set('limit', String(query.limit));
  if (query.cursor !== undefined && query.cursor !== null) {
    params.set('cursor', query.cursor);
  }
  const url = `${PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return auditLogListResponseSchema.parse(raw);
}
