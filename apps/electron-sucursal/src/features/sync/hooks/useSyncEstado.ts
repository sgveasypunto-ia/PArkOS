/**
 * `useSyncEstado.ts` — SWR hook for the sync state strip (HU-F11.1).
 *
 * Polls `GET /api/v1/sync/estado?uuid_sucursal=X` every 30s (per
 * plan.md:2272-2299 §F11.1). Returns lag metrics so the panel can
 * render a color-coded chip.
 *
 * REQ-OPS-132 fetcher-closure — fetcher receives bare `uuid_sucursal`.
 * SWR key gate: `null` when `uuid_sucursal` is empty.
 *
 * REQ-OPS-170 (HU-F11.1, AD-1) — Zod schema MUST match backend
 * `SyncEstadoRead` (`backend/packages/parkos_core/src/parkos_core/schemas/sync_infra.py:399`)
 * exactly: `uuid_sucursal`, `ultima_sync_at`, `lag_seg`, `pendientes`.
 * `estado` is derived on the frontend from `(lag_seg, pendientes,
 * ultima_sync_at)` per REQ-OPS-171 — never received from the backend.
 * Drift anchor DA-F11.1-7 (GATING) closed by this realignment.
 */
import useSWR from 'swr';
import { z } from 'zod';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

export const SyncEstadoSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  /** ISO 8601 timestamp of the last successful sync, or null when the
   *  branch has never synced (REQ-OPS-171 never_synced badge). */
  ultima_sync_at: z.string().nullable(),
  /** Seconds since the last successful sync, or null when never synced. */
  lag_seg: z.number().int().nonnegative().nullable(),
  /** Length of the local sync_queue waiting to drain upstream. */
  pendientes: z.number().int().nonnegative(),
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