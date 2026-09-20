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

/**
 * Typed error for 409 `salida_duplicada` (REQ-OPS-156). The backend
 * F1.7 Pydantic schema `SalidaDuplicadaError` at
 * `backend/.../schemas/operacion.py:434-438` carries `uuid_ingreso`
 * (the ingreso with the conflicting salida). Mirrors that field
 * exactly.
 */
export class SalidaDuplicadaError extends Error {
  public readonly status = 409;
  public readonly uuid_ingreso: string;
  constructor(uuid_ingreso: string) {
    super('salida_duplicada');
    this.name = 'SalidaDuplicadaError';
    this.uuid_ingreso = uuid_ingreso;
  }
}

export interface UseRegistrarSalidaReturn {
  trigger: (input: RegistrarSalidaInput) => Promise<SalidaReadForzado>;
  isMutating: boolean;
  error: ParkosHttpError | SalidaDuplicadaError | undefined;
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
    if (err instanceof ParkosHttpError) {
      if (err.status === 401) {
        return handle401();
      }
      if (err.status === 409) {
        // F1.7 maps partial unique index `one_exit_per_ingreso` violation
        // to `SalidaDuplicadaError` body: `{error, uuid_ingreso}`.
        const uuid = parseSalidaDuplicadaUuid(err.body) ?? init.arg.uuid_ingreso;
        throw new SalidaDuplicadaError(uuid);
      }
    }
    throw err;
  }
}

function parseSalidaDuplicadaUuid(body: string): string | null {
  try {
    const parsed = JSON.parse(body) as { error?: string; uuid_ingreso?: string };
    if (parsed.error === 'salida_duplicada' && typeof parsed.uuid_ingreso === 'string') {
      return parsed.uuid_ingreso;
    }
    return null;
  } catch {
    return null;
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
 * 409 → `SalidaDuplicadaError(uuid_ingreso)`.
 */
export function useRegistrarSalida(): UseRegistrarSalidaReturn {
  const swr: SWRMutationResponse<SalidaReadForzado, Error, string, RegistrarSalidaInput> =
    useSWRMutation(POST_PATH, mutateFn);

  return {
    trigger: swr.trigger as UseRegistrarSalidaReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as ParkosHttpError | SalidaDuplicadaError | undefined,
    data: swr.data,
  };
}