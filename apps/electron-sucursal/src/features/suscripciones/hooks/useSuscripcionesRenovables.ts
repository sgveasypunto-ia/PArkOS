/**
 * `useSuscripcionesRenovables.ts` — SWR hook for
 * `GET /clientes/subscripciones/renovables` (PT-3): subscriptions with
 * <= 10 days left, expired ones included. The "Renovar" action is offered
 * ONLY for these rows (`puede_renovar` comes from the backend).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  GET_RENOVABLES_PATH,
  SuscripcionVencimientoListSchema,
  type SuscripcionVencimientoItem,
} from '../api/renovacionApi';

async function fetchRenovables(): Promise<SuscripcionVencimientoItem[]> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(GET_RENOVABLES_PATH);
  return SuscripcionVencimientoListSchema.parse(raw);
}

export interface UseSuscripcionesRenovablesResult {
  data: SuscripcionVencimientoItem[] | undefined;
  error: Error | undefined;
  refresh: () => Promise<SuscripcionVencimientoItem[] | undefined>;
}

export function useSuscripcionesRenovables(
  uuid_sucursal: string | null,
): UseSuscripcionesRenovablesResult {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = uuid_sucursal && accessToken ? ([GET_RENOVABLES_PATH, uuid_sucursal] as const) : null;

  const { data, error, mutate } = useSWR<SuscripcionVencimientoItem[]>(key, () => fetchRenovables(), {
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
  });

  return { data, error, refresh: async () => mutate() };
}
