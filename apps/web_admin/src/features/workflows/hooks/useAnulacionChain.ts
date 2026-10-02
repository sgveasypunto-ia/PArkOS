/**
 * `useAnulacionChain` -- best-effort reconstruction of an anulación's
 * full transition history for `<AnulacionDetalle />` / `<WorkflowChain />`.
 * Mirrors `alertas/hooks/useAlertaChain.ts` 1:1, substituting
 * `uuid_anulacion_padre` for `uuid_alerta_padre`.
 *
 * Why NOT `GET /workflows/anulaciones/{uuid}/history`: that generic
 * factory endpoint filters `WHERE uuid = :uuid`, which only ever matches
 * ONE row for an insert-new-row-per-transition chain like
 * `prod.anulacion` (each transition gets a BRAND NEW uuid, linked
 * backwards via `uuid_anulacion_padre`). This hook walks the chain
 * client-side instead: fetch the known uuid, follow
 * `uuid_anulacion_padre` backwards one `GET /workflows/anulaciones/{uuid}`
 * at a time, stop at the root (`uuid_anulacion_padre === null`) or at
 * `MAX_HOPS` (defense against an unexpected cycle).
 */
import { useEffect, useState } from 'react';

import { fetchAnulacion } from '../api/anulacionesApi';
import type { AnulacionRead } from '../api/anulacionesSchema';

const MAX_HOPS = 50;

export interface UseAnulacionChainReturn {
  /** Oldest -> newest. Empty while loading or on error. */
  chain: AnulacionRead[];
  isLoading: boolean;
  error: Error | undefined;
}

export function useAnulacionChain(uuid: string | null): UseAnulacionChainReturn {
  const [chain, setChain] = useState<AnulacionRead[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    if (uuid === null) {
      setChain([]);
      setError(undefined);
      return;
    }

    async function walk(): Promise<void> {
      setIsLoading(true);
      setError(undefined);
      const collected: AnulacionRead[] = [];
      try {
        let cursor: string | null = uuid;
        let hops = 0;
        while (cursor !== null && hops < MAX_HOPS) {
          // Sequential by design: each hop's parent uuid is only known
          // after the previous fetch resolves.
          const row = await fetchAnulacion(cursor);
          collected.push(row);
          cursor = row.uuid_anulacion_padre;
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
  }, [uuid]);

  return { chain, isLoading, error };
}
