/**
 * ``useArqueoDetalle`` -- SWR hook for the F18.2 admin arqueo detail
 * panel (the raw ``ArqueoRead`` row + the derived deltas from
 * ``/caja-sesion/arqueos/{uuid}/diferencias``).
 *
 * Two queries fire on mount:
 *   1. ``GET /api/v1/caja/arqueo/{uuid}`` for the base row (future -- the
 *      per-uuid GET handler is added in F18.2 too; for now the list
 *      response already includes the row when the detail view is opened
 *      from it). Kept as a TODO since the current F18.2 backend only
 *      ships the LIST endpoint (commit ``ca6c0a0``).
 *   2. ``GET /caja-sesion/arqueos/{uuid}/diferencias`` for the deltas.
 *      This is the only network call that fires on mount today.
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchArqueoDiferencias } from '../api/arqueosApi';
import type { DiferenciasRead } from '../api/arqueosSchema';

export interface UseArqueoDetalleReturn {
  diferencias: DiferenciasRead | null;
  isLoading: boolean;
  error: Error | undefined;
}

export interface UseArqueoDetalleOptions {
  /** Optional SWR salt for test isolation. */
  swrSalt?: string;
}

export function useArqueoDetalle(
  uuidArqueo: string | null,
  options: UseArqueoDetalleOptions = {},
): UseArqueoDetalleReturn {
  const { swrSalt } = options;
  const key = useMemo(() => {
    if (!uuidArqueo) return null;
    const base = `arqueo-detalle/${uuidArqueo}`;
    return swrSalt !== undefined ? `${base}&_=${swrSalt}` : base;
  }, [uuidArqueo, swrSalt]);

  const { data, error, isLoading } = useSWR<DiferenciasRead, Error>(
    key,
    () => fetchArqueoDiferencias(uuidArqueo as string),
    { revalidateOnFocus: false },
  );

  return { diferencias: data ?? null, isLoading, error };
}