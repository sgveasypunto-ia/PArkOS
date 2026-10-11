/**
 * `tarifasApi.ts` — HTTP client for the admin Tarifa CRUD UI (PR-D).
 *
 * Endpoints consumed (mounted on `api_admin` per `api/v1/__init__.py`):
 *
 * - `GET    /api/v1/empresa/tarifas-sucursal?limit=…`           — list vigente
 * - `GET    /api/v1/empresa/tarifas-sucursal/by-key?…`         — by-key history
 * - `GET    /api/v1/empresa/tarifas-sucursal/{uuid}`           — current row
 * - `POST   /api/v1/empresa/tarifas-sucursal`                  — create (single modalidad)
 * - `POST   /api/v1/empresa/tarifas-sucursal/batch`            — atomic batch (HU-tarifas-batch)
 * - `PUT    /api/v1/empresa/tarifas-sucursal/{uuid}`           — close+insert update
 *
 * All bi-temporal semantics (overlap guard, sucursal-inmutable guard,
 * `vigente_desde` Carril B boundary) live in the backend — PR-C v2.
 * The frontend surfaces typed errors (`TarifaOverlapError`,
 * `TarifaSucursalInmutableError`, `TarifaConflictError`,
 * `TarifaValidationError`) so the form layer can render operator-readable
 * messages instead of raw Zod JSON or generic 4xx/5xx.
 */
import type { ZodError } from 'zod';

import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  tarifaBackendCreateSchema,
  tarifaBatchCreateSchema,
  tarifaBatchResponseSchema,
  tarifaOverlapErrorSchema,
  tarifaReadArraySchema,
  tarifaReadListEnvelopeSchema,
  tarifaReadSchema,
  tarifaSucursalInmutableErrorSchema,
  tarifaUpdateSchema,
  type Tarifa,
  type TarifaBackendCreateInput,
  type TarifaBatchCreateInput,
  type TarifaCreateInput,
  type TarifaUpdateInput,
} from './tarifaSchema';

export type {
  Tarifa,
  TarifaCreateInput,
  TarifaUpdateInput,
  TarifaBackendCreateInput,
  TarifaBatchCreateInput,
};

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

const getHeaders = {
  Accept: 'application/json',
};

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `tarifasApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export class TarifaOverlapError extends Error {
  readonly conflictingUuid: string;
  readonly conflictingVigenteDesde: string | null;
  readonly conflictingVigenteHasta: string | null;

  constructor(body: unknown) {
    const parsed = tarifaOverlapErrorSchema.safeParse(body);
    if (!parsed.success) {
      super('Solapamiento con una tarifa existente (UUID no disponible)');
      this.name = 'TarifaOverlapError';
      this.conflictingUuid = '';
      this.conflictingVigenteDesde = null;
      this.conflictingVigenteHasta = null;
      return;
    }
    super(
      `La nueva ventana se solapa con la tarifa ${parsed.data.detail.conflicting_uuid} (vigente desde ${parsed.data.detail.conflicting_vigente_desde ?? '?'})`,
    );
    this.name = 'TarifaOverlapError';
    this.conflictingUuid = parsed.data.detail.conflicting_uuid;
    this.conflictingVigenteDesde = parsed.data.detail.conflicting_vigente_desde;
    this.conflictingVigenteHasta = parsed.data.detail.conflicting_vigente_hasta;
  }
}

export class TarifaSucursalInmutableError extends Error {
  readonly uuid: string;
  readonly existingSucursal: string;
  readonly attemptedSucursal: string;

  constructor(body: unknown) {
    const parsed = tarifaSucursalInmutableErrorSchema.safeParse(body);
    if (!parsed.success) {
      super('La sucursal de la tarifa no puede cambiarse');
      this.name = 'TarifaSucursalInmutableError';
      this.uuid = '';
      this.existingSucursal = '';
      this.attemptedSucursal = '';
      return;
    }
    super(
      `La tarifa pertenece a la sucursal ${parsed.data.detail.existing_sucursal}; no se puede mover a ${parsed.data.detail.attempted_sucursal}`,
    );
    this.name = 'TarifaSucursalInmutableError';
    this.uuid = parsed.data.detail.uuid;
    this.existingSucursal = parsed.data.detail.existing_sucursal;
    this.attemptedSucursal = parsed.data.detail.attempted_sucursal;
  }
}

/**
 * Local Zod-validation failure.
 *
 * Raised when ``createTarifa`` / ``updateTarifa`` / ``createTarifaBatch``
 * run the payload through their backend Zod schema BEFORE the HTTP
 * round-trip and the schema rejects (e.g. the FE form handed us a
 * ``valor='0'`` because the page's ``onSubmit`` swallowed a null).
 *
 * Crucially, this is the FIX for the chrome-devtools bug where the
 * operator saw a raw Zod JSON string in the alert:
 *   ``[ { "code": "custom", "message": "...", "path": ["valor"] } ]``
 * The form layer now receives a typed error with a structured
 * ``issues`` array (one entry per failing field) that it can render
 * per-field via RHF's ``setError`` (HU-tarifas-batch).
 */
export class TarifaValidationError extends Error {
  readonly issues: ReadonlyArray<{ path: string; message: string }>;

  constructor(zodError: ZodError) {
    super('Validación del formulario');
    this.name = 'TarifaValidationError';
    this.issues = zodError.issues.map((issue) => ({
      path: issue.path.join('.'),
      message: issue.message,
    }));
  }
}

/**
 * Conflict raised by the DB (UK01, FK) that slipped past the
 * ``assert_no_overlap`` pre-check.
 *
 * PR1 backend maps ``VersioningConflictError`` (from
 * ``close_and_insert``'s flush) to HTTP 409 with the canonical
 * ``tarifa_overlap`` shape. The FE distinguishes this from the
 * pre-check overlap (``TarifaOverlapError``) via the optional
 * ``constraint`` field, which the pre-check path does not populate
 * (it has no constraint info because the rejection happens before
 * the INSERT). When ``constraint`` is set, the FE can show a more
 * specific message ("unique key violation: tarifas_sucursal_uk01")
 * to help the operator self-diagnose.
 */
export class TarifaConflictError extends Error {
  readonly constraint: string | null;
  readonly conflictingUuid: string | null;
  readonly conflictingVigenteDesde: string | null;

  constructor(body: unknown) {
    // Body is FastAPI's ``{ detail: { error, conflicting_uuid, ..., constraint } }``
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? (body as { detail: Record<string, unknown> }).detail
        : null;
    const errCode = detail && typeof detail === 'object' ? detail.error : null;
    const constraint =
      detail && typeof detail === 'object' ? (detail.constraint as string | null) : null;
    const conflictingUuid =
      detail && typeof detail === 'object'
        ? (detail.conflicting_uuid as string | null)
        : null;
    const conflictingVigenteDesde =
      detail && typeof detail === 'object'
        ? (detail.conflicting_vigente_desde as string | null)
        : null;
    if (errCode === 'tarifa_overlap') {
      super(
        constraint
          ? `Conflicto con una tarifa existente (constraint: ${constraint})`
          : 'Conflicto con una tarifa existente',
      );
    } else {
      super('Conflicto con una tarifa existente');
    }
    this.name = 'TarifaConflictError';
    this.constraint = constraint ?? null;
    this.conflictingUuid = conflictingUuid ?? null;
    this.conflictingVigenteDesde = conflictingVigenteDesde ?? null;
  }
}

/**
 * Translate a 409/422 response body into the typed error.
 *
 * PR-C v2 returns the typed shape; any other error body falls through
 * to the generic error path. This is a defense-in-depth wrapper so
 * the form layer can `instanceof TarifaOverlapError` without parsing.
 *
 * The 422 branch covers TWO distinct backend responses:
 * - ``sucursal_inmutable`` (PUT body changed the branch) →
 *   ``TarifaSucursalInmutableError``
 * - ``tarifa_batch_modalidades_incompletas`` (batch with wrong items) →
 *   a fresh ``TarifaBatchModalidadesIncompletasError`` (handled below
 *   by the ``mapError`` in Tarifas.tsx via the alert message).
 * The 409 branch covers ``tarifa_overlap`` (the typed shape) and
 * ``TarifaConflictError`` (the DB-layer race, HU-tarifas-batch).
 */
function throwTypedError(res: Response, bodyText: string): never {
  if (res.status === 409) {
    try {
      // The PR1 backend always returns the tarifa_overlap shape on
      // 409. The pre-check path (``assert_no_overlap``) and the DB
      // race (``VersioningConflictError``) both use it. Distinguish
      // by the optional ``constraint`` field.
      throw new TarifaConflictError(JSON.parse(bodyText));
    } catch (err) {
      // If the body is not JSON or the parse above failed, fall back
      // to a generic Error so the caller still knows the request
      // failed (status 409, body present). The original 409 typed
      // error is preserved when the parse succeeds.
      if (err instanceof TarifaConflictError) throw err;
      throw new Error(`tarifasApi: 409 ${bodyText.slice(0, 200)}`);
    }
  }
  if (res.status === 422) {
    try {
      const parsed = JSON.parse(bodyText);
      const detail = parsed?.detail;
      // The batch-endpoint 422 carries a custom error code; the
      // singleton-endpoint 422 carries sucursal_inmutable. Pick the
      // right typed error or fall back to a generic one.
      if (
        detail &&
        typeof detail === 'object' &&
        'error' in detail &&
        (detail as { error: unknown }).error === 'tarifa_batch_modalidades_incompletas'
      ) {
        throw new Error(
          `La batch debe incluir las 4 modalidades canónicas (hora, fracción, plena, nocturna) exactamente una vez cada una.`,
        );
      }
      throw new TarifaSucursalInmutableError(parsed);
    } catch (err) {
      if (err instanceof TarifaSucursalInmutableError) throw err;
      if (err instanceof Error && err.name) throw err;
      throw new Error(`tarifasApi: 422 ${bodyText.slice(0, 200)}`);
    }
  }
  throw new Error(`tarifasApi: ${res.status}: ${bodyText.slice(0, 200)}`);
}

async function fetchJsonOrTyped(input: string, init: ParkosFetchInit): Promise<unknown> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throwTypedError(res, body);
  }
  return (await res.json()) as unknown;
}

export interface ListTarifasOpts {
  limit?: number;
}

export async function listTarifas(opts: ListTarifasOpts = {}): Promise<Tarifa[]> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/empresa/tarifas-sucursal${qs ? `?${qs}` : ''}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: getHeaders });
  return tarifaReadListEnvelopeSchema.parse(raw).items;
}

export interface ByKeyOpts {
  sucursal: string;
  tipo_vehiculo?: string | null;
  tipo_tarifa?: string | null;
}

/**
 * Walk the bi-temporal version chain by business key. PR-C v2 closes
 * the gap where ``GET /{uuid}/history`` filters by uuid and misses the
 * close+insert fresh-UUID case — the by-key endpoint fixes that.
 */
export async function listTarifasByKey(opts: ByKeyOpts): Promise<Tarifa[]> {
  const params = new URLSearchParams({ sucursal: opts.sucursal });
  if (opts.tipo_vehiculo !== undefined && opts.tipo_vehiculo !== null) {
    params.set('tipo_vehiculo', opts.tipo_vehiculo);
  }
  if (opts.tipo_tarifa !== undefined && opts.tipo_tarifa !== null) {
    params.set('tipo_tarifa', opts.tipo_tarifa);
  }
  const url = `/api/v1/empresa/tarifas-sucursal/by-key?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: getHeaders });
  // `by-key` returns a bare array, not the `{items, next_cursor}`
  // envelope the plain list endpoint uses (QA batch tarifas/cupos:
  // parsing it with the envelope schema threw on every call, silently
  // swallowed by SWR into `versiones: []` -- "Ver histórico" always
  // showed "Sin versiones registradas." even with real version rows).
  return tarifaReadArraySchema.parse(raw);
}

export async function getTarifa(uuid: string): Promise<Tarifa> {
  const raw = await fetchJsonOrTyped(`/api/v1/empresa/tarifas-sucursal/${uuid}`, {
    method: 'GET',
    headers: getHeaders,
  });
  return tarifaReadSchema.parse(raw);
}

export async function createTarifa(input: TarifaBackendCreateInput): Promise<Tarifa> {
  // Validate BEFORE the HTTP call so a malformed payload (e.g. the FE
  // page handed us a null ``valor``) surfaces as a typed
  // ``TarifaValidationError`` with a structured ``issues`` array the
  // form layer can render per-field. Throwing the raw ZodError
  // (``.parse``) would leak its stringified message into the alert
  // (chrome-devtools bug, 2026-10-10).
  const parsed = tarifaBackendCreateSchema.safeParse(input);
  if (!parsed.success) {
    throw new TarifaValidationError(parsed.error);
  }
  const raw = await fetchJsonOrTyped('/api/v1/empresa/tarifas-sucursal', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed.data),
  });
  return tarifaReadSchema.parse(raw);
}

export async function updateTarifa(
  uuid: string,
  input: TarifaUpdateInput,
): Promise<Tarifa> {
  // Same defense as ``createTarifa`` -- typed validation error
  // instead of raw ZodError in the alert.
  const parsed = tarifaUpdateSchema.safeParse(input);
  if (!parsed.success) {
    throw new TarifaValidationError(parsed.error);
  }
  const raw = await fetchJsonOrTyped(`/api/v1/empresa/tarifas-sucursal/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(parsed.data),
  });
  return tarifaReadSchema.parse(raw);
}

/**
 * Atomic batch create (HU-tarifas-batch, PR2 frontend).
 *
 * One HTTP round-trip, 1 idempotency-key, 4 ``tarifas_sucursal``
 * rows created in a single transaction. The backend's
 * ``POST /api/v1/empresa/tarifas-sucursal/batch`` validates the 4
 * canonical modalidades and rolls back atomically on any failure.
 *
 * Rejections:
 * - ``TarifaValidationError`` -- local Zod schema rejected the
 *   payload (e.g. items with ``valor <= 0``) BEFORE the HTTP call.
 * - 422 from the backend (Pydantic constraint violation that
 *   escaped the FE schema, or wrong modality count) -- rendered as
 *   a generic 422 by ``throwTypedError``.
 * - 409 ``TarifaConflictError`` -- any item's overlap pre-check or
 *   the DB-level UK01 race fires.
 */
export async function createTarifaBatch(
  input: TarifaBatchCreateInput,
): Promise<Tarifa[]> {
  const parsed = tarifaBatchCreateSchema.safeParse(input);
  if (!parsed.success) {
    throw new TarifaValidationError(parsed.error);
  }
  const raw = await fetchJsonOrTyped('/api/v1/empresa/tarifas-sucursal/batch', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed.data),
  });
  const envelope = tarifaBatchResponseSchema.parse(raw);
  return envelope.items;
}
