/**
 * `anulacionesApi.ts` — HTTP client for the HU-F20.3 admin "anulaciones"
 * surface.
 *
 * Endpoints consumed:
 *   - `GET /api/v1/workflows/anulaciones?cursor=&limit=` (generic
 *     factory-mounted list, unchanged by HU-F20.3 — only `cursor`/`limit`
 *     query params exist).
 *   - `GET /api/v1/workflows/anulaciones/{uuid}` (generic factory
 *     single-item read, current/only version of that row) — used by
 *     `AnulacionDetalle` for direct navigation / deep-link / refresh, and
 *     by `useAnulacionChain` to walk `uuid_anulacion_padre` backwards.
 *   - `POST /api/v1/workflows/anulaciones/{uuid}/transicion` — HU-F20.3,
 *     NEW. `{uuid}` is whatever uuid the UI navigated to for this record
 *     (route param); the backend resolves the actual current tip of the
 *     chain internally, same `uuid` used throughout the UI for a given
 *     record (mirrors `descartarAlerta`'s contract).
 *
 * Why `parkosFetchRaw` (not SWR inside this file): mirrors
 * `alertasApi.ts` — the data hooks own the SWR cache key + revalidation,
 * this file stays a pure fetch layer.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  anulacionReadSchema,
  anulacionesListResponseSchema,
  type AnulacionEstado,
  type AnulacionRead,
  type AnulacionesListQuery,
  type AnulacionesListResponse,
} from './anulacionesSchema';

const BASE_PATH = '/api/v1/workflows/anulaciones';

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

/**
 * Every error response on this surface wraps its discriminator payload
 * inside FastAPI's standard `{"detail": {...}}` envelope (verified
 * against the real backend contract handed down with this task) —
 * mirrors `alertasApi.ts::detailOf`.
 */
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

/** 404 `anulacion_not_found`. */
export class AnulacionNotFoundError extends Error {
  constructor(uuid: string) {
    super(`La anulación ${uuid} no existe o ya no está disponible.`);
    this.name = 'AnulacionNotFoundError';
  }
}

/** 403 `tenant_scope_violation`. */
export class TenantScopeViolationError extends Error {
  constructor() {
    super('No tenés acceso a esta anulación en este tenant.');
    this.name = 'TenantScopeViolationError';
  }
}

/** 403 `permission_denied` -- `reason` carries the BE's `detail` string (e.g. `aprobar_anulacion`). */
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

/**
 * 409 `illegal_transition` -- the chain's CURRENT tip doesn't admit the
 * requested destination `estado` (e.g. another actor already transitioned
 * it, or the UI raced an already-terminal chain).
 */
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
        `La anulación ${uuid} no admite esa transición en su estado actual${
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
      `anulacionesApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchAnulaciones(
  query: AnulacionesListQuery,
): Promise<AnulacionesListResponse> {
  const params = new URLSearchParams();
  params.set('limit', String(query.limit));
  if (query.cursor) params.set('cursor', query.cursor);

  const raw = await fetchJson<unknown>(`${BASE_PATH}?${params.toString()}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return anulacionesListResponseSchema.parse(raw);
}

/** `GET /api/v1/workflows/anulaciones/{uuid}` -- current/only version of that row. */
export async function fetchAnulacion(uuid: string): Promise<AnulacionRead> {
  const res = await parkosFetchRaw(`${BASE_PATH}/${uuid}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (res.ok) {
    return anulacionReadSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 404) throw new AnulacionNotFoundError(uuid);
  if (res.status === 403) throw new TenantScopeViolationError();
  throw new Error(`anulacionesApi: GET ${BASE_PATH}/${uuid} -> ${res.status}: ${bodyText.slice(0, 200)}`);
}

/**
 * `POST /api/v1/workflows/anulaciones/{uuid}/transicion` -- advances the
 * chain to `estado`. Response is the NEW row (different `uuid` than the
 * one posted to), same "insert-new-row-per-transition" contract as
 * `descartarAlerta`.
 */
export async function transicionarAnulacion(
  uuid: string,
  estado: AnulacionEstado,
  motivo: string,
): Promise<AnulacionRead> {
  const res = await parkosFetchRaw(`${BASE_PATH}/${uuid}/transicion`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ estado, motivo }),
  });
  if (res.ok) {
    return anulacionReadSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 404) throw new AnulacionNotFoundError(uuid);
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
    `anulacionesApi: POST ${BASE_PATH}/${uuid}/transicion -> ${res.status}: ${bodyText.slice(0, 200)}`,
  );
}
