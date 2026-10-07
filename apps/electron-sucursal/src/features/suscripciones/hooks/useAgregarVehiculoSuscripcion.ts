/**
 * `useAgregarVehiculoSuscripcion.ts` — SWR mutation hook for
 * `POST /clientes/subscripcion-vehiculos/agregar` (HU-F9.2 realineada,
 * paso 3 del Sheet: agregar un vehículo a una suscripción existente).
 *
 * Mirrors `useVentaSuscripcion.ts` composition verbatim: `parkosFetch`
 * + `buildIdempotencyKey` + typed 422/404/409 error subclasses so the
 * cupos UI can `instanceof`-discriminate the inline message.
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../../operacion/lib/idempotency';
import {
  POST_AGREGAR_VEHICULO_PATH,
  SubscripcionCupoDetalleSchema,
  type AgregarVehiculoCupoRequest,
  type SubscripcionCupoDetalle,
} from '../api/cuposApi';
import {
  CuposCantidadMaximaError,
  CuposContextoSucursalError,
  CuposPermisoDenegadoError,
  CuposPlacaConSuscripcionActivaError,
  CuposSubscripcionNoEncontradaError,
  CuposTipoIncompatibleError,
  CuposTipoPlanIncompatibleError,
  CuposVehiculoYaInscritoError,
  mapCuposHttpError,
} from './cuposErrors';

export {
  CuposCantidadMaximaError,
  CuposSubscripcionNoEncontradaError,
  CuposTipoIncompatibleError,
  CuposVehiculoYaInscritoError,
} from './cuposErrors';

export interface UseAgregarVehiculoSuscripcionReturn {
  trigger: (input: AgregarVehiculoCupoRequest) => Promise<SubscripcionCupoDetalle>;
  isMutating: boolean;
  error:
    | ParkosHttpError
    | CuposSubscripcionNoEncontradaError
    | CuposVehiculoYaInscritoError
    | CuposTipoIncompatibleError
    | CuposCantidadMaximaError
    | CuposPermisoDenegadoError
    | CuposContextoSucursalError
    | CuposPlacaConSuscripcionActivaError
    | CuposTipoPlanIncompatibleError
    | undefined;
  data: SubscripcionCupoDetalle | undefined;
}

async function handle401(): Promise<never> {
  useAuthStore.getState().clear();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('parkos:auth:cleared'));
  }
  throw new ParkosHttpError(401, '{"error":"unauthorized"}', POST_AGREGAR_VEHICULO_PATH);
}

async function mutateFn(
  _key: string,
  { arg }: { arg: AgregarVehiculoCupoRequest },
): Promise<SubscripcionCupoDetalle> {
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST',
    path: POST_AGREGAR_VEHICULO_PATH,
    // Per-attempt nonce: add -> remove -> add of the same plate must NOT replay
    // the cached 201 of the first add (the middleware caches by key for 24h).
    body: { ...arg, intento: crypto.randomUUID() },
  });

  try {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = await parkosFetch<unknown>(POST_AGREGAR_VEHICULO_PATH, {
      method: 'POST',
      body: JSON.stringify(arg),
      headers: { 'Idempotency-Key': idempotencyKey },
      skipIdempotencyKey: true,
    });
    return SubscripcionCupoDetalleSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError) {
      if (err.status === 401) {
        return handle401();
      }
      const mapped = mapCuposHttpError(err.status, err.body, arg.placa);
      if (mapped) throw mapped;
    }
    throw err;
  }
}

export function useAgregarVehiculoSuscripcion(): UseAgregarVehiculoSuscripcionReturn {
  const swr: SWRMutationResponse<
    SubscripcionCupoDetalle,
    Error,
    string,
    AgregarVehiculoCupoRequest
  > = useSWRMutation(POST_AGREGAR_VEHICULO_PATH, mutateFn);

  return {
    trigger: swr.trigger,
    isMutating: swr.isMutating,
    error: swr.error as UseAgregarVehiculoSuscripcionReturn['error'],
    data: swr.data,
  };
}
