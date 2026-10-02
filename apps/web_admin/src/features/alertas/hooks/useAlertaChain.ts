/**
 * `useAlertaChain` -- best-effort reconstruction of an alerta's full
 * transition history for `<AlertaDetalle />` / `<WorkflowChain />`.
 *
 * Why NOT `GET /workflows/alerta/{uuid}/history`: that generic factory
 * endpoint filters `WHERE uuid = :uuid`, which only ever matches ONE row
 * for an insert-new-row-per-transition chain like `prod.alerta`
 * (`workflows_alerta.py::descartar_alerta` explicitly "INSERT NEW...
 * NEVER UPDATE the tip" -- each transition gets a BRAND NEW uuid, linked
 * backwards via `uuid_alerta_padre`). This exact gap is already
 * documented elsewhere in this repo for the same class of chain
 * (`tarifas/hooks/useTarifasByKey.ts`, `tarifas/api/tarifasApi.ts`):
 * `/history` "filters by uuid and misses the close+insert fresh-UUID
 * case". Unlike tarifas, alerta has no dedicated "by-key" index
 * endpoint (yet) to work around it, so this hook walks the chain
 * client-side instead: fetch the known uuid, follow `uuid_alerta_padre`
 * backwards one `GET /workflows/alerta/{uuid}` at a time, stop at the
 * root (`uuid_alerta_padre === null`) or at `MAX_HOPS` (defense against
 * an unexpected cycle).
 *
 * KNOWN GAP (BE-side, out of scope for this FE-only slice): `AlertaRead`
 * does not expose `datos_nuevos`, so the `observaciones` text a
 * "descartar" transition recorded is NOT retrievable from this walk --
 * only `estado` / `timestamp_evento` / `uuid_usuario` are. Each mapped
 * `WorkflowTransition` below carries `observaciones: null` for every
 * walked row; `<AlertaDetalle />` still shows the CURRENT discard's own
 * observaciones (it has them locally, from the just-submitted form).
 */
import { useEffect, useState } from 'react';

import { fetchAlerta } from '../api/alertasApi';
import type { AlertaDetailRead } from '../api/alertasSchema';

const MAX_HOPS = 50;

export interface UseAlertaChainReturn {
  /** Oldest -> newest. Empty while loading or on error. */
  chain: AlertaDetailRead[];
  isLoading: boolean;
  error: Error | undefined;
}

export function useAlertaChain(uuid: string | null): UseAlertaChainReturn {
  const [chain, setChain] = useState<AlertaDetailRead[]>([]);
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
      const collected: AlertaDetailRead[] = [];
      try {
        let cursor: string | null = uuid;
        let hops = 0;
        while (cursor !== null && hops < MAX_HOPS) {
          // Sequential by design: each hop's parent uuid is only known
          // after the previous fetch resolves.
          const row = await fetchAlerta(cursor);
          collected.push(row);
          cursor = row.uuid_alerta_padre;
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
