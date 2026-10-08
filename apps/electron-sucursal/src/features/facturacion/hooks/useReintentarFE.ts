/**
 * `useReintentarFE.ts` — SWR mutation hook for
 * `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar`
 * (HU-F8.2, REQ-OPS-168 + REQ-OPS-169).
 *
 * Composition mirrors `useRegistrarSalida.ts` (F7.2) and
 * `useRegistrarPago.ts` (F8.1):
 *   - `parkosFetch` for the canonical wire transport (F2.2
 *     auth/retry).
 *   - `withActionIdempotencyKey` (F7.2 lib/idempotency.ts) for the
 *     SHA-256 RFC 8785 closure header (DEC-SUC-04 + DEC-IDEM-01).
 *   - `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *     event on 401 (preserved F3.1 invariant — REQ-OPS-107..110).
 *   - `NumeracionAgotadaError` typed class on 409
 *     `numeracion_agotada` (F1.10 — range exhaustion; the ONLY FE
 *     error the UI surfaces per plan.md:1956).
 *   - `mutate('/facturacion/factura-electronica/{uuid}')` after
 *     201 so SWR resumes the 30s polling loop with the new chain
 *     tip (the new envio is `pendiente` — non-terminal per F1.10
 *     DEC-FE-04).
 *
 * F1.10 DEC-FE-02 + REQ-OPS-070 — the hook MUST NEVER UPDATE an
 * existing `envio_dian` row. Each `reintentar` POST creates a NEW
 * row chained via `uuid_envio_padre`. The renderer-side contract is
 * just "trigger → got 201 with new uuid_envio"; the append-only
 * invariant is enforced server-side.
 */
import useSWRMutation, { type SWRMutationResponse } from 'swr/mutation';
import { useCallback } from 'react';
import { useSWRConfig, type ScopedMutator } from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { withActionIdempotencyKey } from '../../operacion/lib/idempotency';

const POST_PATH_PREFIX = '/api/v1/facturacion/factura-electronica';

/**
 * Cached SWR key for the FE status poll — must match the key format
 * used by `useFacturaElectronica` so the cache mutation lands on the
 * right entry.
 */
const FE_CACHE_KEY_PREFIX = '/facturacion/factura-electronica';

/**
 * Typed error for 409 `numeracion_agotada` (F1.10 — `resolucion_facturacion`
 * range exhausted). The body shape is `{error: "numeracion_agotada"}`;
 * the page catches this class and renders the localized banner
 * pointing at the already-seeded `fe_numbering_exhausted` alerta.
 */
export class NumeracionAgotadaError extends Error {
  public readonly status = 409;
  public readonly code = 'numeracion_agotada';
  constructor() {
    super('numeracion_agotada');
    this.name = 'NumeracionAgotadaError';
  }
}

/**
 * Wire shape of the retry response. `uuid` identifies the retry REQUEST (an
 * `alerta` `dian_reintento_solicitado` filed for the cloud), NOT an
 * `envio_dian`: the cloud creates the new envio and it returns by pull.
 */
interface EnvioDianRetryWire {
  uuid: string;
  uuid_envio_padre: string;
}

export interface EnvioDianRetryRead {
  /** uuid of the retry request (alerta), never an envio_dian id. */
  uuid_solicitud: string;
  estado: 'pendiente';
  uuid_envio_padre: string;
}

export interface UseReintentarFEReturn {
  trigger: (uuidFe: string) => Promise<EnvioDianRetryRead>;
  isMutating: boolean;
  error: ParkosHttpError | NumeracionAgotadaError | undefined;
  data: EnvioDianRetryRead | undefined;
}

async function handle401(): Promise<never> {
  useAuthStore.getState().clear();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('parkos:auth:cleared'));
  }
  throw new ParkosHttpError(401, '{"error":"unauthorized"}', POST_PATH_PREFIX);
}

/**
 * SWR fetcher — POST `/reintentar` with Idempotency-Key SHA-256, then
 * revalidate the polling cache so the new chain tip (`pendiente`)
 * re-engages the 30s loop. Mirrors `useRegistrarSalida.ts:73-101`.
 */
async function mutateFn(
  _key: string,
  init: { arg: string },
  mutate: ScopedMutator,
): Promise<EnvioDianRetryRead> {
  const uuidFe = init.arg;
  const path = `${POST_PATH_PREFIX}/${uuidFe}/reintentar`;
  try {
    const { parkosFetch } = await import('@parkos/ui-kit/fetch');
    const raw = (await withActionIdempotencyKey(
      { method: 'POST', path, body: {} },
      (idempotencyKey) =>
        parkosFetch<unknown>(path, {
          method: 'POST',
          headers: {
            'Idempotency-Key': idempotencyKey,
          },
        }),
    )) as EnvioDianRetryWire;

    // REQ-OPS-169 — revalidate the polling cache so SWR resumes
    // `refreshInterval: 30_000` (the new chain tip is `pendiente`,
    // non-terminal). `mutate()` is awaited before `trigger()` returns
    // to avoid a stale `aceptado` flash (R1).
    await mutate(`${FE_CACHE_KEY_PREFIX}/${uuidFe}`);

    return {
      uuid_solicitud: raw.uuid,
      estado: 'pendiente',
      uuid_envio_padre: raw.uuid_envio_padre,
    };
  } catch (err) {
    if (err instanceof ParkosHttpError) {
      if (err.status === 401) {
        return handle401();
      }
      if (err.status === 409) {
        // F1.10 maps `resolucion_facturacion.rango_hasta` exhaustion
        // to `numeracion_agotada`; the page renders the localized
        // banner with `role="alert"` (WCAG 2.1 AA).
        throw new NumeracionAgotadaError();
      }
    }
    throw err;
  }
}

/**
 * `useReintentarFE()` — SWR mutation hook returning
 * `{ trigger, isMutating, error, data }`. `trigger(uuid_fe)` issues
 * `POST .../{uuid}/reintentar` and resolves with the new chain tip.
 *
 * 401 → `useAuthStore.clear()` + `parkos:auth:cleared` (F3.1 invariant).
 * 409 `numeracion_agotada` → `NumeracionAgotadaError` (the ONLY FE
 *   error the UI surfaces per plan.md:1956).
 * 201 → `mutate(cache)` re-engages polling + returns `{uuid_solicitud, estado:'pendiente', uuid_envio_padre}`.
 */
export function useReintentarFE(): UseReintentarFEReturn {
  // Cache-bound mutate: the SWR cache is scoped per operator session.
  const { mutate } = useSWRConfig();
  const fetcher = useCallback(
    (key: string, init: { arg: string }) => mutateFn(key, init, mutate),
    [mutate],
  );
  const swr: SWRMutationResponse<EnvioDianRetryRead, Error, string, string> =
    useSWRMutation(POST_PATH_PREFIX, fetcher);

  return {
    trigger: swr.trigger as UseReintentarFEReturn['trigger'],
    isMutating: swr.isMutating,
    error: swr.error as ParkosHttpError | NumeracionAgotadaError | undefined,
    data: swr.data,
  };
}
