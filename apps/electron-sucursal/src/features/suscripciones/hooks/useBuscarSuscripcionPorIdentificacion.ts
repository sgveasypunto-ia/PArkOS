/**
 * `useBuscarSuscripcionPorIdentificacion.ts` — on-demand search hook
 * for HU-F9.2 realineada paso 2 del Sheet: buscar la suscripción activa
 * de un cliente por su número de identificación.
 *
 * `GET /clientes/subscripciones-activas/buscar?numero_identificacion=X`
 * returns `null` (200) — not an error — when no active subscription
 * matches; the caller renders an explicit empty state.
 *
 * Uses `useSWRMutation` as an on-demand GET trigger (same shape as a
 * POST mutation hook, just semantically a read) so the search only
 * fires when the operator submits, not on every keystroke/mount.
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  GET_BUSCAR_SUBSCRIPCION_PATH,
  SubscripcionCupoDetalleOrNullSchema,
  type SubscripcionCupoDetalle,
} from '../api/cuposApi';

async function handle401(): Promise<never> {
  useAuthStore.getState().clear();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('parkos:auth:cleared'));
  }
  throw new ParkosHttpError(401, '{"error":"unauthorized"}', GET_BUSCAR_SUBSCRIPCION_PATH);
}

async function buscarFn(
  _key: string,
  { arg }: { arg: string },
): Promise<SubscripcionCupoDetalle | null> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  try {
    const raw = await parkosFetch<unknown>(
      `${GET_BUSCAR_SUBSCRIPCION_PATH}?numero_identificacion=${encodeURIComponent(arg)}`,
    );
    return SubscripcionCupoDetalleOrNullSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 401) {
      return handle401();
    }
    throw err;
  }
}

export interface UseBuscarSuscripcionPorIdentificacionReturn {
  trigger: (numero_identificacion: string) => Promise<SubscripcionCupoDetalle | null>;
  isMutating: boolean;
  error: ParkosHttpError | undefined;
  data: SubscripcionCupoDetalle | null | undefined;
}

export function useBuscarSuscripcionPorIdentificacion(): UseBuscarSuscripcionPorIdentificacionReturn {
  const swr: SWRMutationResponse<SubscripcionCupoDetalle | null, Error, string, string> =
    useSWRMutation(GET_BUSCAR_SUBSCRIPCION_PATH, buscarFn);

  return {
    trigger: swr.trigger,
    isMutating: swr.isMutating,
    error: swr.error as ParkosHttpError | undefined,
    data: swr.data,
  };
}
