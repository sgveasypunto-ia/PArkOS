/**
 * `configuracionToleranciasApi.ts` — HTTP client for the admin Tolerancias
 * CRUD UI (PR-D). Mounted on `api_admin` per `api/v1/__init__.py` with
 * `permission_required="config_tolerancias"` (0059 seed).
 *
 * Endpoints consumed:
 * - `GET  /api/v1/configuracion/configuracion-tolerancias?limit=…`
 * - `GET  /api/v1/configuracion/configuracion-tolerancias/efectiva?uuid_sucursal=…`
 * - `GET  /api/v1/configuracion/configuracion-tolerancias/{uuid}`
 * - `POST /api/v1/configuracion/configuracion-tolerancias`
 * - `PUT  /api/v1/configuracion/configuracion-tolerancias/{uuid}`
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  configuracionToleranciasCreateSchema,
  configuracionToleranciasReadListEnvelopeSchema,
  configuracionToleranciasReadSchema,
  configuracionToleranciasUpdateSchema,
  type ConfiguracionTolerancias,
  type ConfiguracionToleranciasCreateInput,
  type ConfiguracionToleranciasUpdateInput,
} from './configuracionToleranciasSchema';

export type {
  ConfiguracionTolerancias,
  ConfiguracionToleranciasCreateInput,
  ConfiguracionToleranciasUpdateInput,
};

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `configuracionToleranciasApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export interface ListConfiguracionToleranciasOpts {
  limit?: number;
}

export async function listConfiguracionTolerancias(
  opts: ListConfiguracionToleranciasOpts = {},
): Promise<ConfiguracionTolerancias[]> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/configuracion/configuracion-tolerancias${qs ? `?${qs}` : ''}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: jsonHeaders });
  return configuracionToleranciasReadListEnvelopeSchema.parse(raw).items;
}

export async function getConfiguracionTolerancias(
  uuid: string,
): Promise<ConfiguracionTolerancias> {
  const raw = await fetchJson<unknown>(
    `/api/v1/configuracion/configuracion-tolerancias/${uuid}`,
    { method: 'GET', headers: jsonHeaders },
  );
  return configuracionToleranciasReadSchema.parse(raw);
}

export async function createConfiguracionTolerancias(
  input: ConfiguracionToleranciasCreateInput,
): Promise<ConfiguracionTolerancias> {
  const parsed = configuracionToleranciasCreateSchema.parse(input);
  const raw = await fetchJson<unknown>(
    '/api/v1/configuracion/configuracion-tolerancias',
    {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(parsed),
    },
  );
  return configuracionToleranciasReadSchema.parse(raw);
}

export async function updateConfiguracionTolerancias(
  uuid: string,
  input: ConfiguracionToleranciasUpdateInput,
): Promise<ConfiguracionTolerancias> {
  const parsed = configuracionToleranciasUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(
    `/api/v1/configuracion/configuracion-tolerancias/${uuid}`,
    {
      method: 'PUT',
      headers: jsonHeaders,
      body: JSON.stringify(parsed),
    },
  );
  return configuracionToleranciasReadSchema.parse(raw);
}
