/**
 * `adminUsuariosApi.ts` — HTTP client for the IT-1.4 admin
 * user-management endpoint.
 *
 * Endpoint consumed (cloud-only, admin- issuer + audit_read permission):
 *   - POST /api/v1/admin/usuarios  — create user with optional
 *                                    `sucursales_asignadas` list.
 *
 * Why no list endpoint yet: IT-1.4 only requires creating users.
 * Listing + editing comes under a follow-up scope. Keeping this
 * client minimal (no SWR cache, no fetch helper class) mirrors the
 * pattern in `sucursalesApi.ts`.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  adminUsuarioCreateSchema,
  type AdminUsuarioCreateInput,
  type AdminUsuarioRead,
} from './adminUsuarioSchema';

const PATH = '/api/v1/admin/usuarios';

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `adminUsuariosApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export async function createAdminUsuario(
  input: AdminUsuarioCreateInput,
): Promise<AdminUsuarioRead> {
  const payload = adminUsuarioCreateSchema.parse(input);
  const raw = await fetchJson<unknown>(PATH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return raw as AdminUsuarioRead;
}
