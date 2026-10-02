/**
 * `useEnvioDianAdmin` -- SWR-backed hook for the HU-F20.5 "monitor de
 * envíos DIAN" listing. Mirrors `alertas/hooks/useAlertasAdmin.ts`
 * (cursor pagination via `loadMore`, re-fetch on any filter change).
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchEnvioDianList } from '../api/envioDianApi';
import type { EnvioDianListQuery, EnvioDianRead, EnvioDianReadList } from '../api/envioDianSchema';

export interface UseEnvioDianAdminReturn {
  items: EnvioDianRead[];
  isLoading: boolean;
  error: Error | undefined;
  nextCursor: string | null;
  loadMore: () => Promise<void>;
  refresh: () => Promise<EnvioDianReadList | undefined>;
  hasMore: boolean;
}

export interface UseEnvioDianAdminOptions {
  /** Optional suffix to namespace the SWR cache key per test. */
  swrSalt?: string;
}

function buildKey(query: EnvioDianListQuery, salt: string | undefined): string {
  const parts: string[] = [];
  if (query.uuid_sucursal) parts.push(`suc=${query.uuid_sucursal}`);
  if (query.estado) parts.push(`estado=${query.estado}`);
  parts.push(`limit=${query.limit}`);
  const suffix = salt !== undefined ? `&_=${salt}` : '';
  return `admin-envio-dian?${parts.join('&')}${suffix}`;
}

export function useEnvioDianAdmin(
  query: EnvioDianListQuery,
  options: UseEnvioDianAdminOptions = {},
): UseEnvioDianAdminReturn {
  const { swrSalt } = options;
  const swrKey = useMemo(
    () => buildKey(query, swrSalt),
    // Deliberately narrowed to the query's primitive fields (mirrors
    // useAlertasAdmin.ts): depending on `query` itself would recompute on
    // every render, since callers typically pass a fresh object literal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [query.uuid_sucursal, query.estado, query.limit, swrSalt],
  );

  const fetcher = async (): Promise<EnvioDianReadList> => fetchEnvioDianList(query);

  const { data, error, isLoading, mutate } = useSWR<EnvioDianReadList, Error>(swrKey, fetcher, {
    revalidateOnFocus: false,
  });

  const items: EnvioDianRead[] = data?.items ?? [];
  const nextCursor = data?.next_cursor ?? null;
  const hasMore = nextCursor !== null;

  const loadMore = async (): Promise<void> => {
    if (!hasMore) return;
    const nextQuery: EnvioDianListQuery = { ...query, cursor: nextCursor ?? undefined };
    try {
      const next = await fetchEnvioDianList(nextQuery);
      await mutate(
        (prev) =>
          prev === undefined
            ? next
            : { items: [...prev.items, ...next.items], next_cursor: next.next_cursor },
        { revalidate: false },
      );
    } catch (err) {
      // Best-effort, mirrors useAlertasAdmin.loadMore: the caller can
      // `refresh()` to retry; we don't throw into the render path.
      console.error('useEnvioDianAdmin.loadMore failed:', err);
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
