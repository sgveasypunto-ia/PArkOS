/**
 * `useRegistrarPagoServicio.ts` — SWR mutation hook for
 * `POST /api/v1/facturacion/factura-servicio` (HU-F8.3, ajuste
 * 2026-09-25). Mirrors `useRegistrarPago.ts` verbatim, swapping the
 * salida-anchored payload/path for the ingreso-anchored one.
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../../operacion/lib/idempotency';
import {
  postFacturaServicio,
  type PostFacturaServicioPayload,
} from '../api/facturaServicioApi';
import type { FacturaRead } from '../api/facturaApi';

const POST_PATH = '/api/v1/facturacion/factura-servicio';

export interface UseRegistrarPagoServicioReturn {
  trigger: (input: PostFacturaServicioPayload) => Promise<FacturaRead>;
  isMutating: boolean;
  error: ParkosHttpError | undefined;
  data: FacturaRead | undefined;
}

async function handle401(): Promise<never> {
  useAuthStore.getState().clear();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('parkos:auth:cleared'));
  }
  throw new ParkosHttpError(401, '{"error":"unauthorized"}', POST_PATH);
}

async function mutateFn(
  _key: string,
  init: { arg: PostFacturaServicioPayload },
): Promise<FacturaRead> {
  const body = init.arg;
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST',
    path: POST_PATH,
    body,
  });

  try {
    return await postFacturaServicio(body, idempotencyKey);
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 401) {
      return handle401();
    }
    throw err;
  }
}

export function useRegistrarPagoServicio(): UseRegistrarPagoServicioReturn {
  const swr: SWRMutationResponse<
    FacturaRead,
    Error,
    string,
    PostFacturaServicioPayload
  > = useSWRMutation(POST_PATH, mutateFn);

  return {
    trigger: swr.trigger as UseRegistrarPagoServicioReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as ParkosHttpError | undefined,
    data: swr.data,
  };
}
