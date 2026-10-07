/**
 * `useTiposSubscripciones` — SWR hook for the active branch's
 * subscription plans. Drives step 3 of the `<Venta />` wizard so the
 * operator no longer types a plan UUID by hand.
 *
 * Calls `GET /api/v1/catalogos/tipo-subscripciones?uuid_sucursal=X[&uuid_tipo_vehiculo=Y]` via
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

function buildUrl(uuid_sucursal: string, uuid_tipo_vehiculo: string | null): string {
  const base = `${GET_TIPOS_SUBSCRIPCION_PATH}?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}`;
  // PT-2: the backend returns the plans of that vehicle type plus the ones
  // with a NULL type (valid for any vehicle).
  return uuid_tipo_vehiculo
    ? `${base}&uuid_tipo_vehiculo=${encodeURIComponent(uuid_tipo_vehiculo)}`
    : base;
}

async function fetchTiposSubscripciones(
  uuid_sucursal: string,
  uuid_tipo_vehiculo: string | null,
): Promise<TipoSubscripcion[]> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(buildUrl(uuid_sucursal, uuid_tipo_vehiculo));
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

/**
 * `uuid_tipo_vehiculo`: `undefined` = unfiltered (legacy callers); a string =
 * only plans of that vehicle type (+ type-agnostic ones); `null` = the
 * caller has not chosen a type yet, so nothing is fetched (never show
 * plans of the wrong type).
 */
export function useTiposSubscripciones(
  uuid_sucursal: string | null,
  uuid_tipo_vehiculo?: string | null,
): UseTiposSubscripcionesResult {
  const accessToken = useAuthStore((s) => s.accessToken);
  const tipoVehiculo = uuid_tipo_vehiculo ?? null;
  const gated = uuid_tipo_vehiculo === null;
  const key =
    uuid_sucursal && accessToken && !gated ? buildUrl(uuid_sucursal, tipoVehiculo) : null;

  const { data, error, isLoading, mutate } = useSWR<TipoSubscripcion[]>(
    key,
    () => fetchTiposSubscripciones(uuid_sucursal as string, tipoVehiculo),
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
