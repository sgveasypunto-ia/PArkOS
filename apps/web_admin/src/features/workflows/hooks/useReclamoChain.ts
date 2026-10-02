/**
 * `useReclamoChain` -- best-effort reconstruction of a reclamo's full
 * transition history for `<ReclamoDetalle />` / `<WorkflowChain />`.
 * Mirrors `useAnulacionChain.ts` 1:1, substituting `uuid_reclamo_padre`
 * for `uuid_anulacion_padre`.
 */
import { useEffect, useState } from 'react';

import { fetchReclamo } from '../api/reclamosApi';
import type { ReclamoRead } from '../api/reclamosSchema';

const MAX_HOPS = 50;

export interface UseReclamoChainReturn {
  /** Oldest -> newest. Empty while loading or on error. */
  chain: ReclamoRead[];
  isLoading: boolean;
  error: Error | undefined;
}

export function useReclamoChain(uuid: string | null): UseReclamoChainReturn {
  const [chain, setChain] = useState<ReclamoRead[]>([]);
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
      const collected: ReclamoRead[] = [];
      try {
        let cursor: string | null = uuid;
        let hops = 0;
        while (cursor !== null && hops < MAX_HOPS) {
          // Sequential by design: each hop's parent uuid is only known
          // after the previous fetch resolves.
          const row = await fetchReclamo(cursor);
          collected.push(row);
          cursor = row.uuid_reclamo_padre;
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
