/**
 * `useEnvioDianChain` -- best-effort reconstruction of an envio_dian
 * retry chain for `<DianRetryHistory />`, walking `uuid_envio_padre`
 * backwards from a known tip row.
 *
 * Why this does NOT fetch one hop at a time like
 * `alertas/hooks/useAlertaChain.ts` does (`GET /workflows/alerta/{uuid}`
 * per hop): there is no equivalent single-item read for `envio_dian`.
 * Confirmed by reading the full `dian/cloud_router.py` -- it ships
 * exactly 6 routes (`POST /factura-electronica`, `POST /envio-dian`,
 * `POST /validacion-evento`, `GET /envio-dian`, `GET /validacion-evento`,
 * `POST /revocacion-factura-webhook`), none of which is a per-uuid GET.
 * Unlike `prod.alerta` (mounted via the generic `make_router` factory,
 * which gets a single-item "read chain tip" route for free), `envio_dian`
 * is cloud-only and hand-built (REQ-X3 -- `workflows.py` must not mount
 * it), and the hand-built version only re-implements the LIST endpoint.
 *
 * Workaround: page through `GET /envio-dian?uuid_sucursal=<tip's>&limit=200`
 * (scoped to the tip's own `uuid_sucursal` -- a retry chain never crosses
 * branches), accumulating rows into a `uuid -> row` map, until the
 * current link's `uuid_envio_padre` resolves or pages are exhausted.
 * `MAX_PAGES` / `MAX_HOPS` bound the work the same defensive way
 * `useAlertaChain.ts`'s `MAX_HOPS` does (defense against an unexpected
 * cycle or a pathologically long chain).
 */
import { useEffect, useState } from 'react';

import { fetchEnvioDianList } from '../api/envioDianApi';
import type { EnvioDianRead } from '../api/envioDianSchema';

const MAX_HOPS = 50;
const MAX_PAGES = 20;
const PAGE_LIMIT = 200;

export interface UseEnvioDianChainReturn {
  /** Oldest -> newest. Empty while loading or on error. */
  chain: EnvioDianRead[];
  isLoading: boolean;
  error: Error | undefined;
}

/**
 * Pages through the listing for `uuidSucursal` (or the whole table when
 * `null`), building a `uuid -> row` map, until `targetUuid` is found or
 * `MAX_PAGES` is exhausted.
 */
async function resolveByUuid(
  targetUuid: string,
  uuidSucursal: string | null,
  known: Map<string, EnvioDianRead>,
  pagesFetchedRef: { count: number },
): Promise<EnvioDianRead | undefined> {
  const existing = known.get(targetUuid);
  if (existing) return existing;

  let cursor: string | undefined;
  while (pagesFetchedRef.count < MAX_PAGES) {
    pagesFetchedRef.count += 1;
    const page = await fetchEnvioDianList({
      uuid_sucursal: uuidSucursal ?? undefined,
      // The listing shows only the last row per document by default; the
      // history needs every row of the chain.
      solo_tip: false,
      limit: PAGE_LIMIT,
      cursor,
    });
    for (const row of page.items) known.set(row.uuid, row);

    const found = known.get(targetUuid);
    if (found) return found;
    if (page.next_cursor === null) return undefined;
    cursor = page.next_cursor;
  }
  return undefined;
}

export function useEnvioDianChain(tip: EnvioDianRead | null): UseEnvioDianChainReturn {
  const [chain, setChain] = useState<EnvioDianRead[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    if (tip === null) {
      setChain([]);
      setError(undefined);
      return;
    }

    async function walk(): Promise<void> {
      setIsLoading(true);
      setError(undefined);
      const collected: EnvioDianRead[] = [tip as EnvioDianRead];
      const known = new Map<string, EnvioDianRead>([[(tip as EnvioDianRead).uuid, tip as EnvioDianRead]]);
      const pagesFetchedRef = { count: 0 };
      try {
        let current = tip as EnvioDianRead;
        let hops = 0;
        while (current.uuid_envio_padre !== null && hops < MAX_HOPS) {
          const parent = await resolveByUuid(
            current.uuid_envio_padre,
            current.uuid_sucursal,
            known,
            pagesFetchedRef,
          );
          if (!parent) break; // exhausted pagination without finding the parent
          collected.push(parent);
          current = parent;
          hops += 1;
        }
        if (!cancelled) setChain(collected.reverse());
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err : new Error('Error desconocido'));
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void walk();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tip?.uuid]);

  return { chain, isLoading, error };
}
