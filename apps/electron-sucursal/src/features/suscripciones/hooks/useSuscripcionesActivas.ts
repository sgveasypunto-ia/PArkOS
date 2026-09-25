/**
 * `useSuscripcionesActivas.ts` — SWR hook for the branch's active
 * subscriptions (HU-F9.2 realineada, paso 1 del Sheet).
 *
 * Replaces the broken `useSuscripcionesList.ts` (called
 * `GET /api/v1/clientes/suscripciones?uuid_sucursal=X`, an endpoint
 * that never existed — guaranteed 404, confirmed live). Calls the real
 * dedicated endpoint `GET /clientes/subscripciones-activas`, which is
 * branch-scoped automatically server-side (tenancy `ContextVar`, no
 * `uuid_sucursal` query param needed or accepted).
 *
 * Mirrors `useTiposSubscripciones.ts` SWR shape verbatim (REQ-OPS-132
 * fetcher-closure, 401-clear invariant, `shouldRetryOnError` skip).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  GET_SUBSCRIPCIONES_ACTIVAS_PATH,
  SubscripcionesActivasResponseSchema,
  type SubscripcionActivaItem,
} from '../api/cuposApi';

async function fetchSubscripcionesActivas(): Promise<SubscripcionActivaItem[]> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(GET_SUBSCRIPCIONES_ACTIVAS_PATH);
  return SubscripcionesActivasResponseSchema.parse(raw).items;
}

export interface UseSuscripcionesActivasResult {
  data: SubscripcionActivaItem[] | undefined;
  error: Error | undefined;
  refresh: () => Promise<SubscripcionActivaItem[] | undefined>;
}

export function useSuscripcionesActivas(
  uuid_sucursal: string | null,
): UseSuscripcionesActivasResult {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = uuid_sucursal && accessToken ? GET_SUBSCRIPCIONES_ACTIVAS_PATH : null;

  const { data, error, mutate } = useSWR<SubscripcionActivaItem[]>(
    key,
    fetchSubscripcionesActivas,
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
