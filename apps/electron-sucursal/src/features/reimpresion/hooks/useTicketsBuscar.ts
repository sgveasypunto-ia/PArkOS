/**
 * `useTicketsBuscar.ts` — SWR hook for the ticket-search-by-plate
 * (HU-F8.3 reprint workflow).
 *
 * Calls `GET /api/v1/workflows/reimpresion-ticket?placa=X` via the
 * `make_router` factory endpoint. Returns the most-recent reimpresion
 * ticket for the plate (or `[]` when no rows).
 *
 * REQ-OPS-132 fetcher-closure idiom — fetcher receives bare `placa`.
 * SWR key gate: `null` when `placa` is empty.
 */
import useSWR from 'swr';
import { z } from 'zod';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

export const ReimpresionTicketSchema = z.object({
  uuid: z.string().uuid(),
  uuid_ingreso: z.string().uuid(),
  placa: z.string(),
  motivo: z.string().min(10),
  created_at: z.string(),
});
export type ReimpresionTicket = z.infer<typeof ReimpresionTicketSchema>;
export const ReimpresionTicketArraySchema = z.array(ReimpresionTicketSchema);

async function fetchTicketsByPlaca(placa: string): Promise<ReimpresionTicket[]> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `/api/v1/workflows/reimpresion-ticket?placa=${encodeURIComponent(placa)}`,
  );
  return ReimpresionTicketArraySchema.parse(raw);
}

export function useTicketsBuscar(placa: string | null): {
  data: ReimpresionTicket[] | undefined;
  error: Error | undefined;
  refresh: () => Promise<ReimpresionTicket[] | undefined>;
} {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = placa && accessToken
    ? `/workflows/reimpresion-ticket?placa=${placa}`
    : null;

  const { data, error, mutate } = useSWR<ReimpresionTicket[]>(
    key,
    () => fetchTicketsByPlaca(placa as string),
    {
      dedupingInterval: 5_000,
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
 * `useReimpresion` — POST mutation hook for the reprint request.
 * RHF submits via `parkosFetch` directly; this hook wraps the SWR
 * revalidation after success.
 */
export function useReimpresion() {
  return {
    async submit(payload: {
      placa: string;
      uuid_ingreso: string;
      motivo: string;
    }): Promise<{ uuid: string }> {
      const { parkosFetch } = await import('@parkos/ui-kit/fetch');
      const raw = await parkosFetch<unknown>(
        '/api/v1/workflows/reimpresion-ticket',
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
      );
      const parsed = z.object({ uuid: z.string().uuid() }).parse(raw);
      return parsed;
    },
  };
}