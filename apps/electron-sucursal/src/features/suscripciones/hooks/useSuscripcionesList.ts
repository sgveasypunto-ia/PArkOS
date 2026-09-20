/**
 * `useSuscripcionesList.ts` — SWR hook for the suscripciones listing
 * (HU-F9.2).
 *
 * Calls `GET /api/v1/clientes/suscripciones?uuid_sucursal=X` via the
 * standard list endpoint (F1.12 archive). Returns the rows with their
 * expiry dates so the panel can highlight "vence en X días" banners.
 *
 * REQ-OPS-132 fetcher-closure — fetcher receives bare `uuid_sucursal`.
 * SWR key gate: `null` when `uuid_sucursal` is empty.
 */
import useSWR from 'swr';
import { z } from 'zod';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

export const SuscripcionSchema = z.object({
  uuid: z.string().uuid(),
  uuid_cliente: z.string().uuid(),
  placa: z.string(),
  uuid_plan: z.string().uuid(),
  fecha_inicio: z.string(),
  fecha_fin: z.string(),
  estado: z.enum(['activa', 'vencida', 'suspendida']),
});
export type Suscripcion = z.infer<typeof SuscripcionSchema>;
export const SuscripcionArraySchema = z.array(SuscripcionSchema);

async function fetchSuscripciones(uuid_sucursal: string): Promise<Suscripcion[]> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `/api/v1/clientes/suscripciones?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}`,
  );
  return SuscripcionArraySchema.parse(raw);
}

export function useSuscripcionesList(uuid_sucursal: string | null): {
  data: Suscripcion[] | undefined;
  error: Error | undefined;
  refresh: () => Promise<Suscripcion[] | undefined>;
} {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = uuid_sucursal && accessToken
    ? `/clientes/suscripciones?uuid_sucursal=${uuid_sucursal}`
    : null;

  const { data, error, mutate } = useSWR<Suscripcion[]>(
    key,
    () => fetchSuscripciones(uuid_sucursal as string),
    {
      dedupingInterval: 30_000,
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