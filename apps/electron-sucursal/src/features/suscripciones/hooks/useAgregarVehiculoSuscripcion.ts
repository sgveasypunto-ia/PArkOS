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
  CuposSubscripcionNoEncontradaError,
  CuposTipoIncompatibleError,
  CuposVehiculoYaInscritoError,
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

interface BackendErrorBody {
  error?: string;
  placa?: string;
  tipos_encontrados?: string[];
  cantidad_maxima_vehiculos?: number;
}

/**
 * FastAPI's `HTTPException(status_code=422, detail={"error": ...})`
 * serializes to `{"detail": {"error": ...}}` on the wire -- the typed
 * fields live under `.detail`, never at the top level. Real bug found
 * live 2026-09-24 (first time this handler was ever reachable over real
 * HTTP -- the previous double-prefix routing bug made it 404 forever):
 * reading `parsed.error` directly always returned `undefined`, so every
 * 404/409/422 silently fell through to the generic `ParkosHttpError`
 * instead of its typed subclass. Falls back to the top-level object for
 * robustness in case a future endpoint ever returns an unwrapped body.
 */
function parseBackendErrorBody(body: string): BackendErrorBody | null {
  try {
    const parsed = JSON.parse(body) as { detail?: BackendErrorBody } & BackendErrorBody;
    return parsed.detail ?? parsed;
  } catch {
    return null;
  }
}

async function mutateFn(
  _key: string,
  { arg }: { arg: AgregarVehiculoCupoRequest },
): Promise<SubscripcionCupoDetalle> {
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST',
    path: POST_AGREGAR_VEHICULO_PATH,
    body: arg,
  });

  try {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = await parkosFetch<unknown>(POST_AGREGAR_VEHICULO_PATH, {
      method: 'POST',
      body: JSON.stringify(arg),
      headers: { 'Idempotency-Key': idempotencyKey },
    });
    return SubscripcionCupoDetalleSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError) {
      if (err.status === 401) {
        return handle401();
      }
      const parsed = parseBackendErrorBody(err.body);
      const code = parsed?.error;
      if (err.status === 404 && code === 'subscripcion_no_encontrada') {
        throw new CuposSubscripcionNoEncontradaError();
      }
      if (err.status === 409 && code === 'vehiculo_ya_inscrito') {
        throw new CuposVehiculoYaInscritoError(parsed?.placa ?? arg.placa);
      }
      if (err.status === 422 && code === 'tipo_vehiculo_incompatible') {
        throw new CuposTipoIncompatibleError(parsed?.tipos_encontrados ?? []);
      }
      if (err.status === 422 && code === 'cantidad_maxima_excedida') {
        throw new CuposCantidadMaximaError(parsed?.cantidad_maxima_vehiculos ?? 0);
      }
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
