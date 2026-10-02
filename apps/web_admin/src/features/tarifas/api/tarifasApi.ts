/**
 * `tarifasApi.ts` — HTTP client for the admin Tarifa CRUD UI (PR-D).
 *
 * Endpoints consumed (mounted on `api_admin` per `api/v1/__init__.py`):
 *
 * - `GET    /api/v1/empresa/tarifas-sucursal?limit=…`           — list vigente
 * - `GET    /api/v1/empresa/tarifas-sucursal/by-key?…`         — by-key history
 * - `GET    /api/v1/empresa/tarifas-sucursal/{uuid}`           — current row
 * - `POST   /api/v1/empresa/tarifas-sucursal`                  — create
 * - `PUT    /api/v1/empresa/tarifas-sucursal/{uuid}`           — close+insert update
 *
 * All bi-temporal semantics (overlap guard, sucursal-inmutable guard,
 * `vigente_desde` Carril B boundary) live in the backend — PR-C v2.
 * The frontend surfaces the typed errors from `tarifaOverlapErrorSchema`
 * and `tarifaSucursalInmutableErrorSchema` so the form layer can render
 * an operator-readable message instead of a generic 409/422.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  tarifaBackendCreateSchema,
  tarifaOverlapErrorSchema,
  tarifaReadArraySchema,
  tarifaReadListEnvelopeSchema,
  tarifaReadSchema,
  tarifaSucursalInmutableErrorSchema,
  tarifaUpdateSchema,
  type Tarifa,
  type TarifaBackendCreateInput,
  type TarifaCreateInput,
  type TarifaUpdateInput,
} from './tarifaSchema';

export type { Tarifa, TarifaCreateInput, TarifaUpdateInput, TarifaBackendCreateInput };

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
 * Translate a 409/422 response body into the typed error.
 *
 * PR-C v2 returns the typed shape; any other error body falls through
 * to the generic error path. This is a defense-in-depth wrapper so
 * the form layer can `instanceof TarifaOverlapError` without parsing.
 */
function throwTypedError(res: Response, bodyText: string): never {
  if (res.status === 409) {
    try {
      throw new TarifaOverlapError(JSON.parse(bodyText));
    } catch {
      throw new Error(`tarifasApi: 409 ${bodyText.slice(0, 200)}`);
    }
  }
  if (res.status === 422) {
    try {
      throw new TarifaSucursalInmutableError(JSON.parse(bodyText));
    } catch {
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
  const parsed = tarifaBackendCreateSchema.parse(input);
  const raw = await fetchJsonOrTyped('/api/v1/empresa/tarifas-sucursal', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return tarifaReadSchema.parse(raw);
}

export async function updateTarifa(
  uuid: string,
  input: TarifaUpdateInput,
): Promise<Tarifa> {
  const parsed = tarifaUpdateSchema.parse(input);
  const raw = await fetchJsonOrTyped(`/api/v1/empresa/tarifas-sucursal/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return tarifaReadSchema.parse(raw);
}
