/**
 * `configuracionCajaApi.ts` — HTTP client for `configuracion_caja`
 * (HU-F15.5, CU-13). Mirrors the sibling
 * `configuracion-tolerancias/api/configuracionToleranciasApi.ts` client
 * 1:1 (same `fetchJson` helper shape, same error convention), plus
 * `getConfiguracionCajaEfectiva`, which the Tolerancias client does NOT
 * have — there is no `.../configuracion-tolerancias/efectiva` route on
 * the backend (confirmed in `api/v1/configuracion.py`: only
 * `efectiva` (seguridad) and `efectiva_caja` are mounted). The
 * Tolerancias admin screen works around that gap by listing every row
 * and resolving the effective one client-side (see
 * `useConfiguracionTolerancias` + `ConfiguracionTolerancias.tsx`).
 * `configuracion-caja/efectiva` DOES exist (HU-F13.3), so this client
 * uses it directly instead of reimplementing that same workaround.
 *
 * Endpoints consumed:
 * - `GET  /api/v1/configuracion/configuracion-caja?limit=…`
 * - `GET  /api/v1/configuracion/configuracion-caja/efectiva?uuid_sucursal=…`
 * - `GET  /api/v1/configuracion/configuracion-caja/{uuid}`
 * - `POST /api/v1/configuracion/configuracion-caja`
 * - `PUT  /api/v1/configuracion/configuracion-caja/{uuid}`
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  configuracionCajaCreateSchema,
  configuracionCajaReadListEnvelopeSchema,
  configuracionCajaReadSchema,
  configuracionCajaUpdateSchema,
  type ConfiguracionCaja,
  type ConfiguracionCajaCreateInput,
  type ConfiguracionCajaUpdateInput,
} from './configuracionCajaSchema';

export type { ConfiguracionCaja, ConfiguracionCajaCreateInput, ConfiguracionCajaUpdateInput };

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `configuracionCajaApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export interface ListConfiguracionCajaOpts {
  limit?: number;
}

export async function listConfiguracionCaja(
  opts: ListConfiguracionCajaOpts = {},
): Promise<ConfiguracionCaja[]> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/configuracion/configuracion-caja${qs ? `?${qs}` : ''}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: jsonHeaders });
  return configuracionCajaReadListEnvelopeSchema.parse(raw).items;
}

export async function getConfiguracionCaja(uuid: string): Promise<ConfiguracionCaja> {
  const raw = await fetchJson<unknown>(`/api/v1/configuracion/configuracion-caja/${uuid}`, {
    method: 'GET',
    headers: jsonHeaders,
  });
  return configuracionCajaReadSchema.parse(raw);
}

/**
 * `denominaciones_permitidas` crosses the Zod form boundary as
 * `string[] | null` (one numeric token per denomination — see the
 * schema file header). The backend's `ConfiguracionCajaCreate.
 * denominaciones_permitidas` is `list[int] | None`: convert to real
 * numbers right here, right before the request leaves the client, so
 * neither the form layer nor the Zod schema has to juggle two
 * representations of the same field.
 */
function toWirePayload<T extends { denominaciones_permitidas: string[] | null }>(
  parsed: T,
): Omit<T, 'denominaciones_permitidas'> & { denominaciones_permitidas: number[] | null } {
  return {
    ...parsed,
    denominaciones_permitidas: parsed.denominaciones_permitidas?.map(Number) ?? null,
  };
}

export async function createConfiguracionCaja(
  input: ConfiguracionCajaCreateInput,
): Promise<ConfiguracionCaja> {
  const parsed = configuracionCajaCreateSchema.parse(input);
  const raw = await fetchJson<unknown>('/api/v1/configuracion/configuracion-caja', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(toWirePayload(parsed)),
  });
  return configuracionCajaReadSchema.parse(raw);
}

export async function updateConfiguracionCaja(
  uuid: string,
  input: ConfiguracionCajaUpdateInput,
): Promise<ConfiguracionCaja> {
  const parsed = configuracionCajaUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(`/api/v1/configuracion/configuracion-caja/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(toWirePayload(parsed)),
  });
  return configuracionCajaReadSchema.parse(raw);
}

/**
 * `GET /configuracion-caja/efectiva?uuid_sucursal=…` (HU-F13.3).
 *
 * Resolves the per-branch override OR the global default
 * (`uuid_sucursal IS NULL`), server-side. Returns the row's own
 * `uuid_sucursal` so the caller can tell which one it got: equal to
 * `uuidSucursal` → it's this branch's override; `null` → it's the
 * global default and this branch has none yet.
 *
 * Returns `null` on 404 (neither an override nor a global default is
 * configured) instead of throwing — the 404 is an expected, modeled
 * state here (HU-F15.5 "mensaje explícito invitando a configurar el
 * default global primero"), not an exceptional one.
 */
export async function getConfiguracionCajaEfectiva(
  uuidSucursal: string,
): Promise<ConfiguracionCaja | null> {
  const url = `/api/v1/configuracion/configuracion-caja/efectiva?uuid_sucursal=${encodeURIComponent(uuidSucursal)}`;
  const res = await parkosFetchRaw(url, { method: 'GET', headers: jsonHeaders });
  if (res.status === 404) return null;
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`configuracionCajaApi: GET ${url} -> ${res.status}: ${body.slice(0, 200)}`);
  }
  return configuracionCajaReadSchema.parse(await res.json());
}
