/**
 * `useRegistrarSalida.ts` — SWR mutation hook for `POST /api/v1/operacion/salidas`
 * (HU-F7.2, REQ-OPS-154).
 *
 * Composition:
 *   - `parkosFetch` for the canonical wire transport (F2.2 auth/retry).
 *   - `buildIdempotencyKey` (lib/idempotency.ts) for the SHA-256
 *     RFC 8785 closure header (DEC-SUC-04 + DEC-IDEM-01 reuse from F1.6).
 *   - `SalidaReadForzadoSchema` (api/salidaApi.ts) for the response parse.
 *   - `useAuthStore.getState().clear()` + `parkos:auth:cleared` event
 *     on 401 (preserved F3.1 invariant from REQ-OPS-107..110; mirrors
 *     `useCotizacion.ts:154-160`).
 *
 * The hook is `modo`-indifferent per DEC-MONO-01 (F1.7 server-side
 * `tipo_salida` derivation): the consumer reads `data.tipo_salida`
 * from the response and routes downstream UX.
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../lib/idempotency';
import { SalidaReadForzadoSchema, type SalidaReadForzado } from '../api/salidaApi';

const POST_PATH = '/api/v1/operacion/salidas';

export interface RegistrarSalidaInput {
  uuid_ingreso: string;
}

export interface UseRegistrarSalidaReturn {
  trigger: (input: RegistrarSalidaInput) => Promise<SalidaReadForzado>;
  isMutating: boolean;
  error: ParkosHttpError | undefined;
  data: SalidaReadForzado | undefined;
}

async function handle401(): Promise<never> {
  useAuthStore.getState().clear();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('parkos:auth:cleared'));
  }
  // Re-throw as a normalized ParkosHttpError so the hook's surface
  // stays consistent (status 401) — the auth-cleared side-effect is
  // already done above.
  throw new ParkosHttpError(401, '{"error":"unauthorized"}', POST_PATH);
}

/**
 * SWR fetcher — synchronous-looking wrapper around the POST. We use
 * SWR's mutation hook to expose `isMutating` (REQ-OPS-152 UI in-flight
 * disable) and to integrate with the existing `parkosFetch` retry
 * pipeline.
 */
async function mutateFn(
  _key: string,
  init: { arg: RegistrarSalidaInput },
): Promise<SalidaReadForzado> {
  const body = { uuid_ingreso: init.arg.uuid_ingreso };
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST',
    path: POST_PATH,
    body,
  });

  try {
    const raw = await postSalidaWithIdempotency(body, idempotencyKey);
    return SalidaReadForzadoSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 401) {
      return handle401();
    }
    throw err;
  }
}

/**
 * Thin wrapper around `parkosFetch` that lets us pass an explicit
 * `Idempotency-Key` header (the public `salidaApi.postSalida` relies
 * on `parkosFetch`'s internal hash which uses `JSON.stringify(body)` —
 * same input shape as our `buildIdempotencyKey` when the body has
 * only `uuid_ingreso`, but explicit forwarding documents the contract
 * at the call site).
 */
async function postSalidaWithIdempotency(
  body: { uuid_ingreso: string },
  idempotencyKey: string,
): Promise<unknown> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  return parkosFetch<unknown>(POST_PATH, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  });
}

/**
 * `useRegistrarSalida()` — SWR mutation hook returning
 * `{ trigger, isMutating, error, data }`. `trigger({uuid_ingreso})`
 * issues the canonical POST and resolves with the parsed
 * `SalidaReadForzado` payload.
 *
 * 401 → `useAuthStore.clear()` + `parkos:auth:cleared` (preserved
 * invariant from F3.1 / `useCotizacion.ts`).
 */
export function useRegistrarSalida(): UseRegistrarSalidaReturn {
  const swr: SWRMutationResponse<SalidaReadForzado, Error, string, RegistrarSalidaInput> =
    useSWRMutation(POST_PATH, mutateFn);

  return {
    trigger: swr.trigger as UseRegistrarSalidaReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as ParkosHttpError | undefined,
    data: swr.data,
  };
}