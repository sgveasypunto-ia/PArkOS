/**
 * `useRenovarSuscripcion.ts` — SWR mutation hook for
 * `POST /clientes/subscripciones/{uuid}/renovar` (PT-3).
 *
 * The backend REQUIRES an `Idempotency-Key` per attempt. The caller owns
 * the attempt id (`intentoId`): the same id on a retry (network / 5xx)
 * replays the stored 201 instead of charging twice; a NEW id starts a new
 * attempt. The key is built with the shared `buildIdempotencyKey` helper and
 * sent with `skipIdempotencyKey` so `parkosFetch` does not overwrite it with
 * its generic body hash (which would collide across attempts).
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../../operacion/lib/idempotency';
import {
  RenovarSuscripcionRequestSchema,
  RenovarSuscripcionResponseSchema,
  postRenovarPath,
  type RenovarSuscripcionRequest,
  type RenovarSuscripcionResponse,
} from '../api/renovacionApi';
import { RenovacionError, mapRenovacionHttpError } from './renovacionErrors';

export interface RenovarSuscripcionInput extends RenovarSuscripcionRequest {
  uuid_subscripcion: string;
  /** Stable id of the operator's attempt (see file header). */
  intentoId: string;
}

export interface UseRenovarSuscripcionReturn {
  trigger: (input: RenovarSuscripcionInput) => Promise<RenovarSuscripcionResponse>;
  isMutating: boolean;
  error: RenovacionError | ParkosHttpError | undefined;
  data: RenovarSuscripcionResponse | undefined;
  reset: () => void;
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
  { arg }: { arg: RenovarSuscripcionInput },
): Promise<RenovarSuscripcionResponse> {
  const { uuid_subscripcion, intentoId, ...rest } = arg;
  // Zod gate (datafono requires the voucher) BEFORE touching the network.
  const body = RenovarSuscripcionRequestSchema.parse(rest);
  const path = postRenovarPath(uuid_subscripcion);
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST',
    path,
    body: { ...body, intento: intentoId },
  });

  try {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = await parkosFetch<unknown>(path, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'Idempotency-Key': idempotencyKey },
      skipIdempotencyKey: true,
    });
    return RenovarSuscripcionResponseSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError) {
      if (err.status === 401) return handle401(path);
      if (err.status >= 400 && err.status < 500) {
        throw mapRenovacionHttpError(err.status, err.body);
      }
      if (err.status === 500) {
        // 500 `iva_no_configurado` is a business answer, not a transient fault.
        const mapped = mapRenovacionHttpError(err.status, err.body);
        if (mapped.code !== 'desconocido') throw mapped;
      }
    }
    throw err;
  }
}

export function useRenovarSuscripcion(): UseRenovarSuscripcionReturn {
  const swr: SWRMutationResponse<
    RenovarSuscripcionResponse,
    Error,
    string,
    RenovarSuscripcionInput
  > = useSWRMutation('clientes/subscripciones/renovar', mutateFn);

  return {
    trigger: swr.trigger as UseRenovarSuscripcionReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as UseRenovarSuscripcionReturn['error'],
    data: swr.data,
    reset: swr.reset,
  };
}
