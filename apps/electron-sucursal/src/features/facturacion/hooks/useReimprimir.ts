/**
 * `useReimprimir.ts` — SWR mutation hook for
 * `POST /api/v1/workflows/reimpresion-ticket/{uuid_ingreso}/reimprimir`
 * (HU-F8.3, REQ-OPS-173).
 *
 * Composition mirrors `useRegistrarPago.ts` (F8.1) and
 * `useReintentarFE.ts` (F8.2):
 *   - `parkosFetch` for the canonical wire transport (F2.2 auth/retry).
 *   - `buildIdempotencyKey` (F7.2 lib/idempotency.ts) for the SHA-256
 *     RFC 8785 closure header (DEC-SUC-04 + DEC-IDEM-01).
 *   - `ReimpresionTicketCreateSchema` (api/reimpresionApi.ts) for
 *     client-side pre-validation — `motivo.min(10)` is checked
 *     BEFORE the POST so the operator never sees a 400 round-trip.
 *   - `ReimpresionTicketReadSchema` for the discriminated response
 *     parse (workflow_estado + uuid_factura nullable per DEC-TKT-04).
 *   - `useAuthStore.getState().clear()` + `parkos:auth:cleared` event
 *     on 401 (preserved F3.1 invariant from REQ-OPS-107..110).
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../../operacion/lib/idempotency';
import {
  ReimpresionTicketCreateSchema,
  ReimpresionTicketReadSchema,
  type ReimpresionTicketCreate,
  type ReimpresionTicketRead,
} from '../api/reimpresionApi';

const POST_PATH_PREFIX = '/api/v1/workflows/reimpresion-ticket';

export interface UseReimprimirReturn {
  trigger: (
    input: ReimpresionTicketCreate & { uuidIngreso: string },
  ) => Promise<ReimpresionTicketRead>;
  isMutating: boolean;
  error: ParkosHttpError | undefined;
  data: ReimpresionTicketRead | undefined;
}

async function handle401(): Promise<never> {
  useAuthStore.getState().clear();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('parkos:auth:cleared'));
  }
  throw new ParkosHttpError(401, '{"error":"unauthorized"}', POST_PATH_PREFIX);
}

async function mutateFn(
  _key: string,
  init: {
    arg: ReimpresionTicketCreate & { uuidIngreso: string };
  },
): Promise<ReimpresionTicketRead> {
  // REQ-OPS-173 — Zod pre-validation. motivo.min(10) check happens
  // BEFORE the POST so a 400 round-trip is avoided. A ZodError thrown
  // here propagates through SWRMutation as `error`.
  ReimpresionTicketCreateSchema.parse(init.arg);

  const path = `${POST_PATH_PREFIX}/${init.arg.uuidIngreso}/reimprimir`;
  const body = { motivo: init.arg.motivo, tipo: init.arg.tipo };
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST',
    path,
    body,
  });

  try {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = await parkosFetch<unknown>(path, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'Idempotency-Key': idempotencyKey },
    });
    return ReimpresionTicketReadSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 401) {
      return handle401();
    }
    throw err;
  }
}

/**
 * `useReimprimir()` — SWR mutation hook returning
 * `{ trigger, isMutating, error, data }`.
 *
 * `trigger({uuidIngreso, motivo, tipo})` issues the canonical POST
 * and resolves with the parsed `ReimpresionTicketRead` payload.
 *
 * Errors:
 *   - Zod parse failure (motivo < 10 chars) → `error` is `ZodError`
 *     (no POST fired).
 *   - 401 → `useAuthStore.clear()` + `parkos:auth:cleared`
 *     (preserved F3.1 invariant from `useRegistrarPago.ts` /
 *     `useReintentarFE.ts`).
 *
 * Doble trigger with the same body yields the SAME `Idempotency-Key`
 * header — the server-side `IdempotencyKeyMiddleware` (F1.6) dedups
 * the second POST.
 */
export function useReimprimir(): UseReimprimirReturn {
  const swr: SWRMutationResponse<
    ReimpresionTicketRead,
    Error,
    string,
    ReimpresionTicketCreate & { uuidIngreso: string }
  > = useSWRMutation(POST_PATH_PREFIX, mutateFn);

  return {
    trigger: swr.trigger as UseReimprimirReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as ParkosHttpError | undefined,
    data: swr.data,
  };
}
