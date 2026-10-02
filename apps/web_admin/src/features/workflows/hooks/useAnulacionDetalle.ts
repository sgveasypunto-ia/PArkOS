/**
 * `useAnulacionDetalle` -- SWR-backed single-item fetch for
 * `<AnulacionDetalle />`. Mirrors `alertas/hooks/useAlertaDetalle.ts`'s
 * shape (isLoading/error/mutate) for a direct-navigation / deep-link /
 * refresh-safe detail read, independent of whatever the list screen
 * already had in memory.
 */
import useSWR from 'swr';

import { fetchAnulacion } from '../api/anulacionesApi';
import type { AnulacionRead } from '../api/anulacionesSchema';

export interface UseAnulacionDetalleReturn {
  anulacion: AnulacionRead | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<AnulacionRead | undefined>;
  /** Locally patches the cached row without a round-trip (post-transición). */
  setAnulacion: (updated: AnulacionRead) => void;
}

export function useAnulacionDetalle(uuid: string | null): UseAnulacionDetalleReturn {
  const { data, error, isLoading, mutate } = useSWR<AnulacionRead, Error>(
    uuid ? `anulacion-detalle:${uuid}` : null,
    () => fetchAnulacion(uuid as string),
    { revalidateOnFocus: false },
  );

  return {
    anulacion: data,
    isLoading,
    error,
    refresh: async () => mutate(),
    setAnulacion: (updated) => {
      void mutate(updated, { revalidate: false });
    },
  };
}
