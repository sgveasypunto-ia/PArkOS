/**
 * `tipoTarifaApi.ts` — HTTP client for the admin TipoTarifa CRUD UI
 * (PR-D). Mounted on `api_admin` per `api/v1/__init__.py` with
 * `permission_required="config_catalogo"` (0002 canonical seed).
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  tipoTarifaCreateSchema,
  tipoTarifaReadListEnvelopeSchema,
  tipoTarifaReadSchema,
  tipoTarifaUpdateSchema,
  type TipoTarifa,
  type TipoTarifaCreateInput,
  type TipoTarifaUpdateInput,
} from './tipoTarifaSchema';

export type { TipoTarifa, TipoTarifaCreateInput, TipoTarifaUpdateInput };

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `tipoTarifaApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export interface ListTipoTarifaOpts {
  limit?: number;
}

export async function listTipoTarifa(
  opts: ListTipoTarifaOpts = {},
): Promise<TipoTarifa[]> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/catalogos/tipo-tarifa${qs ? `?${qs}` : ''}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: jsonHeaders });
  return tipoTarifaReadListEnvelopeSchema.parse(raw).items;
}

export async function getTipoTarifa(uuid: string): Promise<TipoTarifa> {
  const raw = await fetchJson<unknown>(`/api/v1/catalogos/tipo-tarifa/${uuid}`, {
    method: 'GET',
    headers: jsonHeaders,
  });
  return tipoTarifaReadSchema.parse(raw);
}

export async function createTipoTarifa(
  input: TipoTarifaCreateInput,
): Promise<TipoTarifa> {
  const parsed = tipoTarifaCreateSchema.parse(input);
  const raw = await fetchJson<unknown>('/api/v1/catalogos/tipo-tarifa', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return tipoTarifaReadSchema.parse(raw);
}

export async function updateTipoTarifa(
  uuid: string,
  input: TipoTarifaUpdateInput,
): Promise<TipoTarifa> {
  const parsed = tipoTarifaUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(`/api/v1/catalogos/tipo-tarifa/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return tipoTarifaReadSchema.parse(raw);
}
