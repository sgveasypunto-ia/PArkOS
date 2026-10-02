/**
 * `useReclamoDetalle` -- SWR-backed single-item fetch for
 * `<ReclamoDetalle />`. Mirrors `useAnulacionDetalle.ts` 1:1.
 */
import useSWR from 'swr';

import { fetchReclamo } from '../api/reclamosApi';
import type { ReclamoRead } from '../api/reclamosSchema';

export interface UseReclamoDetalleReturn {
  reclamo: ReclamoRead | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<ReclamoRead | undefined>;
  /** Locally patches the cached row without a round-trip (post-transición). */
  setReclamo: (updated: ReclamoRead) => void;
}

export function useReclamoDetalle(uuid: string | null): UseReclamoDetalleReturn {
  const { data, error, isLoading, mutate } = useSWR<ReclamoRead, Error>(
    uuid ? `reclamo-detalle:${uuid}` : null,
    () => fetchReclamo(uuid as string),
    { revalidateOnFocus: false },
  );

  return {
    reclamo: data,
    isLoading,
    error,
    refresh: async () => mutate(),
    setReclamo: (updated) => {
      void mutate(updated, { revalidate: false });
    },
  };
}
