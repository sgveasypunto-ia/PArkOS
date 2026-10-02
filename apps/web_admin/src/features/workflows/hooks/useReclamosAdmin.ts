/**
 * `useReclamosAdmin` -- SWR-backed hook for the HU-F20.3 admin
 * "reclamos" listing. Mirrors `useAnulacionesAdmin.ts` 1:1.
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchReclamos } from '../api/reclamosApi';
import type { ReclamoRead, ReclamosListResponse } from '../api/reclamosSchema';

const LIMIT = 20;

export interface UseReclamosAdminReturn {
  items: ReclamoRead[];
  isLoading: boolean;
  error: Error | undefined;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  refresh: () => Promise<ReclamosListResponse | undefined>;
}

export interface UseReclamosAdminOptions {
  /** Optional suffix to namespace the SWR cache key per test. */
  swrSalt?: string;
}

export function useReclamosAdmin(options: UseReclamosAdminOptions = {}): UseReclamosAdminReturn {
  const { swrSalt } = options;
  const swrKey = useMemo(
    () => `admin-reclamos?limit=${LIMIT}${swrSalt !== undefined ? `&_=${swrSalt}` : ''}`,
    [swrSalt],
  );

  const { data, error, isLoading, mutate } = useSWR<ReclamosListResponse, Error>(
    swrKey,
    () => fetchReclamos({ limit: LIMIT }),
    { revalidateOnFocus: false },
  );

  const items = data?.items ?? [];
  const nextCursor = data?.next_cursor ?? null;
  const hasMore = nextCursor !== null;

  const loadMore = async (): Promise<void> => {
    if (!hasMore) return;
    try {
      const next = await fetchReclamos({ limit: LIMIT, cursor: nextCursor ?? undefined });
      await mutate(
        (prev) =>
          prev === undefined
            ? next
            : { items: [...prev.items, ...next.items], next_cursor: next.next_cursor },
        { revalidate: false },
      );
    } catch (err) {
      console.error('useReclamosAdmin.loadMore failed:', err);
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
