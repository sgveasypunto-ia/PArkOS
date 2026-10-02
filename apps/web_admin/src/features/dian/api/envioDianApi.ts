/**
 * `envioDianApi.ts` — HTTP client for the HU-F20.5 "monitor de envíos
 * DIAN" admin surface.
 *
 * Endpoints consumed:
 *   - `GET /api/v1/envio-dian?uuid_sucursal=&estado=&cursor=&limit=`
 *     (`dian/cloud_router.py::list_envio_dian`, HU-F13.4, already real).
 *     Returns `{items: EnvioDianRead[], next_cursor: string|null}`.
 *
 *   - `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar`
 *     (`api/v1/facturacion.py::retry_envio_dian`, HU-F1.10, already real
 *     and merged — this module does NOT reimplement any backend logic).
 *
 *     DRIFT vs. the HU-F20.5 task brief: the brief assumed "retry" meant
 *     `POST /api/v1/envio-dian` (the generic workflow-transition endpoint
 *     in `cloud_router.py`) reusing a client-supplied `uuid_envio_padre`.
 *     That assumption does not hold against the real backend:
 *       1. That endpoint's `estado` defaults to `"enviado"` for a chained
 *          insert and validates `parent.estado -> new_estado` against
 *          `repo.workflow.STATE_MACHINES['envio_dian']`
 *          (`{pendiente: [enviado], enviado: [ack, error], ack: [],
 *          error: []}`). A "rechazado" parent (a dispatcher-written
 *          state, OUTSIDE that state machine's own vocabulary) resolves
 *          to `allowed = []` in `repo/workflow.py::append_transition`,
 *          so ANY chained insert off a rejected envio raises
 *          `IllegalTransitionError` — uncaught in `create_envio_dian`,
 *          surfacing as a 500, not a usable retry.
 *       2. A DIFFERENT, dedicated, already-shipped endpoint exists for
 *          this exact use case: `POST
 *          /api/v1/facturacion/factura-electronica/{uuid}/reintentar`
 *          (`uuid` = `uuid_factura_electronica`, NOT the envio's own
 *          uuid). It resolves the chain tip SERVER-SIDE
 *          (`buscar_envio_dian_chain_tip`), validates
 *          `aceptado -> 409 reintento_no_permitido`,
 *          `pendiente -> 409 envio_dian_already_pending`, and proceeds
 *          (inserting a new `estado='pendiente'` row chained via
 *          `uuid_envio_padre=<tip.uuid>`) for `rechazado`/`enviado`/no-tip.
 *          This is the actual, real, already-working "retry" mechanism —
 *          confirmed by reading `api/v1/facturacion.py` AND its existing
 *          branch-side consumer, `apps/electron-sucursal/.../useReintentarFE.ts`
 *          (HU-F8.2), which calls this exact path.
 *
 *     Idempotency-Key note (RIESGO-ADM-09): the task brief assumed the
 *     backend never validates this header. Two things are both true and
 *     worth being precise about:
 *       - This specific endpoint (`retry_envio_dian`) does NOT itself
 *         read or special-case `Idempotency-Key` — confirmed by reading
 *         its full 8-step body.
 *       - BUT `IdempotencyKeyMiddleware` (`api/middleware.py`) IS
 *         globally mounted on the admin app
 *         (`api_admin_main/app.py:78`) and replays a cached response for
 *         any repeated `(issuer, Idempotency-Key)` pair within 24h — AND
 *         `parkosFetch`/`parkosFetchRaw` (`@parkos/ui-kit/fetch`)
 *         auto-attaches `Idempotency-Key: sha256(method|url|body)` to
 *         EVERY mutational request unless `skipIdempotencyKey` is passed
 *         (which this module never does). So a rapid double-click that
 *         hits this function twice with the same `uuidFacturaElectronica`
 *         (same URL, same empty body) DOES get deduplicated at the
 *         network+backend layer today, transparently. This is real
 *         protection the task brief's premise missed — see the HU-F20.5
 *         report for the full citation trail. It is still real-world
 *         prudent to ALSO disable the UI button synchronously on first
 *         click (defense in depth against any future
 *         `skipIdempotencyKey` use, a slow click outside the 24h TTL
 *         edge case, etc.) — `useRetryEnvioDian.ts` does that.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  envioDianReadListSchema,
  envioDianRetryReadSchema,
  type EnvioDianListQuery,
  type EnvioDianReadList,
  type EnvioDianRetryRead,
} from './envioDianSchema';

const LIST_PATH = '/api/v1/envio-dian';
const RETRY_PATH_PREFIX = '/api/v1/facturacion/factura-electronica';

function detailOf(bodyText: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(bodyText) as unknown;
    if (typeof parsed === 'object' && parsed !== null && 'detail' in parsed) {
      const detail = (parsed as { detail?: unknown }).detail;
      if (typeof detail === 'object' && detail !== null) {
        return detail as Record<string, unknown>;
      }
    }
  } catch {
    // Not JSON (or shape mismatch) -- callers fall back to a static message.
  }
  return null;
}

/** 404 `factura_electronica_no_encontrada`. */
export class FacturaElectronicaNoEncontradaError extends Error {
  constructor(uuidFacturaElectronica: string) {
    super(`La factura electrónica ${uuidFacturaElectronica} no existe.`);
    this.name = 'FacturaElectronicaNoEncontradaError';
  }
}

/** 403 `tenant_scope_violation`. */
export class DianTenantScopeViolationError extends Error {
  constructor() {
    super('No tenés acceso a esta factura electrónica en este tenant.');
    this.name = 'DianTenantScopeViolationError';
  }
}

/**
 * 409 `reintento_no_permitido` — the chain tip is `aceptado` (DIAN
 * already confirmed the document); retrying is nonsensical.
 */
export class ReintentoNoPermitidoError extends Error {
  public readonly estadoActual: string | null;
  constructor(estadoActual: string | null) {
    super('Esta factura electrónica ya fue aceptada por la DIAN; no se puede reintentar.');
    this.name = 'ReintentoNoPermitidoError';
    this.estadoActual = estadoActual;
  }
}

/**
 * 409 `envio_dian_already_pending` — a prior attempt is still in flight
 * (rapid-retry guard, server-side authority — see `facturacion.py` step 5).
 */
export class EnvioDianAlreadyPendingError extends Error {
  public readonly uuidEnvioPendiente: string | null;
  constructor(uuidEnvioPendiente: string | null) {
    super('Ya hay un envío DIAN pendiente para esta factura electrónica.');
    this.name = 'EnvioDianAlreadyPendingError';
    this.uuidEnvioPendiente = uuidEnvioPendiente;
  }
}

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `envioDianApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

/**
 * `GET /api/v1/envio-dian` — cursor-paginated listing. `estado` (when
 * provided) MUST be one of `ENVIO_DIAN_ESTADOS` or the BE replies 422
 * `invalid_estado` — callers only ever pass tab values from that same
 * const, so this never happens in practice.
 */
export async function fetchEnvioDianList(query: EnvioDianListQuery): Promise<EnvioDianReadList> {
  const params = new URLSearchParams();
  if (query.uuid_sucursal) params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.estado) params.set('estado', query.estado);
  if (query.cursor) params.set('cursor', query.cursor);
  params.set('limit', String(query.limit));

  const url = `${LIST_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return envioDianReadListSchema.parse(raw);
}

/**
 * `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` — the
 * REAL retry mechanism (see this module's docblock). `uuidFacturaElectronica`
 * is `EnvioDianRead.uuid_factura_electronica` of the rejected envio, NOT
 * the envio's own `uuid`.
 *
 * No request body (the BE computes the chain tip itself); no manual
 * `Idempotency-Key` handling here -- `parkosFetchRaw` already attaches
 * one automatically (see this module's docblock for why that's real
 * protection, not a no-op).
 */
export async function retryEnvioDian(uuidFacturaElectronica: string): Promise<EnvioDianRetryRead> {
  const res = await parkosFetchRaw(`${RETRY_PATH_PREFIX}/${uuidFacturaElectronica}/reintentar`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  if (res.ok) {
    return envioDianRetryReadSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 404) throw new FacturaElectronicaNoEncontradaError(uuidFacturaElectronica);
  if (res.status === 403) throw new DianTenantScopeViolationError();
  if (res.status === 409) {
    const detail = detailOf(bodyText);
    const code = typeof detail?.error === 'string' ? detail.error : null;
    if (code === 'reintento_no_permitido') {
      const estadoActual = typeof detail?.estado_actual === 'string' ? detail.estado_actual : null;
      throw new ReintentoNoPermitidoError(estadoActual);
    }
    if (code === 'envio_dian_already_pending') {
      const uuidEnvioPendiente =
        typeof detail?.uuid_envio_pendiente === 'string' ? detail.uuid_envio_pendiente : null;
      throw new EnvioDianAlreadyPendingError(uuidEnvioPendiente);
    }
  }
  throw new Error(
    `envioDianApi: POST ${RETRY_PATH_PREFIX}/${uuidFacturaElectronica}/reintentar -> ${res.status}: ${bodyText.slice(0, 200)}`,
  );
}
