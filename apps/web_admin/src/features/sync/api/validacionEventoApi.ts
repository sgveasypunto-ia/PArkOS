/**
 * `validacionEventoApi.ts` — HTTP client for the HU-F19.6 admin "bandeja
 * de validación de eventos" tab (CU-07), consuming the already-real
 * backend endpoints implemented in this same worktree
 * (`dian/cloud_router.py`):
 *
 *   - GET  /api/v1/validacion-evento?uuid_sucursal=&estado=&cursor=&limit=
 *   - POST /api/v1/validacion-evento
 *
 * Thin transport only, same convention as `syncApi.ts` / `alertasApi.ts`:
 * build the URL, fetch, parse with Zod. SWR caching lives in
 * `hooks/useValidacionEventos.ts`.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@/lib/fetch';

import {
  validacionEventoListResponseSchema,
  type ValidacionEventoEstado,
  type ValidacionEventoListQuery,
  type ValidacionEventoListResponse,
} from './validacionEventoSchema';

const PATH = '/api/v1/validacion-evento';

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `validacionEventoApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchValidacionEventos(
  query: ValidacionEventoListQuery,
): Promise<ValidacionEventoListResponse> {
  const params = new URLSearchParams();
  if (query.uuid_sucursal) params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.estado) params.set('estado', query.estado);
  if (query.cursor) params.set('cursor', query.cursor);
  params.set('limit', String(query.limit ?? 50));
  const url = `${PATH}?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return validacionEventoListResponseSchema.parse(raw);
}

/**
 * 409 `validacion_evento_transicion_ilegal` — the chain tip acted on is
 * already in a terminal state (`validado` / `rechazado` are BOTH
 * terminal, `STATE_MACHINES['validacion_evento']` has no outgoing
 * transition from either) — typically because a concurrent admin
 * already resolved it. Mirrors `alertasApi.ts::AlertaYaResueltaError`.
 */
export class ValidacionEventoTransicionIlegalError extends Error {
  constructor(detail?: string) {
    super(
      detail ?? 'Este evento ya fue validado o rechazado por alguien más; recargá la bandeja.',
    );
    this.name = 'ValidacionEventoTransicionIlegalError';
  }
}

export interface CreateValidacionEventoTransicionInput {
  /** The uuid of the current chain tip being acted on (required by the BE for any transition). */
  uuidValidacionPadre: string;
  estado: Extract<ValidacionEventoEstado, 'validado' | 'rechazado'>;
  /** Mandatory + non-blank when `estado === 'rechazado'` (BE 422s otherwise); optional for `'validado'`. */
  observaciones?: string;
}

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

/**
 * `POST /api/v1/validacion-evento` — records a `validado`/`rechazado`
 * transition on an existing chain tip. Root creation (no
 * `uuid_validacion_padre`) is out of scope for this admin UI: the inbox
 * only ever acts on rows the device already synced as `pendiente`.
 *
 * 404 on an unknown `uuidValidacionPadre` is not yet a typed response
 * server-side (may surface as a 500) — handled here the same as any
 * other unmapped status: a generic error message, never a thrown
 * unhandled rejection.
 */
export async function createValidacionEventoTransicion(
  input: CreateValidacionEventoTransicionInput,
): Promise<{ uuid: string }> {
  const body: Record<string, unknown> = {
    uuid_validacion_padre: input.uuidValidacionPadre,
    estado: input.estado,
  };
  const trimmed = input.observaciones?.trim();
  if (trimmed) body.observaciones = trimmed;

  const res = await parkosFetchRaw(PATH, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.ok) {
    return (await res.json()) as { uuid: string };
  }
  const bodyText = await res.text();
  if (res.status === 409) {
    const detail = detailOf(bodyText);
    const msg = typeof detail?.detail === 'string' ? detail.detail : undefined;
    throw new ValidacionEventoTransicionIlegalError(msg);
  }
  if (res.status === 422) {
    const detail = detailOf(bodyText);
    const msg = typeof detail?.detail === 'string' ? detail.detail : null;
    throw new Error(`Datos inválidos para registrar la validación${msg ? `: ${msg}` : '.'}`);
  }
  throw new Error(`validacionEventoApi: POST ${PATH} -> ${res.status}: ${bodyText.slice(0, 200)}`);
}
