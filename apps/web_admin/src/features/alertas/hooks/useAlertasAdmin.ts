/**
 * `useAlertasAdmin` -- SWR-backed hook for the HU-F19.5 admin "bandeja
 * de alertas" listing. Mirrors `arqueos/hooks/useArqueosAdmin.ts`
 * (cursor pagination via `loadMore`, re-fetch on any filter change).
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchAlertas } from '../api/alertasApi';
import type { AlertaRead, AlertasListQuery, AlertasListResponse } from '../api/alertasSchema';

export interface UseAlertasAdminReturn {
  items: AlertaRead[];
  isLoading: boolean;
  error: Error | undefined;
  nextCursor: string | null;
  loadMore: () => Promise<void>;
  refresh: () => Promise<AlertasListResponse | undefined>;
  hasMore: boolean;
}

export interface UseAlertasAdminOptions {
  /** Optional suffix to namespace the SWR cache key per test. */
  swrSalt?: string;
}

function buildKey(query: AlertasListQuery, salt: string | undefined): string {
  const parts: string[] = [];
  if (query.uuid_sucursal) parts.push(`suc=${query.uuid_sucursal}`);
  if (query.tipo_alerta) parts.push(`tipo=${query.tipo_alerta}`);
  if (query.estado) parts.push(`estado=${query.estado}`);
  if (query.severidad) parts.push(`sev=${query.severidad}`);
  if (query.desde) parts.push(`desde=${query.desde}`);
  if (query.hasta) parts.push(`hasta=${query.hasta}`);
  parts.push(`limit=${query.limit}`);
  const suffix = salt !== undefined ? `&_=${salt}` : '';
  return `admin-alertas?${parts.join('&')}${suffix}`;
}

export function useAlertasAdmin(
  query: AlertasListQuery,
  options: UseAlertasAdminOptions = {},
): UseAlertasAdminReturn {
  const { swrSalt } = options;
  const swrKey = useMemo(
    () => buildKey(query, swrSalt),
    // Deliberately narrowed to the query's primitive fields (mirrors
    // useArqueosAdmin.ts): depending on `query` itself would recompute on
    // every render, since callers typically pass a fresh object literal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      query.uuid_sucursal,
      query.tipo_alerta,
      query.estado,
      query.severidad,
      query.desde,
      query.hasta,
      query.limit,
      swrSalt,
    ],
  );

  const fetcher = async (): Promise<AlertasListResponse> => fetchAlertas(query);

  const { data, error, isLoading, mutate } = useSWR<AlertasListResponse, Error>(swrKey, fetcher, {
    revalidateOnFocus: false,
  });

  const items: AlertaRead[] = data?.items ?? [];
  const nextCursor = data?.next_cursor ?? null;
  const hasMore = nextCursor !== null;

  const loadMore = async (): Promise<void> => {
    if (!hasMore) return;
    const nextQuery: AlertasListQuery = { ...query, cursor: nextCursor ?? undefined };
    try {
      const next = await fetchAlertas(nextQuery);
      await mutate(
        (prev) =>
          prev === undefined
            ? next
            : { items: [...prev.items, ...next.items], next_cursor: next.next_cursor },
        { revalidate: false },
      );
    } catch (err) {
      // Best-effort, mirrors useArqueosAdmin.loadMore: the caller can
      // `refresh()` to retry; we don't throw into the render path.
      console.error('useAlertasAdmin.loadMore failed:', err);
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
