/**
 * `sucursalesApi.ts` — HTTP client for the admin Sucursal CRUD + pairing
 * token (IT-2.1, IT-2.7).
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
 * - `POST /api/v1/empresa/sucursal`                -- create
 * - `PUT  /api/v1/empresa/sucursal/{uuid}`         -- update (bi-temporal close+insert)
 * - `GET  /api/v1/sucursal/{uuid}/pairing-token`   -- mint pairing token
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  type PairingTokenResponse,
  type Sucursal,
  type SucursalCreateInput,
  type SucursalUpdateInput,
  pairingTokenResponseSchema,
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

export async function mintPairingToken(sucursalUuid: string): Promise<PairingTokenResponse> {
  const raw = await fetchJson<unknown>(`/api/v1/sucursal/${sucursalUuid}/pairing-token`, {
    method: 'GET',
    headers: jsonHeaders,
  });
  return pairingTokenResponseSchema.parse(raw);
}
