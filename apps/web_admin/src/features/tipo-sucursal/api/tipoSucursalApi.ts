/**
 * `tipoSucursalApi.ts` — HTTP client for the read-only TipoSucursal
 * catalog surface used by the unified SucursalForm (auto-fill of
 * `uuid_tipo_sucursal` on create).
 *
 * Mounted on `api_admin` per `api/v1/__init__.py`. The factory exposes
 * full C+Q+U but this client only consumes the list endpoint (the
 * seed is shipped via Alembic migration, not CRUD).
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  tipoSucursalReadListEnvelopeSchema,
  type TipoSucursal,
} from './tipoSucursalSchema';

export type { TipoSucursal };

const jsonHeaders = {
  Accept: 'application/json',
};

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `tipoSucursalApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export interface ListTipoSucursalOpts {
  limit?: number;
}

export async function listTipoSucursal(
  opts: ListTipoSucursalOpts = {},
): Promise<TipoSucursal[]> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/catalogos/tipo-sucursal${qs ? `?${qs}` : ''}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: jsonHeaders });
  return tipoSucursalReadListEnvelopeSchema.parse(raw).items;
}
