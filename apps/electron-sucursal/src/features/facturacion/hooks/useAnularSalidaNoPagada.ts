/**
 * `useAnularSalidaNoPagada.ts` — SWR mutation hook for
 * `POST /api/v1/operacion/salidas/{uuid_salida}/anular-no-pagada`
 * (HU-F8.1-anular-salida-no-pagada, 2026-09-23).
 *
 * Use case: when the operator closes the F8.1 payment drawer WITHOUT
 * confirming the cobro (Cancelar button / X / overlay click / Escape),
 * the ingreso would otherwise stay closed because the matching
 * `prod.salidas` row is already inserted (from `POST /operacion/salidas`).
 * This hook writes an annulment row to `prod.anulaciones` (a workflow
 * `[L-W]` event) so `V_INGRESO_ESTADO` recalculates back to `abierto`
 * and the operator can collect on the next visit (or any other shift).
 *
 * Composition (mirrors `useRegistrarPago.ts` precedent — F8.1):
 *   - `parkosFetch` for the canonical wire transport (F2.2
 *     auth/retry).
 *   - `buildIdempotencyKey` (lib/idempotency.ts — F7.2) for the
 *     SHA-256 RFC 8785 closure header (DEC-SUC-04 + DEC-IDEM-01
 *     reuse from F1.6). A double-trigger with the same `uuid_salida`
 *     yields the SAME Idempotency-Key → server-side cache dedup
 *     (F1.6 `IdempotencyKeyMiddleware`).
 *   - 401 → `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *     event (preserved F3.1 invariant from REQ-OPS-107..110;
 *     mirrors `useRegistrarSalida`).
 *
 * BE contract (`backend/.../api/v1/operacion.py::anular_salida_no_pagada_endpoint`,
 * F8.1-b endpoint):
 *   - Custom per-case endpoint (NOT the generic factory
 *     ``/workflows/anulaciones`` because that one ships with
 *     ``write_enabled=False`` per PR6 rationale, see
 *     ``backend/.../api/v1/workflows.py:106``). The factory cannot
 *     be reused for ``Anulaciones`` ([L-W] workflow, not [V]
 *     versioned) without growing ``make_router`` with a new
 *     ``repo_kind`` branch — too invasive for a one-case fix.
 *   - Body: ``{ motivo: string }`` (≥10 chars, ≤500 chars — same
 *     validator as the BE schema
 *     ``AnularSalidaNoPagadaPayload.motivo``). We send the
 *     Spanish audit-trail literal ``MOTIVO_AUTO_ANULACION_SALIDA``
 *     so operators can grep ``prod.anulaciones.motivo`` later.
 *   - Path param: ``uuid_salida``.
 *   - Response: 201 ``AnulacionesRead`` (or 404 ``salida_no_encontrada``,
 *     409 ``salida_ya_anulada``).
 *   - Idempotency-Key: ``DEC-IDEM-01`` (F1.6) — server-side cache
 *     dedups. Combined with the V2 guard inside the handler
 *     (``SalidaYaAnulada`` → 409), the annulment is robust to
 *     network retries / double-clicks.
 *
 * Operational contract (F8.1-b):
 *   - Call ONLY from `<PagoSheet>` `handleClose()` when
 *     `pagadoRef.current === false`. The call MUST NOT block the
 *     sheet unmount — the workflow write is async, and the operator
 *     already dismissed the drawer. The `trigger()` resolves with the
 *     newly-created `AnulacionesRead`; the caller may surface a
 *     warning toast if it fails (so the operator knows the ingreso
 *     stayed closed), but the spec does NOT block the next cobro on
 *     annulation success — it's an audit-trail write.
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../../operacion/lib/idempotency';

const POST_PATH_PREFIX = '/api/v1/operacion/salidas/';
const POST_PATH_SUFFIX = '/anular-no-pagada';

/**
 * Spanish audit-trail motivo (62 chars; ≥10 required by
 * `AnularSalidaNoPagadaPayload.motivo` validator). Operators can
 * grep this literal in `prod.anulaciones.motivo` to find
 * auto-annulments vs manual ones (HU-F8.3 reimpresion-anular
 * precedent uses its own copy).
 */
export const MOTIVO_AUTO_ANULACION_SALIDA =
  'Cliente no pagó - salida anulada automáticamente al cerrar modal';

export interface AnularSalidaInput {
  /** UUID of the `prod.salidas` row to annul. */
  uuid_salida: string;
}

export interface UseAnularSalidaNoPagadaReturn {
  trigger: (input: AnularSalidaInput) => Promise<unknown>;
  isMutating: boolean;
  error: ParkosHttpError | undefined;
  data: unknown;
}

async function handle401(uuid_salida: string): Promise<never> {
  useAuthStore.getState().clear();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('parkos:auth:cleared'));
  }
  throw new ParkosHttpError(
    401,
    '{"error":"unauthorized"}',
    POST_PATH_PREFIX + uuid_salida + POST_PATH_SUFFIX,
  );
}

async function mutateFn(
  _key: string,
  init: { arg: AnularSalidaInput },
): Promise<unknown> {
  const uuid_salida = init.arg.uuid_salida;
  const path = POST_PATH_PREFIX + uuid_salida + POST_PATH_SUFFIX;
  const body = {
    motivo: MOTIVO_AUTO_ANULACION_SALIDA,
  };
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST',
    path,
    body,
  });

  try {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    return await parkosFetch<unknown>(path, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    });
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 401) {
      return handle401(uuid_salida);
    }
    throw err;
  }
}

/**
 * `useAnularSalidaNoPagada()` — SWR mutation hook returning
 * `{ trigger, isMutating, error, data }`.
 *
 * `trigger({uuid_salida})` issues the canonical `POST
 * /api/v1/operacion/salidas/{uuid_salida}/anular-no-pagada` with
 * the audit motivo. Resolves with the newly-created
 * `AnulacionesRead` payload (the `uuid` of the new annulment row).
 *
 * 401 → `useAuthStore.clear()` + `parkos:auth:cleared` (preserved
 * invariant from F3.1 / `useRegistrarSalida.ts`).
 *
 * Doble trigger with the same `uuid_salida` yields the SAME
 * `Idempotency-Key` SHA-256 header — server-side
 * `IdempotencyKeyMiddleware` (F1.6) dedups the second POST and
 * returns the cached 201 (no duplicate annulation row).
 */
export function useAnularSalidaNoPagada(): UseAnularSalidaNoPagadaReturn {
  // SWRMutation key MUST be stable for `mutateFn` to resolve the
  // arg at call time. We use the prefix as the cache key; the
  // path param is part of the URL but NOT part of the SWR key
  // (SWR doesn't need it — `arg.uuid_salida` is the source of
  // truth and `mutateFn` re-builds the path on each call).
  const swr: SWRMutationResponse<unknown, Error, string, AnularSalidaInput> =
    useSWRMutation(POST_PATH_PREFIX + POST_PATH_SUFFIX, mutateFn);

  return {
    trigger: swr.trigger as UseAnularSalidaNoPagadaReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as ParkosHttpError | undefined,
    data: swr.data,
  };
}
