/**
 * `useClientes.ts` — SWR hook for `<ClientesList />` (HU-F20.1).
 *
 * The list endpoint only accepts `cursor`/`limit` (max 200, see
 * `clientesApi.ts`'s module docblock) and clientes can outgrow a single
 * page, so this hook owns a "Cargar más" accumulation: the first page
 * is SWR-cached (`KEY`), every subsequent page is fetched directly and
 * appended to local state. A revalidation of the first page (`refresh`)
 * resets the accumulated extra pages so stale rows never linger mixed
 * in with a freshly revalidated first page.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';

import { listClientes, type Cliente } from '../api/clientesApi';

const KEY = '/api/v1/clientes/clientes';
const PAGE_LIMIT = 200;

export interface UseClientesReturn {
  clientes: Cliente[];
  isLoading: boolean;
  error: Error | undefined;
  hasMore: boolean;
  isLoadingMore: boolean;
  loadMore: () => Promise<void>;
  refresh: () => Promise<void>;
}

export function useClientes(): UseClientesReturn {
  const { data, error, isLoading, mutate } = useSWR(
    KEY,
    () => listClientes({ limit: PAGE_LIMIT }),
    { revalidateOnFocus: false },
  );

  const [morePages, setMorePages] = useState<Cliente[][]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [cursorInitialized, setCursorInitialized] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  useEffect(() => {
    if (data !== undefined) {
      setNextCursor(data.next_cursor);
      setCursorInitialized(true);
      setMorePages([]);
    }
  }, [data]);

  const loadMore = useCallback(async () => {
    if (nextCursor === null) return;
    setIsLoadingMore(true);
    try {
      const page = await listClientes({ cursor: nextCursor, limit: PAGE_LIMIT });
      setMorePages((prev) => [...prev, page.items]);
      setNextCursor(page.next_cursor);
    } finally {
      setIsLoadingMore(false);
    }
  }, [nextCursor]);

  const clientes = useMemo(
    () => [...(data?.items ?? []), ...morePages.flat()],
    [data, morePages],
  );

  return {
    clientes,
    isLoading,
    error,
    hasMore: cursorInitialized && nextCursor !== null,
    isLoadingMore,
    loadMore,
    refresh: async () => {
      await mutate();
    },
  };
}
