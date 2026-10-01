/**
 * ``useArqueosAdmin`` -- SWR-backed hook for the F18.2 admin
 * arqueo listing.
 *
 * The hook re-fetches whenever ANY of the four filter arguments changes
 * (SWR key includes all of them). Cursor pagination is handled by the
 * ``loadMore`` helper, which captures the previous SWR data and appends
 * the next page's items in a fresh cache key suffix so SWR's deduping
 * is preserved.
 *
 * Cache isolation across tests: tests that need a clean fetch pass a
 * unique ``swrSalt`` prop to avoid SWR's default provider serving a
 * stale payload from a previous case (same pattern as
 * ``EmpresaBitacoraTab``'s ``swrKeySuffix``).
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchArqueosAdmin } from '../api/arqueosApi';
import type {
  ArqueosListQuery,
  ArqueosListResponse,
  ArqueoRead,
} from '../api/arqueosSchema';

export interface UseArqueosAdminReturn {
  items: ArqueoRead[];
  isLoading: boolean;
  error: Error | undefined;
  nextCursor: string | null;
  loadMore: () => Promise<void>;
  refresh: () => Promise<ArqueosListResponse | undefined>;
  hasMore: boolean;
}

export interface UseArqueosAdminOptions {
  /** Optional suffix to namespace the SWR cache key per test. */
  swrSalt?: string;
}

function buildKey(query: ArqueosListQuery, salt: string | undefined): string | null {
  // No-filters-without-salt-active is weird -- when there are zero
  // filters and the BE will return the most-recent N, we still want to
  // fetch. SWR only runs the fetcher when the key is a string; null
  // pauses. We always return a string here so the list fetches on mount.
  const base = `admin-arqueos`;
  const parts: string[] = [];
  if (query.uuid_sucursal) parts.push(`suc=${query.uuid_sucursal}`);
  if (query.fecha_desde) parts.push(`desde=${query.fecha_desde}`);
  if (query.fecha_hasta) parts.push(`hasta=${query.fecha_hasta}`);
  if (query.uuid_tipo_arqueo) parts.push(`tipo=${query.uuid_tipo_arqueo}`);
  parts.push(`limit=${query.limit}`);
  const suffix = salt !== undefined ? `&_=${salt}` : '';
  return `${base}?${parts.join('&')}${suffix}`;
}

export function useArqueosAdmin(
  query: ArqueosListQuery,
  options: UseArqueosAdminOptions = {},
): UseArqueosAdminReturn {
  const { swrSalt } = options;
  const swrKey = useMemo(() => buildKey(query, swrSalt), [
    query.uuid_sucursal,
    query.fecha_desde,
    query.fecha_hasta,
    query.uuid_tipo_arqueo,
    query.limit,
    swrSalt,
  ]);

  const fetcher = async (): Promise<ArqueosListResponse> => fetchArqueosAdmin(query);

  const { data, error, isLoading, mutate } = useSWR<
    ArqueosListResponse,
    Error
  >(swrKey, fetcher, {
    revalidateOnFocus: false,
  });

  const items: ArqueoRead[] = data?.items ?? [];
  const nextCursor = data?.next_cursor ?? null;
  const hasMore = nextCursor !== null;

  // ``loadMore`` re-fetches with the same filters plus the cursor and
  // appends the new page's items to the existing SWR cache. The merge
  // keeps the cache key stable so SWR's deduping is preserved; only the
  // appended items are new.
  const loadMore = async (): Promise<void> => {
    if (!hasMore) return;
    const nextQuery: ArqueosListQuery = { ...query, cursor: nextCursor ?? undefined };
    try {
      const next = await fetchArqueosAdmin(nextQuery);
      await mutate(
        (prev) =>
          prev === undefined
            ? next
            : {
                items: [...prev.items, ...next.items],
                next_cursor: next.next_cursor,
              },
        { revalidate: false },
      );
    } catch (err) {
      // Surface on the next render via SWR's own error path; the hook
      // caller can ``refresh()`` to retry. We don't ``throw`` here --
      // loadMore is best-effort.
      // eslint-disable-next-line no-console
      console.error('useArqueosAdmin.loadMore failed:', err);
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