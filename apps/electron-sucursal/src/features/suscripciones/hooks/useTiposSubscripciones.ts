/**
 * `useTiposSubscripciones` — SWR hook for the active branch's
 * subscription plans. Drives step 3 of the `<Venta />` wizard so the
 * operator no longer types a plan UUID by hand.
 *
 * Calls `GET /api/v1/tipos-subscripciones?uuid_sucursal=X` via
 * parkosFetch + `TipoSubscripcionArraySchema.parse` (Zod mirror of
 * the backend `TipoSubscripcionesRead` Pydantic schema). Reuses the
 * authStore access-token gate so the SWR key is `null` while
 * unauthenticated (same REQ-OPS-132 fetcher-closure baseline used by
 * useSuscripcionesList and useTiposVehiculo).
 *
 * Defense in depth: `shouldRetryOnError` skips 401 / 403 / 404 (latter
 * for the case where the branch has no plans yet — operator sees the
 * empty state in the wizard instead of retry spam).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import type {
  TipoSubscripcion} from '../api/ventaSuscripcionApi';
import {
  GET_TIPOS_SUBSCRIPCION_PATH,
  TipoSubscripcionListSchema,
} from '../api/ventaSuscripcionApi';

async function fetchTiposSubscripciones(
  uuid_sucursal: string,
): Promise<TipoSubscripcion[]> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `${GET_TIPOS_SUBSCRIPCION_PATH}?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}`,
  );
  // Catalog endpoints wrap the rows in `{ items, next_cursor }` per
  // the F1.12 cursor-pagination contract. Unwrap to the bare array
  // for SWR consumers + downstream callers.
  return TipoSubscripcionListSchema.parse(raw).items;
}

export interface UseTiposSubscripcionesResult {
  data: TipoSubscripcion[] | undefined;
  error: Error | undefined;
  isLoading: boolean;
  refresh: () => Promise<TipoSubscripcion[] | undefined>;
}

export function useTiposSubscripciones(
  uuid_sucursal: string | null,
): UseTiposSubscripcionesResult {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key =
    uuid_sucursal && accessToken
      ? `${GET_TIPOS_SUBSCRIPCION_PATH}?uuid_sucursal=${uuid_sucursal}`
      : null;

  const { data, error, isLoading, mutate } = useSWR<TipoSubscripcion[]>(
    key,
    () => fetchTiposSubscripciones(uuid_sucursal as string),
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
    isLoading,
    refresh: async () => mutate(),
  };
}
