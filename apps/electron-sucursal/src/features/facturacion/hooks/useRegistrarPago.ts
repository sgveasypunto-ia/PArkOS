/**
 * `useRegistrarPago.ts` — SWR mutation hook for
 * `POST /api/v1/facturacion/factura` (HU-F8.1, REQ-OPS-167).
 *
 * Composition (mirrors `useRegistrarSalida.ts` precedent — F7.2):
 *   - `parkosFetch` for the canonical wire transport (F2.2
 *     auth/retry).
 *   - `buildIdempotencyKey` (lib/idempotency.ts — F7.2) for the
 *     SHA-256 RFC 8785 closure header (DEC-SUC-04 + DEC-IDEM-01
 *     reuse from F1.6).
 *   - `FacturaReadSchema` (api/facturaApi.ts) for the discriminated
 *     response parse (efectivo | datafono by `medio_pago`).
 *   - `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *     event on 401 (preserved F3.1 invariant from REQ-OPS-107..110;
 *     mirrors `useRegistrarSalida.ts`).
 *
 * The hook is `modo`-indifferent per DEC-MONO-01 (F1.7 server-side
 * `tipo_salida` derivation precedent): the consumer reads
 * `data.numero_recibo` from the response and routes downstream UX
 * (CU-15S print trigger + recibo de pago print trigger — both
 * DEC-SUC-27 ordered, fires AFTER pago).
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../../operacion/lib/idempotency';
import {
  postFactura,
  type FacturaRead,
  type PostFacturaPayload,
} from '../api/facturaApi';

const POST_PATH = '/api/v1/facturacion/factura';

export interface UseRegistrarPagoReturn {
  trigger: (input: PostFacturaPayload) => Promise<FacturaRead>;
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
  init: { arg: PostFacturaPayload },
): Promise<FacturaRead> {
  const body = init.arg;
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST',
    path: POST_PATH,
    body,
  });

  try {
    return await postFactura(body, idempotencyKey);
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 401) {
      return handle401();
    }
    throw err;
  }
}

/**
 * `useRegistrarPago()` — SWR mutation hook returning
 * `{ trigger, isMutating, error, data }`.
 *
 * `trigger({uuid_ingreso, medio_pago, ...})` issues the canonical
 * POST and resolves with the parsed `FacturaRead` payload
 * (discriminated by `medio_pago`).
 *
 * 401 → `useAuthStore.clear()` + `parkos:auth:cleared` (preserved
 * invariant from F3.1 / `useRegistrarSalida.ts`).
 *
 * Doble trigger with the same body yields the SAME `Idempotency-Key`
 * header — the server-side `IdempotencyKeyMiddleware` (F1.6) dedups
 * the second POST.
 */
export function useRegistrarPago(): UseRegistrarPagoReturn {
  const swr: SWRMutationResponse<FacturaRead, Error, string, PostFacturaPayload> =
    useSWRMutation(POST_PATH, mutateFn);

  return {
    trigger: swr.trigger as UseRegistrarPagoReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as ParkosHttpError | undefined,
    data: swr.data,
  };
}