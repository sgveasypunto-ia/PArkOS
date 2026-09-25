/**
 * `useQuitarVehiculoSuscripcion.ts` — SWR mutation hook for
 * `PUT /clientes/subscripcion-vehiculos/{uuid}/quitar` (HU-F9.2
 * realineada, paso 3 del Sheet: dar de baja un vehículo inscrito).
 *
 * Bi-temporal close_and_insert server-side (nunca DELETE) — the
 * response already carries the refreshed cupo detail, so the caller
 * doesn't need a second round-trip.
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../../operacion/lib/idempotency';
import {
  SubscripcionCupoDetalleSchema,
  putQuitarVehiculoPath,
  type SubscripcionCupoDetalle,
} from '../api/cuposApi';
import { CuposVehiculoInscritoNoEncontradoError } from './cuposErrors';

export { CuposVehiculoInscritoNoEncontradoError } from './cuposErrors';

export interface UseQuitarVehiculoSuscripcionReturn {
  trigger: (uuidSubscripcionVehiculo: string) => Promise<SubscripcionCupoDetalle>;
  isMutating: boolean;
  error: ParkosHttpError | CuposVehiculoInscritoNoEncontradoError | undefined;
  data: SubscripcionCupoDetalle | undefined;
}

async function handle401(path: string): Promise<never> {
  useAuthStore.getState().clear();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('parkos:auth:cleared'));
  }
  throw new ParkosHttpError(401, '{"error":"unauthorized"}', path);
}

async function mutateFn(
  _key: string,
  { arg: uuidSubscripcionVehiculo }: { arg: string },
): Promise<SubscripcionCupoDetalle> {
  const path = putQuitarVehiculoPath(uuidSubscripcionVehiculo);
  const idempotencyKey = await buildIdempotencyKey({
    method: 'PUT',
    path,
    body: {},
  });

  try {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = await parkosFetch<unknown>(path, {
      method: 'PUT',
      headers: { 'Idempotency-Key': idempotencyKey },
    });
    return SubscripcionCupoDetalleSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError) {
      if (err.status === 401) {
        return handle401(path);
      }
      if (err.status === 404) {
        throw new CuposVehiculoInscritoNoEncontradoError();
      }
    }
    throw err;
  }
}

export function useQuitarVehiculoSuscripcion(): UseQuitarVehiculoSuscripcionReturn {
  const swr: SWRMutationResponse<SubscripcionCupoDetalle, Error, string, string> =
    useSWRMutation('subscripcion-vehiculos/quitar', mutateFn);

  return {
    trigger: swr.trigger,
    isMutating: swr.isMutating,
    error: swr.error as UseQuitarVehiculoSuscripcionReturn['error'],
    data: swr.data,
  };
}
