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
  const raw = await fetchJson<unknown>(`${PATH}/${uuid}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  return adminUsuarioReadSchema.parse(raw);
}

export async function listAdminUsuarioSucursales(
  uuid: string,
): Promise<AdminSucursalAsignadaRead[]> {
  const raw = await fetchJson<unknown>(`${PATH}/${uuid}/sucursales`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  const items = Array.isArray(raw) ? raw : [];
  return items.map((item) => adminSucursalAsignadaReadSchema.parse(item));
}

export async function asignarAdminUsuarioSucursal(
  uuid: string,
  sucursalUuid: string,
): Promise<AdminSucursalAsignadaRead> {
  const raw = await fetchJson<unknown>(`${PATH}/${uuid}/sucursales`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uuid_sucursal: sucursalUuid }),
  });
  return adminSucursalAsignadaReadSchema.parse(raw);
}

export async function desasignarAdminUsuarioSucursal(
  uuid: string,
  sucursalUuid: string,
): Promise<void> {
  const res = await parkosFetchRaw(`${PATH}/${uuid}/sucursales/${sucursalUuid}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `adminUsuariosApi: DELETE ${PATH}/${uuid}/sucursales/${sucursalUuid} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
}
