/**
 * `sucursalesApi.ts` — HTTP client for the admin Sucursal CRUD
 * (IT-2.1, IT-2.7).
 *
 * Uses the canonical `@/lib/fetch` `parkosFetchRaw` (which handles the
 * `Authorization: Bearer <jwt>` + `X-Sucursal-Context` headers via the
 * auth store + localStorage) so the operator does not have to thread
 * tokens through every call.
 *
 * Endpoints consumed (mounted on `api_admin` per
 * `api/v1/__init__.py`):
 *
 * - `GET  /api/v1/empresa/sucursal`                -- list
 * - `GET  /api/v1/empresa/sucursal/{uuid}`         -- single (HU-F15.1)
 * - `POST /api/v1/empresa/sucursal`                -- create
 * - `PUT  /api/v1/empresa/sucursal/{uuid}`         -- update (bi-temporal close+insert)
 * - `POST /api/v1/empresa/sucursal/{uuid}/deshabilitar` -- close-only disable (HU-F15.1 BR2/BR3)
 *
 * Pairing-token minting used to live here too (`GET /api/v1/sucursal/
 * {uuid}/pairing-token`), but that endpoint is OUTDATED (GET-mints-as-
 * side-effect, no ttl_hours, no rate limit, no revoke) and has been
 * replaced by the real admin pairing-token surface (HU-F19.3) — see
 * `@/features/pairing/api/pairingApi.ts`.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  type Sucursal,
  type SucursalCreateInput,
  type SucursalUpdateInput,
  sucursalCreateSchema,
  sucursalReadListSchema,
  sucursalReadSchema,
  sucursalUpdateSchema,
} from './sucursalSchema';

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

async function fetchJson<T>(input: RequestInfo, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `sucursalesApi: ${init.method ?? 'GET'} ${String(input)} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

/**
 * HU-F15.1 BR3 — typed 409 raised by {@link disableSucursal} when the
 * branch still has vehicles inside (``sucursal_con_ocupacion``) or
 * vigente subscriptions referencing it
 * (``sucursal_con_suscripciones_vigentes``). The form layer renders an
 * operator-readable message instead of a generic 409 (mirrors
 * `tarifasApi.ts`'s `TarifaOverlapError` convention).
 */
export class SucursalDeshabilitarBloqueadoError extends Error {
  readonly reason: 'sucursal_con_ocupacion' | 'sucursal_con_suscripciones_vigentes';
  readonly activos: number | null;
  readonly suscripcionesVigentes: number | null;

  constructor(body: unknown) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? (body as { detail?: unknown }).detail
        : undefined;
    const error =
      typeof detail === 'object' && detail !== null && 'error' in detail
        ? (detail as { error?: unknown }).error
        : undefined;
    if (error === 'sucursal_con_ocupacion') {
      const activos = (detail as { activos?: unknown }).activos;
      super(
        `La sucursal tiene ${typeof activos === 'number' ? activos : 'vehículos'} adentro. No se puede deshabilitar mientras haya ocupación activa.`,
      );
      this.name = 'SucursalDeshabilitarBloqueadoError';
      this.reason = 'sucursal_con_ocupacion';
      this.activos = typeof activos === 'number' ? activos : null;
      this.suscripcionesVigentes = null;
      return;
    }
    const suscripciones = (detail as { suscripciones_vigentes?: unknown } | undefined)
      ?.suscripciones_vigentes;
    super(
      `La sucursal tiene ${typeof suscripciones === 'number' ? suscripciones : ''} suscripciones vigentes. No se puede deshabilitar mientras existan suscripciones activas referenciándola.`,
    );
    this.name = 'SucursalDeshabilitarBloqueadoError';
    this.reason = 'sucursal_con_suscripciones_vigentes';
    this.activos = null;
    this.suscripcionesVigentes = typeof suscripciones === 'number' ? suscripciones : null;
  }
}

export class SucursalNoEncontradaError extends Error {
  constructor(uuid: string) {
    super(`La sucursal ${uuid} no existe o ya no está vigente.`);
    this.name = 'SucursalNoEncontradaError';
  }
}

export async function listSucursales(opts: { limit?: number } = {}): Promise<Sucursal[]> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/empresa/sucursal${qs ? `?${qs}` : ''}`;
  const raw = await fetchJson<unknown>(url, {
    method: 'GET',
    headers: jsonHeaders,
  });
  return sucursalReadListSchema.parse(raw).items;
}

export async function createSucursal(input: SucursalCreateInput): Promise<Sucursal> {
  const parsed = sucursalCreateSchema.parse(input);
  const raw = await fetchJson<unknown>('/api/v1/empresa/sucursal', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return sucursalReadSchema.parse(raw);
}

export async function updateSucursal(
  uuid: string,
  input: SucursalUpdateInput,
): Promise<Sucursal> {
  const parsed = sucursalUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(
    `/api/v1/empresa/sucursal/${uuid}`,
    {
      method: 'PUT',
      headers: jsonHeaders,
      body: JSON.stringify(parsed),
    },
  );
  return sucursalReadSchema.parse(raw);
}

/**
 * HU-F15.1 — single-branch read for `/sucursales/:uuid`. Hits the
 * dedicated header-free global-reads router (`get_sucursal_global`),
 * bounded to the caller's own permitted branches server-side; a branch
 * outside that scope 404s (indistinguishable from non-existent, by
 * backend design).
 */
export async function getSucursal(uuid: string): Promise<Sucursal> {
  const res = await parkosFetchRaw(`/api/v1/empresa/sucursal/${uuid}`, {
    method: 'GET',
    headers: jsonHeaders,
  });
  if (!res.ok) {
    if (res.status === 404) throw new SucursalNoEncontradaError(uuid);
    const body = await res.text();
    throw new Error(`sucursalesApi: GET ${uuid} -> ${res.status}: ${body.slice(0, 200)}`);
  }
  return sucursalReadSchema.parse(await res.json());
}

/**
 * HU-F15.1 BR2/BR3 — close-only disable (no replacement version). Throws
 * {@link SucursalNoEncontradaError} (404) or
 * {@link SucursalDeshabilitarBloqueadoError} (409) on failure; resolves
 * with no value on success (backend returns 204).
 */
export async function disableSucursal(uuid: string): Promise<void> {
  const res = await parkosFetchRaw(`/api/v1/empresa/sucursal/${uuid}/deshabilitar`, {
    method: 'POST',
    headers: jsonHeaders,
  });
  if (res.ok) return;
  if (res.status === 404) throw new SucursalNoEncontradaError(uuid);
  const body = await res.text();
  if (res.status === 409) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(body);
    } catch {
      throw new Error(`sucursalesApi: 409 ${body.slice(0, 200)}`);
    }
    throw new SucursalDeshabilitarBloqueadoError(parsed);
  }
  throw new Error(
    `sucursalesApi: POST ${uuid}/deshabilitar -> ${res.status}: ${body.slice(0, 200)}`,
  );
}
