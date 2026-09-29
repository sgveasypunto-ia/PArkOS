/**
 * `adminUsuariosApi.ts` — HTTP client for the IT-1.4 admin
 * user-management surface (PR3 of the web_admin redesign).
 *
 * Endpoints consumed (cloud-only, admin- issuer):
 *   - POST   /api/v1/admin/usuarios                                -- create
 *   - GET    /api/v1/admin/usuarios                                -- list (active rows)
 *   - GET    /api/v1/admin/usuarios/{uuid}                         -- get one
 *   - GET    /api/v1/admin/usuarios/{uuid}/sucursales              -- list branch assignments
 *   - POST   /api/v1/admin/usuarios/{uuid}/sucursales              -- assign branch
 *   - DELETE /api/v1/admin/usuarios/{uuid}/sucursales/{sucursal}   -- unassign branch
 *
 * PUT for editing users is OUT OF SCOPE for PR3 — the backend does
 * not expose it yet. The Gestión de Usuarios UI therefore offers
 * "Asignar sucursales" (assign + unassign) but not "Editar usuario"
 * (no field-level mutation). A future change adds the PUT endpoint.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  adminSucursalAsignadaReadSchema,
  adminUsuarioCreateSchema,
  adminUsuarioReadListSchema,
  adminUsuarioReadSchema,
  type AdminSucursalAsignadaRead,
  type AdminUsuarioCreateInput,
  type AdminUsuarioRead,
} from './adminUsuarioSchema';

const PATH = '/api/v1/admin/usuarios';

/**
 * Guard for path interpolation. These URLs are built by template
 * literal, so a caller that passes a URL instead of a uuid produces a
 * silently malformed path (`/admin/usuarios//api/v1/admin/usuarios/.../sucursales/sucursales`)
 * that the backend answers with a 404 and no explanation. Failing here
 * turns that into an actionable error at the source.
 */
function assertUuid(value: string, paramName: string): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) {
    throw new Error(
      `adminUsuariosApi: "${paramName}" must be a bare UUID, got ${JSON.stringify(value)}`,
    );
  }
  return value;
}

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
  return adminUsuarioReadSchema.parse(raw);
}

export async function listAdminUsuarios(): Promise<AdminUsuarioRead[]> {
  const raw = await fetchJson<unknown>(PATH, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return adminUsuarioReadListSchema.parse(raw).items;
}

export async function getAdminUsuario(uuid: string): Promise<AdminUsuarioRead> {
  const raw = await fetchJson<unknown>(`${PATH}/${assertUuid(uuid, 'uuid')}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return adminUsuarioReadSchema.parse(raw);
}

export async function listAdminUsuarioSucursales(
  uuid: string,
): Promise<AdminSucursalAsignadaRead[]> {
  const raw = await fetchJson<unknown>(
    `${PATH}/${assertUuid(uuid, 'usuarioUuid')}/sucursales`,
    {
      method: 'GET',
      headers: { Accept: 'application/json' },
    },
  );
  const items = Array.isArray(raw) ? raw : [];
  return items.map((item) => adminSucursalAsignadaReadSchema.parse(item));
}

export async function asignarAdminUsuarioSucursal(
  uuid: string,
  sucursalUuid: string,
): Promise<AdminSucursalAsignadaRead> {
  const raw = await fetchJson<unknown>(
    `${PATH}/${assertUuid(uuid, 'usuarioUuid')}/sucursales`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uuid_sucursal: assertUuid(sucursalUuid, 'sucursalUuid') }),
    },
  );
  return adminSucursalAsignadaReadSchema.parse(raw);
}

export async function desasignarAdminUsuarioSucursal(
  uuid: string,
  sucursalUuid: string,
): Promise<void> {
  const url = `${PATH}/${assertUuid(uuid, 'usuarioUuid')}/sucursales/${assertUuid(sucursalUuid, 'sucursalUuid')}`;
  const res = await parkosFetchRaw(url, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `adminUsuariosApi: DELETE ${url} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
}
