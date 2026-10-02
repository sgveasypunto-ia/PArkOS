/**
 * `useBuscarLogTransaccional` -- debounced (300ms) typeahead hook for
 * `GET /admin/log-transaccional/buscar` (HU-F20.4, <=10 results, no
 * cursor). Plain `useEffect` + `setTimeout` + cancellation-flag, same
 * "request-on-change" shape `sync/pages/SyncLog.tsx` already uses for its
 * filter-driven fetch -- no SWR here since there is no cache key worth
 * sharing across callers for a free-text, per-keystroke search.
 */
import { useEffect, useState } from 'react';

import { buscarLogTransaccional } from '../api/auditoriaApi';
import type { BuscarPrefijoItem } from '../api/auditoriaSchema';

const DEFAULT_DEBOUNCE_MS = 300;
const RESULT_LIMIT = 10;

export interface UseBuscarLogTransaccionalReturn {
  prefijo: string;
  setPrefijo: (value: string) => void;
  items: BuscarPrefijoItem[];
  isLoading: boolean;
  error: Error | null;
}

export function useBuscarLogTransaccional(
  debounceMs: number = DEFAULT_DEBOUNCE_MS,
): UseBuscarLogTransaccionalReturn {
  const [prefijo, setPrefijo] = useState('');
  const [items, setItems] = useState<BuscarPrefijoItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const trimmed = prefijo.trim();
    if (trimmed.length === 0) {
      setItems([]);
      setError(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    const handle = setTimeout(() => {
      buscarLogTransaccional({ prefijo: trimmed, limit: RESULT_LIMIT })
        .then((resp) => {
          if (cancelled) return;
          setItems(resp.items);
          setError(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setError(err instanceof Error ? err : new Error(String(err)));
          setItems([]);
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    }, debounceMs);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [prefijo, debounceMs]);

  return { prefijo, setPrefijo, items, isLoading, error };
}
