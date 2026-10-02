/**
 * `reclamosApi.ts` — HTTP client for the HU-F20.3 admin "reclamos"
 * surface. Mirrors `anulacionesApi.ts` 1:1 (same conventions, same
 * error-class-per-status-discriminator pattern), substituting
 * `reclamo(s)` for `anulacion(es)`.
 *
 * Endpoints consumed:
 *   - `GET /api/v1/workflows/reclamos?cursor=&limit=`
 *   - `GET /api/v1/workflows/reclamos/{uuid}`
 *   - `POST /api/v1/workflows/reclamos/{uuid}/transicion`
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  reclamoReadSchema,
  reclamosListResponseSchema,
  type ReclamoEstado,
  type ReclamoRead,
  type ReclamosListQuery,
  type ReclamosListResponse,
} from './reclamosSchema';

const BASE_PATH = '/api/v1/workflows/reclamos';

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

/** Mirrors `anulacionesApi.ts::detailOf`. */
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

/** 404 `reclamo_not_found`. */
export class ReclamoNotFoundError extends Error {
  constructor(uuid: string) {
    super(`El reclamo ${uuid} no existe o ya no está disponible.`);
    this.name = 'ReclamoNotFoundError';
  }
}

/** 403 `tenant_scope_violation`. */
export class TenantScopeViolationError extends Error {
  constructor() {
    super('No tenés acceso a este reclamo en este tenant.');
    this.name = 'TenantScopeViolationError';
  }
}

/** 403 `permission_denied` -- `reason` carries the BE's `detail` string (e.g. `resolver_reclamo`). */
export class PermissionDeniedError extends Error {
  readonly reason: string | null;

  constructor(reason: string | null) {
    super(
      reason
        ? `No tenés permiso para realizar esta acción (${reason}).`
        : 'No tenés permiso para realizar esta acción.',
    );
    this.name = 'PermissionDeniedError';
    this.reason = reason;
  }
}

/** 409 `illegal_transition` -- the chain's CURRENT tip doesn't admit the requested destination `estado`. */
export class IllegalTransitionError extends Error {
  readonly estadoActual: string | null;
  readonly estadoSolicitado: string | null;

  constructor(uuid: string, detail: Record<string, unknown> | null) {
    const estadoActual = typeof detail?.estado_actual === 'string' ? detail.estado_actual : null;
    const estadoSolicitado =
      typeof detail?.estado_solicitado === 'string' ? detail.estado_solicitado : null;
    const msg = typeof detail?.detail === 'string' ? detail.detail : null;
    super(
      msg ??
        `El reclamo ${uuid} no admite esa transición en su estado actual${
          estadoActual ? ` (${estadoActual})` : ''
        }.`,
    );
    this.name = 'IllegalTransitionError';
    this.estadoActual = estadoActual;
    this.estadoSolicitado = estadoSolicitado;
  }
}

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `reclamosApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchReclamos(query: ReclamosListQuery): Promise<ReclamosListResponse> {
  const params = new URLSearchParams();
  params.set('limit', String(query.limit));
  if (query.cursor) params.set('cursor', query.cursor);

  const raw = await fetchJson<unknown>(`${BASE_PATH}?${params.toString()}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return reclamosListResponseSchema.parse(raw);
}

/** `GET /api/v1/workflows/reclamos/{uuid}` -- current/only version of that row. */
export async function fetchReclamo(uuid: string): Promise<ReclamoRead> {
  const res = await parkosFetchRaw(`${BASE_PATH}/${uuid}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (res.ok) {
    return reclamoReadSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 404) throw new ReclamoNotFoundError(uuid);
  if (res.status === 403) throw new TenantScopeViolationError();
  throw new Error(`reclamosApi: GET ${BASE_PATH}/${uuid} -> ${res.status}: ${bodyText.slice(0, 200)}`);
}

/**
 * `POST /api/v1/workflows/reclamos/{uuid}/transicion` -- advances the
 * chain to `estado`. Response is the NEW row (different `uuid` than the
 * one posted to).
 */
export async function transicionarReclamo(
  uuid: string,
  estado: ReclamoEstado,
  motivo: string,
): Promise<ReclamoRead> {
  const res = await parkosFetchRaw(`${BASE_PATH}/${uuid}/transicion`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ estado, motivo }),
  });
  if (res.ok) {
    return reclamoReadSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 404) throw new ReclamoNotFoundError(uuid);
  if (res.status === 409) throw new IllegalTransitionError(uuid, detailOf(bodyText));
  if (res.status === 403) {
    const detail = detailOf(bodyText);
    if (detail?.error === 'permission_denied') {
      throw new PermissionDeniedError(typeof detail.detail === 'string' ? detail.detail : null);
    }
    throw new TenantScopeViolationError();
  }
  if (res.status === 422) {
    const detail = detailOf(bodyText);
    const msg = typeof detail?.detail === 'string' ? detail.detail : null;
    throw new Error(`Datos inválidos para la transición${msg ? `: ${msg}` : '.'}`);
  }
  throw new Error(
    `reclamosApi: POST ${BASE_PATH}/${uuid}/transicion -> ${res.status}: ${bodyText.slice(0, 200)}`,
  );
}
