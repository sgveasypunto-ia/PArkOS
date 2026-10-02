/**
 * `useLogTransaccional` -- SWR-backed hook for the HU-F20.4 admin
 * "bitácora" cross-branch listing. Mirrors
 * `arqueos/hooks/useArqueosAdmin.ts` / `alertas/hooks/useAlertasAdmin.ts`
 * (cursor pagination via `loadMore`, re-fetch on any filter change).
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchLogTransaccional } from '../api/auditoriaApi';
import type {
  AuditLogItem,
  AuditLogListResponse,
  LogTransaccionalListQuery,
} from '../api/auditoriaSchema';

export interface UseLogTransaccionalReturn {
  items: AuditLogItem[];
  isLoading: boolean;
  error: Error | undefined;
  nextCursor: string | null;
  loadMore: () => Promise<void>;
  refresh: () => Promise<AuditLogListResponse | undefined>;
  hasMore: boolean;
}

export interface UseLogTransaccionalOptions {
  /** Optional suffix to namespace the SWR cache key per test. */
  swrSalt?: string;
}

function buildKey(query: LogTransaccionalListQuery, salt: string | undefined): string {
  const parts: string[] = [];
  if (query.tabla) parts.push(`tabla=${query.tabla}`);
  if (query.uuid_registro) parts.push(`reg=${query.uuid_registro}`);
  if (query.uuid_sucursal) parts.push(`suc=${query.uuid_sucursal}`);
  if (query.uuid_usuario) parts.push(`usr=${query.uuid_usuario}`);
  if (query.desde) parts.push(`desde=${query.desde}`);
  if (query.hasta) parts.push(`hasta=${query.hasta}`);
  parts.push(`limit=${query.limit ?? 20}`);
  const suffix = salt !== undefined ? `&_=${salt}` : '';
  return `admin-log-transaccional?${parts.join('&')}${suffix}`;
}

export function useLogTransaccional(
  query: LogTransaccionalListQuery,
  options: UseLogTransaccionalOptions = {},
): UseLogTransaccionalReturn {
  const { swrSalt } = options;
  const swrKey = useMemo(
    () => buildKey(query, swrSalt),
    // Deliberately narrowed to the query's primitive fields (mirrors
    // useArqueosAdmin.ts / useAlertasAdmin.ts): depending on `query` itself
    // would recompute on every render, since callers typically pass a
    // fresh object literal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      query.tabla,
      query.uuid_registro,
      query.uuid_sucursal,
      query.uuid_usuario,
      query.desde,
      query.hasta,
      query.limit,
      swrSalt,
    ],
  );

  const fetcher = async (): Promise<AuditLogListResponse> => fetchLogTransaccional(query);

  const { data, error, isLoading, mutate } = useSWR<AuditLogListResponse, Error>(swrKey, fetcher, {
    revalidateOnFocus: false,
  });

  const items: AuditLogItem[] = data?.items ?? [];
  const nextCursor = data?.next_cursor ?? null;
  const hasMore = nextCursor !== null;

  const loadMore = async (): Promise<void> => {
    if (!hasMore) return;
    const nextQuery: LogTransaccionalListQuery = { ...query, cursor: nextCursor ?? undefined };
    try {
      const next = await fetchLogTransaccional(nextQuery);
      await mutate(
        (prev) =>
          prev === undefined
            ? next
            : { items: [...prev.items, ...next.items], next_cursor: next.next_cursor },
        { revalidate: false },
      );
    } catch (err) {
      // Best-effort, mirrors useArqueosAdmin.loadMore / useAlertasAdmin.loadMore:
      // the caller can `refresh()` to retry; we don't throw into the render path.
      console.error('useLogTransaccional.loadMore failed:', err);
    }
  };

  return {
    items,
    isLoading,
    error,
    nextCursor,
    loadMore,
    refresh: async () => mutate(),
    hasMore,
  };
}
