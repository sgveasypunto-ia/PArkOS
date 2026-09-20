/**
 * `useAnularReimpresion.ts` — SWR mutation hook for
 * `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular`
 * (HU-F8.3, REQ-OPS-174).
 *
 * Composition mirrors `useReimprimir.ts` (F8.3) and
 * `useReintentarFE.ts` (F8.2):
 *   - `parkosFetch` for the canonical wire transport (F2.2 auth/retry).
 *   - `buildIdempotencyKey` (F7.2 lib/idempotency.ts) for the SHA-256
 *     RFC 8785 closure header (DEC-SUC-04 + DEC-IDEM-01).
 *   - `ReimpresionTicketAnularSchema` (api/reimpresionApi.ts) for
 *     client-side pre-validation — `motivo_anulacion.min(10)` is
 *     checked BEFORE the POST so the operator never sees a 400
 *     round-trip.
 *   - `ReimpresionTicketReadSchema` for the discriminated response
 *     parse (`workflow_estado='rechazada'` + `uuid_reimpresion_padre`
 *     populated — F1.11 DEC-TKT-03 insert-only invariant).
 *   - `useAuthStore.getState().clear()` + `parkos:auth:cleared` event
 *     on 401 (preserved F3.1 invariant from REQ-OPS-107..110).
 *
 * F1.11 DEC-TKT-03 invariant: anulación NEVER UPDATEs the original
 * reimpresion row. The backend INSERTs a NEW row with
 * `uuid_reimpresion_padre=<original>` and `workflow_estado='rechazada'`.
 * The renderer-side hook just calls the endpoint; the append-only
 * invariant is enforced server-side via F1.11's `WorkflowBase` +
 * `repo.workflow.append_transition(...)`.
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../../operacion/lib/idempotency';
import {
  ReimpresionTicketAnularSchema,
  ReimpresionTicketReadSchema,
  type ReimpresionTicketAnular,
  type ReimpresionTicketRead,
} from '../api/reimpresionApi';

const POST_PATH_PREFIX = '/api/v1/workflows/reimpresion-ticket';

export interface UseAnularReimpresionReturn {
  trigger: (
    input: ReimpresionTicketAnular & { uuidReimpresion: string },
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
    arg: ReimpresionTicketAnular & { uuidReimpresion: string };
  },
): Promise<ReimpresionTicketRead> {
  // REQ-OPS-174 — Zod pre-validation. motivo_anulacion.min(10) check
  // happens BEFORE the POST so a 400 round-trip is avoided.
  ReimpresionTicketAnularSchema.parse(init.arg);

  const path = `${POST_PATH_PREFIX}/${init.arg.uuidReimpresion}/anular`;
  const body = { motivo_anulacion: init.arg.motivo_anulacion };
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
 * `useAnularReimpresion()` — SWR mutation hook returning
 * `{ trigger, isMutating, error, data }`.
 *
 * `trigger({uuidReimpresion, motivoAnulacion})` issues the canonical
 * POST and resolves with the new `ReimpresionTicketRead` payload
 * (`workflow_estado='rechazada'`, `uuid_reimpresion_padre=<original>`).
 *
 * Errors:
 *   - Zod parse failure (motivo_anulacion < 10 chars) → `error` is
 *     `ZodError` (no POST fired).
 *   - 401 → `useAuthStore.clear()` + `parkos:auth:cleared`
 *     (preserved F3.1 invariant).
 */
export function useAnularReimpresion(): UseAnularReimpresionReturn {
  const swr: SWRMutationResponse<
    ReimpresionTicketRead,
    Error,
    string,
    ReimpresionTicketAnular & { uuidReimpresion: string }
  > = useSWRMutation(POST_PATH_PREFIX, mutateFn);

  return {
    trigger: swr.trigger as UseAnularReimpresionReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as ParkosHttpError | undefined,
    data: swr.data,
  };
}
