/**
 * `useSyncEstado.ts` — SWR hook for the sync state strip (HU-F11.1).
 *
 * Polls `GET /api/v1/sync/estado?uuid_sucursal=X` every 30s (per
 * plan.md:2272-2299 §F11.1). Returns lag metrics so the panel can
 * render a color-coded chip.
 *
 * REQ-OPS-132 fetcher-closure — fetcher receives bare `uuid_sucursal`.
 * SWR key gate: `null` when `uuid_sucursal` is empty.
 */
import useSWR from 'swr';
import { z } from 'zod';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

export const SyncEstadoSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  lag_seg: z.number().int().nonnegative(),
  /** Pendientes en la sync_queue local. */
  pendientes: z.number().int().nonnegative(),
  ultimo_error: z.string().nullable(),
  /** 'online' | 'lagging' | 'offline' derivado server-side. */
  estado: z.enum(['online', 'lagging', 'offline']),
  ultima_sync: z.string().nullable(),
});
export type SyncEstado = z.infer<typeof SyncEstadoSchema>;

const SYNC_REFRESH_INTERVAL_MS = 30_000;

async function fetchSyncEstado(uuid_sucursal: string): Promise<SyncEstado> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `/api/v1/sync/estado?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}`,
  );
  return SyncEstadoSchema.parse(raw);
}

export function useSyncEstado(uuid_sucursal: string | null): {
  data: SyncEstado | undefined;
  error: Error | undefined;
  refresh: () => Promise<SyncEstado | undefined>;
} {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = uuid_sucursal && accessToken
    ? `/sync/estado?uuid_sucursal=${uuid_sucursal}`
    : null;

  const { data, error, mutate } = useSWR<SyncEstado>(
    key,
    () => fetchSyncEstado(uuid_sucursal as string),
    {
      refreshInterval: SYNC_REFRESH_INTERVAL_MS,
      shouldRetryOnError: (err) => {
        if (err instanceof ParkosHttpError) {
          return err.status !== 401 && err.status !== 403 && err.status !== 404;
        }
        return true;
      },
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('parkos:auth:cleared'));
          }
        }
      },
    },
  );

  return {
    data,
    error,
    refresh: async () => mutate(),
  };
}

/**
 * `useAlertas` — SWR hook for the alertas panel (F11.2). Polls
 * `GET /api/v1/workflows/alerta?uuid_sucursal=X&estado=abierta`
 * every 30s. SWR key gate on `null`.
 */
export const AlertaSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid(),
  tipo_alerta: z.string(),
  mensaje: z.string(),
  estado: z.enum(['abierta', 'cerrada']),
  uuid_alerta_padre: z.string().uuid().nullable(),
  created_at: z.string(),
});
export type Alerta = z.infer<typeof AlertaSchema>;
export const AlertaArraySchema = z.array(AlertaSchema);

async function fetchAlertas(uuid_sucursal: string): Promise<Alerta[]> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `/api/v1/workflows/alerta?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}&estado=abierta`,
  );
  return AlertaArraySchema.parse(raw);
}

export function useAlertas(uuid_sucursal: string | null): {
  data: Alerta[] | undefined;
  error: Error | undefined;
  refresh: () => Promise<Alerta[] | undefined>;
} {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = uuid_sucursal && accessToken
    ? `/workflows/alerta?uuid_sucursal=${uuid_sucursal}&estado=abierta`
    : null;

  const { data, error, mutate } = useSWR<Alerta[]>(
    key,
    () => fetchAlertas(uuid_sucursal as string),
    {
      refreshInterval: 30_000,
      shouldRetryOnError: (err) => {
        if (err instanceof ParkosHttpError) {
          return err.status !== 401 && err.status !== 403 && err.status !== 404;
        }
        return true;
      },
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('parkos:auth:cleared'));
          }
        }
      },
    },
  );

  return {
    data,
    error,
    refresh: async () => mutate(),
  };
}