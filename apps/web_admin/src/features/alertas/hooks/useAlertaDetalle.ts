/**
 * `useAlertaDetalle` -- SWR-backed single-item fetch for
 * `<AlertaDetalle />`. Mirrors `arqueos/hooks/useArqueoDetalle.ts`'s
 * shape (isLoading/error/mutate) for a direct-navigation / deep-link /
 * refresh-safe detail read, independent of whatever the list screen
 * already had in memory.
 */
import useSWR from 'swr';

import { fetchAlerta } from '../api/alertasApi';
import type { AlertaDetailRead } from '../api/alertasSchema';

export interface UseAlertaDetalleReturn {
  alerta: AlertaDetailRead | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<AlertaDetailRead | undefined>;
  /** Locally patches the cached row without a round-trip (post-descartar). */
  setAlerta: (updated: AlertaDetailRead) => void;
}

export function useAlertaDetalle(uuid: string | null): UseAlertaDetalleReturn {
  const { data, error, isLoading, mutate } = useSWR<AlertaDetailRead, Error>(
    uuid ? `alerta-detalle:${uuid}` : null,
    () => fetchAlerta(uuid as string),
    { revalidateOnFocus: false },
  );

  return {
    alerta: data,
    isLoading,
    error,
    refresh: async () => mutate(),
    setAlerta: (updated) => {
      void mutate(updated, { revalidate: false });
    },
  };
}
