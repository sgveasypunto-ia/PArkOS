/**
 * `tiposVehiculoApi.ts` — HTTP client for the admin TiposVehiculo CRUD UI
 * (PR-D). Mounted on `api_admin` per `api/v1/__init__.py` with
 * `permission_required="config_catalogo"` (0002 canonical seed).
 *
 * Endpoints consumed:
 * - `GET    /api/v1/catalogos/tipos-vehiculo?limit=…`
 * - `GET    /api/v1/catalogos/tipos-vehiculo/{uuid}`
 * - `POST   /api/v1/catalogos/tipos-vehiculo`
 * - `PUT    /api/v1/catalogos/tipos-vehiculo/{uuid}`
 *
 * The factory exposes the same C+Q+U surface; we wrap it with Zod
 * validation and a typed error envelope. No fancy guard errors here —
 * the catalog has no overlap / sucursal / ingresos invariants (the
 * UK01 on (tipo, vigente_desde) surfaces as 500 from the DB on a
 * duplicate; the form layer surfaces it as a generic error).
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  tipoVehiculoCreateSchema,
  tipoVehiculoReadListEnvelopeSchema,
  tipoVehiculoReadSchema,
  tipoVehiculoUpdateSchema,
  type TipoVehiculo,
  type TipoVehiculoCreateInput,
  type TipoVehiculoUpdateInput,
} from './tipoVehiculoSchema';

export type { TipoVehiculo, TipoVehiculoCreateInput, TipoVehiculoUpdateInput };

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `tiposVehiculoApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export interface ListTiposVehiculoOpts {
  limit?: number;
}

export async function listTiposVehiculo(
  opts: ListTiposVehiculoOpts = {},
): Promise<TipoVehiculo[]> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/catalogos/tipos-vehiculo${qs ? `?${qs}` : ''}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: jsonHeaders });
  return tipoVehiculoReadListEnvelopeSchema.parse(raw).items;
}

export async function getTipoVehiculo(uuid: string): Promise<TipoVehiculo> {
  const raw = await fetchJson<unknown>(
    `/api/v1/catalogos/tipos-vehiculo/${uuid}`,
    { method: 'GET', headers: jsonHeaders },
  );
  return tipoVehiculoReadSchema.parse(raw);
}

export async function createTipoVehiculo(
  input: TipoVehiculoCreateInput,
): Promise<TipoVehiculo> {
  const parsed = tipoVehiculoCreateSchema.parse(input);
  const raw = await fetchJson<unknown>('/api/v1/catalogos/tipos-vehiculo', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return tipoVehiculoReadSchema.parse(raw);
}

export async function updateTipoVehiculo(
  uuid: string,
  input: TipoVehiculoUpdateInput,
): Promise<TipoVehiculo> {
  const parsed = tipoVehiculoUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(
    `/api/v1/catalogos/tipos-vehiculo/${uuid}`,
    {
      method: 'PUT',
      headers: jsonHeaders,
      body: JSON.stringify(parsed),
    },
  );
  return tipoVehiculoReadSchema.parse(raw);
}
