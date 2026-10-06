/**
 * `useUrlFilters` — list filters kept in the querystring so that a detail
 * screen's "Volver" (history back) lands on the list with the same filters
 * (PT-1). Only the keys of `empty` are read/written; empty values are omitted
 * from the URL. Updates use `replace` so typing in a filter does not pile up
 * history entries.
 *
 * `seedKeys`: extra query params that only seed the initial value (deep links
 * such as `?uuid_alerta=`); they are dropped from the URL on the first update.
 * `sanitize`: optional hook to coerce hand-edited/stale URL values.
 */
import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

export function useUrlFilters<T extends object>(
  empty: T,
  options: {
    seed?: (params: URLSearchParams) => Partial<T> | null;
    seedKeys?: readonly string[];
    sanitize?: (value: T) => T;
  } = {},
): [T, (next: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const { seed, seedKeys = [], sanitize } = options;
  const emptyRecord = empty as Record<string, string>;

  const value = useMemo(() => {
    const seeded = (seed?.(searchParams) ?? null) as Record<string, string> | null;
    const out: Record<string, string> = {};
    for (const key of Object.keys(emptyRecord)) {
      out[key] = searchParams.get(key) ?? seeded?.[key] ?? emptyRecord[key] ?? '';
    }
    const typed = out as unknown as T;
    return sanitize ? sanitize(typed) : typed;
    // `empty`/`seed`/`sanitize` are module-level constants in callers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const setValue = useCallback(
    (next: T) => {
      const nextRecord = next as Record<string, string>;
      const params = new URLSearchParams(searchParams);
      for (const key of seedKeys) params.delete(key);
      for (const key of Object.keys(emptyRecord)) {
        const v = nextRecord[key] ?? '';
        if (v === '') params.delete(key);
        else params.set(key, v);
      }
      setSearchParams(params, { replace: true });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [searchParams, setSearchParams],
  );

  return [value, setValue];
}
