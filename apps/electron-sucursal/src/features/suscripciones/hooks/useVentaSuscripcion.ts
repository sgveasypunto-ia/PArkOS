/**
 * `useVentaSuscripcion.ts` — SWR mutation hook for
 * `POST /api/v1/clientes/venta-suscripcion` (HU-F9.1, REQ-OPS-177
 * + REQ-OPS-179).
 *
 * Composition (mirrors `useRegistrarSalida.ts` F7.2 + F8.1
 * `useRegistrarPago.ts` precedent verbatim):
 *   - `parkosFetch` for the canonical wire transport (F2.2
 *     auth/retry).
 *   - `buildIdempotencyKey` (features/operacion/lib/idempotency.ts
 *     — F7.2) for the SHA-256 RFC 8785 closure header
 *     (DEC-SUC-04 + DEC-IDEM-01 reuse from F1.6).
 *   - `VentaSuscripcionReadSchema` (api/ventaSuscripcionApi.ts)
 *     for the response parse.
 *   - `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *     event on 401 (preserved F3.1 invariant from REQ-OPS-107..110;
 *     mirrors `useRegistrarSalida.ts` + `useRegistrarPago.ts`).
 *
 * The 422 error mapping is the F9.1-specific value-add: 3 backend
 * error codes (`suscripcion_duplicada_placa`,
 * `tipo_vehiculo_incompatible`, `cantidad_maxima_excedida`)
 * surface as typed subclasses so wizard step 2 can render the
 * inline message with `instanceof` discrimination (REQ-OPS-179).
 *
 * The previous stub at `useSuscripcionesList.ts:80-98` was MOVED
 * here per REQ-OPS-177 drift (F9.2 file stays read-only SWR query;
 * the mutation has its own dedicated module — single responsibility).
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { buildIdempotencyKey } from '../../operacion/lib/idempotency';
import {
  POST_VENTA_SUSCRIPCION_PATH,
  VentaSuscripcionReadSchema,
  type VentaSuscripcionCreate,
  type VentaSuscripcionRead,
} from '../api/ventaSuscripcionApi';

export type { VentaSuscripcionCreate, VentaSuscripcionRead } from '../api/ventaSuscripcionApi';
export {
  VentaSuscripcionDuplicatePlateError,
  VentaSuscripcionTipoIncompatibleError,
  VentaSuscripcionCantidadMaximaError,
} from './ventaSuscripcionErrors';

/**
 * Typed errors for the 3 backend 422 codes (REQ-OPS-179). Wizard
 * step 2 uses `instanceof` discrimination to render the inline
 * message. These mirror the F1.12 backend typed-error bodies.
 */
import {
  VentaSuscripcionDuplicatePlateError,
  VentaSuscripcionTipoIncompatibleError,
  VentaSuscripcionCantidadMaximaError,
} from './ventaSuscripcionErrors';

export interface UseVentaSuscripcionReturn {
  trigger: (input: VentaSuscripcionCreate) => Promise<VentaSuscripcionRead>;
  isMutating: boolean;
  error:
    | ParkosHttpError
    | VentaSuscripcionDuplicatePlateError
    | VentaSuscripcionTipoIncompatibleError
    | VentaSuscripcionCantidadMaximaError
    | undefined;
  data: VentaSuscripcionRead | undefined;
}

async function handle401(): Promise<never> {
  useAuthStore.getState().clear();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('parkos:auth:cleared'));
  }
  throw new ParkosHttpError(
    401,
    '{"error":"unauthorized"}',
    POST_VENTA_SUSCRIPCION_PATH,
  );
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
 * live 2026-09-24 while validating HU-F9.2 realineada (the very first
 * time `POST /clientes/venta-suscripcion` was ever reachable over real
 * HTTP -- a separate double-prefix routing bug made it 404 forever
 * before that fix): reading `parsed.error` directly always returned
 * `undefined`, so every 422 (suscripcion_duplicada_placa,
 * tipo_vehiculo_incompatible, cantidad_maxima_excedida) silently fell
 * through to the generic `ParkosHttpError` instead of its typed
 * subclass, since HU-F1.12 shipped. Falls back to the top-level object
 * for robustness in case a future endpoint ever returns an unwrapped body.
 */
function parseBackendErrorBody(body: string): BackendErrorBody | null {
  try {
    const parsed = JSON.parse(body) as { detail?: BackendErrorBody } & BackendErrorBody;
    return parsed.detail ?? parsed;
  } catch {
    return null;
  }
}

/**
 * SWR fetcher — synchronous-looking wrapper around the POST. Uses
 * SWR's mutation hook to expose `isMutating` for the wizard Confirm
 * button disable (REQ-OPS-152 UI in-flight disable precedent) and
 * to integrate with the existing `parkosFetch` retry pipeline.
 */
async function mutateFn(
  _key: string,
  init: { arg: VentaSuscripcionCreate },
): Promise<VentaSuscripcionRead> {
  const body = init.arg;
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST',
    path: POST_VENTA_SUSCRIPCION_PATH,
    body,
  });

  try {
    const raw = await postVentaWithIdempotency(body, idempotencyKey);
    return VentaSuscripcionReadSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError) {
      if (err.status === 401) {
        return handle401();
      }
      if (err.status === 422) {
        const parsed = parseBackendErrorBody(err.body);
        const code = parsed?.error;
        if (code === 'suscripcion_duplicada_placa') {
          throw new VentaSuscripcionDuplicatePlateError(parsed?.placa ?? '');
        }
        if (code === 'tipo_vehiculo_incompatible') {
          throw new VentaSuscripcionTipoIncompatibleError(
            parsed?.tipos_encontrados ?? [],
          );
        }
        if (code === 'cantidad_maxima_excedida') {
          throw new VentaSuscripcionCantidadMaximaError(
            parsed?.cantidad_maxima_vehiculos ?? 0,
          );
        }
      }
    }
    throw err;
  }
}

/**
 * Thin wrapper around `parkosFetch` that forwards the explicit
 * `Idempotency-Key` header (the public API surface relies on
 * `parkosFetch`'s internal hash, but explicit forwarding documents
 * the contract at the call site — same pattern as F7.2
 * `postSalidaWithIdempotency`).
 */
async function postVentaWithIdempotency(
  body: VentaSuscripcionCreate,
  idempotencyKey: string,
): Promise<unknown> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  return parkosFetch<unknown>(POST_VENTA_SUSCRIPCION_PATH, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  });
}

/**
 * `useVentaSuscripcion()` — SWR mutation hook returning
 * `{ trigger, isMutating, error, data }`.
 *
 * `trigger({cliente, placas, uuid_tipo_subscripcion, fecha_inicio_cobertura, cobrar_ahora, medio_pago?})`
 * issues the canonical POST and resolves with the parsed
 * `VentaSuscripcionRead` payload.
 *
 * 401 → `useAuthStore.clear()` + `parkos:auth:cleared` (preserved
 * F3.1 invariant).
 *
 * 422 → typed subclass for the 3 backend error codes (mirror
 * F1.12 `SubscripcionDuplicadaPlacaError`, `TipoVehiculoIncompatibleError`,
 * `CantidadMaximaExcedidaError`).
 *
 * Doble trigger with the same body yields the SAME `Idempotency-Key`
 * header — server-side `IdempotencyKeyMiddleware` (F1.6) dedups.
 */
export function useVentaSuscripcion(): UseVentaSuscripcionReturn {
  const swr: SWRMutationResponse<VentaSuscripcionRead, Error, string, VentaSuscripcionCreate> =
    useSWRMutation(POST_VENTA_SUSCRIPCION_PATH, mutateFn);

  return {
    trigger: swr.trigger as UseVentaSuscripcionReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as UseVentaSuscripcionReturn['error'],
    data: swr.data,
  };
}
