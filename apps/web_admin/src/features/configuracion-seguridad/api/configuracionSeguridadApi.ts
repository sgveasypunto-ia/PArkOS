/**
 * `configuracionSeguridadApi.ts` — HTTP client for the admin Seguridad
 * CRUD UI (PR-D). Mounted on `api_admin` per `api/v1/__init__.py` with
 * `permission_required="config_seguridad"` (0059 seed).
 *
 * Endpoints consumed:
 * - `GET  /api/v1/configuracion/configuracion-seguridad?limit=…`
 * - `GET  /api/v1/configuracion/configuracion-seguridad/efectiva?uuid_sucursal=…`
 * - `GET  /api/v1/configuracion/configuracion-seguridad/{uuid}`
 * - `POST /api/v1/configuracion/configuracion-seguridad`
 * - `PUT  /api/v1/configuracion/configuracion-seguridad/{uuid}`
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  configuracionSeguridadCreateSchema,
  configuracionSeguridadReadListEnvelopeSchema,
  configuracionSeguridadReadSchema,
  configuracionSeguridadUpdateSchema,
  type ConfiguracionSeguridad,
  type ConfiguracionSeguridadCreateInput,
  type ConfiguracionSeguridadUpdateInput,
} from './configuracionSeguridadSchema';

export type {
  ConfiguracionSeguridad,
  ConfiguracionSeguridadCreateInput,
  ConfiguracionSeguridadUpdateInput,
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
      `configuracionSeguridadApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export interface ListConfiguracionSeguridadOpts {
  limit?: number;
}

export async function listConfiguracionSeguridad(
  opts: ListConfiguracionSeguridadOpts = {},
): Promise<ConfiguracionSeguridad[]> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/configuracion/configuracion-seguridad${qs ? `?${qs}` : ''}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: jsonHeaders });
  return configuracionSeguridadReadListEnvelopeSchema.parse(raw).items;
}

export async function getConfiguracionSeguridadEfectiva(
  uuid_sucursal: string,
): Promise<ConfiguracionSeguridad> {
  const url = `/api/v1/configuracion/configuracion-seguridad/efectiva?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: jsonHeaders });
  return configuracionSeguridadReadSchema.parse(raw);
}

export async function getConfiguracionSeguridad(
  uuid: string,
): Promise<ConfiguracionSeguridad> {
  const raw = await fetchJson<unknown>(
    `/api/v1/configuracion/configuracion-seguridad/${uuid}`,
    { method: 'GET', headers: jsonHeaders },
  );
  return configuracionSeguridadReadSchema.parse(raw);
}

export async function createConfiguracionSeguridad(
  input: ConfiguracionSeguridadCreateInput,
): Promise<ConfiguracionSeguridad> {
  const parsed = configuracionSeguridadCreateSchema.parse(input);
  const raw = await fetchJson<unknown>(
    '/api/v1/configuracion/configuracion-seguridad',
    {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(parsed),
    },
  );
  return configuracionSeguridadReadSchema.parse(raw);
}

export async function updateConfiguracionSeguridad(
  uuid: string,
  input: ConfiguracionSeguridadUpdateInput,
): Promise<ConfiguracionSeguridad> {
  const parsed = configuracionSeguridadUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(
    `/api/v1/configuracion/configuracion-seguridad/${uuid}`,
    {
      method: 'PUT',
      headers: jsonHeaders,
      body: JSON.stringify(parsed),
    },
  );
  return configuracionSeguridadReadSchema.parse(raw);
}
