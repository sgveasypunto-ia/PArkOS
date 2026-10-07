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

import { withActionIdempotencyKey } from '../../operacion/lib/idempotency';
import {
  SubscripcionCupoDetalleSchema,
  putQuitarVehiculoPath,
  type SubscripcionCupoDetalle,
} from '../api/cuposApi';
import {
  CuposVehiculoInscritoNoEncontradoError,
  mapCuposHttpError,
  type CuposContextoSucursalError,
  type CuposPermisoDenegadoError,
  type CuposSubscripcionNoEncontradaError,
} from './cuposErrors';

export { CuposVehiculoInscritoNoEncontradoError } from './cuposErrors';

export interface UseQuitarVehiculoSuscripcionReturn {
  trigger: (uuidSubscripcionVehiculo: string) => Promise<SubscripcionCupoDetalle>;
  isMutating: boolean;
  error:
    | ParkosHttpError
    | CuposVehiculoInscritoNoEncontradoError
    | CuposPermisoDenegadoError
    | CuposContextoSucursalError
    | CuposSubscripcionNoEncontradaError
    | undefined;
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
  try {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = await withActionIdempotencyKey(
      { method: 'PUT', path, body: null },
      (idempotencyKey) =>
        parkosFetch<unknown>(path, {
          method: 'PUT',
          headers: { 'Idempotency-Key': idempotencyKey },
          skipIdempotencyKey: true,
        }),
    );
    return SubscripcionCupoDetalleSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError) {
      if (err.status === 401) {
        return handle401(path);
      }
      const mapped = mapCuposHttpError(err.status, err.body);
      if (mapped) throw mapped;
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
