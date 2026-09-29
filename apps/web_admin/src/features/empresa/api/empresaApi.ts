/**
 * `empresaApi.ts` — HTTP client for the admin Empresa singleton
 * (HU-F15.2 of `plan.md:3537`).
 *
 * Empresa es un singleton tenant-global: existe una sola fila
 * vigente a la vez por tenant. La UI obtiene la primera (y única)
 * fila del listado y luego hace PUT sobre su UUID para actualizar
 * (el backend hace close+insert bi-temporal).
 *
 * Endpoints consumed:
 *   - `GET  /api/v1/empresa/empresa`               (list; toma la 1ra fila)
 *   - `PUT  /api/v1/empresa/empresa/{uuid}`        (update, bi-temporal)
 *
 * Uses `parkosFetchRaw` del `@/lib/fetch` (que ya inyecta Bearer +
 * X-Sucursal-Context vía el auth store), mismo patrón que
 * `sucursalesApi.ts:18`.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  empresaReadListSchema,
  empresaReadSchema,
  empresaUpdateSchema,
  empresaMensajesUpdateSchema,
  type Empresa,
  type EmpresaMensajesUpdateInput,
  type EmpresaUpdateInput,
} from './empresaSchema';

export type { Empresa, EmpresaUpdateInput, EmpresaMensajesUpdateInput };

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `empresaApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

const SINGLETON_PATH = '/api/v1/empresa/empresa';

/**
 * Devuelve la fila vigente de Empresa, o `null` si todavía no se
 * sembró ninguna. El backend acepta `?limit=1` para evitar traer
 * un cursor gigante cuando solo queremos el singleton.
 */
export async function getEmpresa(): Promise<Empresa | null> {
  const raw = await fetchJson<unknown>(`${SINGLETON_PATH}?limit=1`, {
    method: 'GET',
    headers: jsonHeaders,
  });
  const parsed = empresaReadListSchema.parse(raw);
  return parsed.items[0] ?? null;
}

export async function updateEmpresa(
  uuid: string,
  input: EmpresaUpdateInput,
): Promise<Empresa> {
  const parsed = empresaUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(`${SINGLETON_PATH}/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return empresaReadSchema.parse(raw);
}

/**
 * PUT parcial para Mensajes. El backend acepta solo el campo a
 * actualizar (no requiere mandar `nombre`/`nit`/`regimen`); la UI
 * lo manda igual para mantener el contrato simétrico con Update, y
 * el backend ignora los no provistos en EmpresaUpdate. Para que la
 * separación entre tabs quede clara en el wire, mandamos solo los
 * dos campos de mensajes y el backend los acepta como nulos si el
 * payload no los incluye — pero acá dejamos la validación local
 * explícita para que un cambio en el backend no rompa el cliente.
 */
export async function updateEmpresaMensajes(
  uuid: string,
  input: EmpresaMensajesUpdateInput,
): Promise<Empresa> {
  const parsed = empresaMensajesUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(`${SINGLETON_PATH}/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return empresaReadSchema.parse(raw);
}
