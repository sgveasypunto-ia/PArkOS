/**
 * `useValidacionEventos` — SWR-backed hook for the HU-F19.6 "bandeja de
 * validación de eventos" tab. Mirrors `alertas/hooks/useAlertasAdmin.ts`
 * (cursor pagination via `loadMore`, re-fetch on any filter change).
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchValidacionEventos } from '../api/validacionEventoApi';
import type {
  ValidacionEventoListQuery,
  ValidacionEventoListResponse,
  ValidacionEventoRead,
} from '../api/validacionEventoSchema';

export interface UseValidacionEventosReturn {
  items: ValidacionEventoRead[];
  isLoading: boolean;
  error: Error | undefined;
  nextCursor: string | null;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  refresh: () => Promise<ValidacionEventoListResponse | undefined>;
}

export interface UseValidacionEventosOptions {
  /** Optional suffix to namespace the SWR cache key per test. */
  swrSalt?: string;
}

function buildKey(query: ValidacionEventoListQuery, salt: string | undefined): string {
  const parts: string[] = [];
  if (query.uuid_sucursal) parts.push(`suc=${query.uuid_sucursal}`);
  if (query.estado) parts.push(`estado=${query.estado}`);
  parts.push(`limit=${query.limit ?? 50}`);
  const suffix = salt !== undefined ? `&_=${salt}` : '';
  return `validacion-eventos?${parts.join('&')}${suffix}`;
}

export function useValidacionEventos(
  query: ValidacionEventoListQuery,
  options: UseValidacionEventosOptions = {},
): UseValidacionEventosReturn {
  const { swrSalt } = options;
  const swrKey = useMemo(
    () => buildKey(query, swrSalt),
    // Deliberately narrowed to the query's primitive fields (mirrors
    // useAlertasAdmin.ts): depending on `query` itself would recompute on
    // every render, since callers typically pass a fresh object literal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [query.uuid_sucursal, query.estado, query.limit, swrSalt],
  );

  const fetcher = async (): Promise<ValidacionEventoListResponse> =>
    fetchValidacionEventos(query);

  const { data, error, isLoading, mutate } = useSWR<ValidacionEventoListResponse, Error>(
    swrKey,
    fetcher,
    { revalidateOnFocus: false },
  );

  const items = data?.items ?? [];
  const nextCursor = data?.next_cursor ?? null;
  const hasMore = nextCursor !== null;

  const loadMore = async (): Promise<void> => {
    if (!hasMore) return;
    const nextQuery: ValidacionEventoListQuery = { ...query, cursor: nextCursor ?? undefined };
    try {
      const next = await fetchValidacionEventos(nextQuery);
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
      console.error('useValidacionEventos.loadMore failed:', err);
    }
  };

  return {
    items,
    isLoading,
    error,
    nextCursor,
    hasMore,
    loadMore,
    refresh: async () => mutate(),
  };
}
