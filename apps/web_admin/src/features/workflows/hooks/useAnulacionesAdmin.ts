/**
 * `useAnulacionesAdmin` -- SWR-backed hook for the HU-F20.3 admin
 * "anulaciones" listing. Mirrors `alertas/hooks/useAlertasAdmin.ts`
 * (cursor pagination via `loadMore`), simplified since this list has no
 * server-side filters (only `cursor`/`limit`).
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchAnulaciones } from '../api/anulacionesApi';
import type { AnulacionRead, AnulacionesListResponse } from '../api/anulacionesSchema';

const LIMIT = 20;

export interface UseAnulacionesAdminReturn {
  items: AnulacionRead[];
  isLoading: boolean;
  error: Error | undefined;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  refresh: () => Promise<AnulacionesListResponse | undefined>;
}

export interface UseAnulacionesAdminOptions {
  /** Optional suffix to namespace the SWR cache key per test. */
  swrSalt?: string;
}

export function useAnulacionesAdmin(
  options: UseAnulacionesAdminOptions = {},
): UseAnulacionesAdminReturn {
  const { swrSalt } = options;
  const swrKey = useMemo(
    () => `admin-anulaciones?limit=${LIMIT}${swrSalt !== undefined ? `&_=${swrSalt}` : ''}`,
    [swrSalt],
  );

  const { data, error, isLoading, mutate } = useSWR<AnulacionesListResponse, Error>(
    swrKey,
    () => fetchAnulaciones({ limit: LIMIT }),
    { revalidateOnFocus: false },
  );

  const items = data?.items ?? [];
  const nextCursor = data?.next_cursor ?? null;
  const hasMore = nextCursor !== null;

  const loadMore = async (): Promise<void> => {
    if (!hasMore) return;
    try {
      const next = await fetchAnulaciones({ limit: LIMIT, cursor: nextCursor ?? undefined });
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
      console.error('useAnulacionesAdmin.loadMore failed:', err);
    }
  };

  return {
    items,
    isLoading,
    error,
    hasMore,
    loadMore,
    refresh: async () => mutate(),
  };
}
