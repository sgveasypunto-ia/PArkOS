/**
 * `alertasApi.ts` — HTTP client for the HU-F19.5 admin "bandeja de
 * alertas" surface.
 *
 * Endpoints consumed:
 *   - `GET /api/v1/workflows/alerta?uuid_sucursal=&tipo_alerta=&estado=&severidad=&desde=&hasta=&cursor=&limit=`
 *     (HU-F19.5, hand-built list — see `alertasSchema.ts` module docblock
 *     for why the query param names don't match the generic
 *     `AlertaFilter`). Returns `{items: AlertaRead[], next_cursor: string|null}`.
 *   - `GET /api/v1/workflows/alerta/{uuid}` (generic factory single-item
 *     read, current version only) — used by `AlertaDetalle` for direct
 *     navigation / deep-link / refresh, and by `useAlertaChain` to walk
 *     `uuid_alerta_padre` backwards.
 *   - `POST /api/v1/workflows/alerta/{uuid}/descartar` — HU-F19.4, ALREADY
 *     REAL and merged into `dev` (PR #64). Reused as-is: this module adds
 *     a typed client for it, it does NOT reimplement any backend logic.
 *     `observaciones` is mandatory; 409 means the alert was already
 *     `resuelta` (terminal state — `STATE_MACHINES['alerta']` has no
 *     outgoing transition from it).
 *
 * Why `parkosFetchRaw` (not SWR inside this file): mirrors
 * `arqueosApi.ts` / `pairingApi.ts` — the data hooks own the SWR cache
 * key + revalidation, this file stays a pure fetch layer.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  alertaDetailReadSchema,
  alertasListResponseSchema,
  type AlertaDetailRead,
  type AlertasListQuery,
  type AlertasListResponse,
} from './alertasSchema';

const LIST_PATH = '/api/v1/workflows/alerta';

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

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

/** 404 `alerta_not_found` (V1, both the GET-by-uuid and the descartar POST). */
export class AlertaNotFoundError extends Error {
  constructor(uuid: string) {
    super(`La alerta ${uuid} no existe o ya no está disponible.`);
    this.name = 'AlertaNotFoundError';
  }
}

/** 403 `tenant_scope_violation`. */
export class TenantScopeViolationError extends Error {
  constructor() {
    super('No tenés acceso a esta alerta en este tenant.');
    this.name = 'TenantScopeViolationError';
  }
}

/**
 * 409 `alerta_ya_resuelta` (V2 terminal) -- the alert was already
 * `resuelta` by someone else (or a previous "descartar" call) by the
 * time this request landed. The backend body carries `estado_actual`,
 * always `"resuelta"` here.
 */
export class AlertaYaResueltaError extends Error {
  constructor(uuid: string) {
    super(
      `La alerta ${uuid} ya estaba resuelta. Alguien más la descartó o resolvió antes que vos; recargá la bandeja.`,
    );
    this.name = 'AlertaYaResueltaError';
  }
}

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `alertasApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchAlertas(query: AlertasListQuery): Promise<AlertasListResponse> {
  const params = new URLSearchParams();
  if (query.uuid_sucursal) params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.tipo_alerta) params.set('tipo_alerta', query.tipo_alerta);
  if (query.estado) params.set('estado', query.estado);
  if (query.severidad) params.set('severidad', query.severidad);
  if (query.desde) params.set('desde', query.desde);
  if (query.hasta) params.set('hasta', query.hasta);
  params.set('limit', String(query.limit));
  if (query.cursor) params.set('cursor', query.cursor);

  const url = `${LIST_PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return alertasListResponseSchema.parse(raw);
}

/**
 * `GET /api/v1/workflows/alerta/{uuid}` -- current-version single-item
 * read (generic factory route, NOT the hand-built list). No `severity`
 * on the wire; `alertaDetailReadSchema` models the field as optional.
 */
export async function fetchAlerta(uuid: string): Promise<AlertaDetailRead> {
  const res = await parkosFetchRaw(`${LIST_PATH}/${uuid}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (res.ok) {
    return alertaDetailReadSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 404) throw new AlertaNotFoundError(uuid);
  if (res.status === 403) throw new TenantScopeViolationError();
  throw new Error(`alertasApi: GET ${LIST_PATH}/${uuid} -> ${res.status}: ${bodyText.slice(0, 200)}`);
}

/**
 * `POST /api/v1/workflows/alerta/{uuid}/descartar` -- HU-F19.4, real
 * and merged. `observaciones` mandatory (BE rejects blank with 422,
 * surfaced here as the generic fallback error since the HU-F19.4 form
 * already blocks submission on an empty field client-side).
 *
 * Response is `response_model=AlertaRead` server-side (the plain
 * factory read schema, NOT `AlertaListItem`) -- no `severity` on the
 * wire, hence `alertaDetailReadSchema` (optional `severity`), same as
 * `fetchAlerta`.
 */
export async function descartarAlerta(
  uuid: string,
  observaciones: string,
): Promise<AlertaDetailRead> {
  const res = await parkosFetchRaw(`${LIST_PATH}/${uuid}/descartar`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ observaciones }),
  });
  if (res.ok) {
    return alertaDetailReadSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 404) throw new AlertaNotFoundError(uuid);
  if (res.status === 409) throw new AlertaYaResueltaError(uuid);
  if (res.status === 403) throw new TenantScopeViolationError();
  if (res.status === 422) {
    const detail = detailOf(bodyText);
    const msg = typeof detail?.detail === 'string' ? detail.detail : null;
    throw new Error(`Datos inválidos para descartar la alerta${msg ? `: ${msg}` : '.'}`);
  }
  throw new Error(
    `alertasApi: POST ${LIST_PATH}/${uuid}/descartar -> ${res.status}: ${bodyText.slice(0, 200)}`,
  );
}
