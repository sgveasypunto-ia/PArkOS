import { z } from 'zod';
import { parkosFetch } from '@/lib/fetch';
import {
  usuarioSchema,
  usuarioListSchema,
  permisoSchema,
  permisoUsuarioSchema,
  sesionSchema,
  loginHistoricoSchema,
  sucursalUsuarioSchema,
  type Usuario,
  type UsuarioCreate,
  type UsuarioUpdate,
  type UsuarioListResponse,
  type Permiso,
  type PermisoUsuario,
  type Sesion,
  type LoginHistorico,
  type SucursalUsuario,
} from './usuariosSchema';

export async function getUsuarios(): Promise<UsuarioListResponse> {
  const raw = await parkosFetch<unknown>('/api/v1/admin/usuarios');
  return usuarioListSchema.parse(raw);
}

export async function getUsuario(uuid: string): Promise<Usuario> {
  const raw = await parkosFetch<unknown>(`/api/v1/admin/usuarios/${uuid}`);
  return usuarioSchema.parse(raw);
}

export async function createUsuario(data: UsuarioCreate): Promise<Usuario> {
  const raw = await parkosFetch<unknown>('/api/v1/admin/usuarios', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return usuarioSchema.parse(raw);
}

export async function updateUsuario(
  uuid: string,
  data: UsuarioUpdate,
): Promise<Usuario> {
  const raw = await parkosFetch<unknown>(`/api/v1/admin/usuarios/${uuid}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  return usuarioSchema.parse(raw);
}

export async function getPermisos(): Promise<Permiso[]> {
  const raw = await parkosFetch<unknown>('/api/v1/admin/permisos');
  return z.array(permisoSchema).parse(raw);
}

export async function getPermisosUsuario(
  uuidUsuario: string,
): Promise<PermisoUsuario[]> {
  const raw = await parkosFetch<unknown>(
    `/api/v1/admin/usuarios/${uuidUsuario}/permisos`,
  );
  return z.array(permisoUsuarioSchema).parse(raw);
}

export async function asignarPermiso(
  uuidUsuario: string,
  uuidPermiso: string,
): Promise<void> {
  await parkosFetch(
    `/api/v1/admin/usuarios/${uuidUsuario}/permisos/${uuidPermiso}`,
    {
      method: 'POST',
    },
  );
}

export async function revocarPermiso(
  uuidUsuario: string,
  uuidPermiso: string,
): Promise<void> {
  await parkosFetch(
    `/api/v1/admin/usuarios/${uuidUsuario}/permisos/${uuidPermiso}`,
    {
      method: 'DELETE',
    },
  );
}

export async function getSesionesActivas(
  uuidUsuario: string,
): Promise<Sesion[]> {
  const raw = await parkosFetch<unknown>(
    `/api/v1/admin/usuarios/${uuidUsuario}/sesiones?activas=true`,
  );
  return z.array(sesionSchema).parse(raw);
}

export async function cerrarSesion(
  uuidUsuario: string,
  uuidSesion: string,
): Promise<void> {
  await parkosFetch(
    `/api/v1/admin/usuarios/${uuidUsuario}/sesiones/${uuidSesion}/cerrar`,
    {
      method: 'POST',
    },
  );
}

export async function getLoginHistorico(
  uuidUsuario: string,
): Promise<LoginHistorico[]> {
  const raw = await parkosFetch<unknown>(
    `/api/v1/admin/usuarios/${uuidUsuario}/login-historico`,
  );
  return z.array(loginHistoricoSchema).parse(raw);
}

export async function resetPassword(
  uuidUsuario: string,
  newPassword: string,
): Promise<void> {
  await parkosFetch(`/api/v1/admin/usuarios/${uuidUsuario}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  });
}

export async function getSucursalesUsuario(
  uuidUsuario: string,
): Promise<SucursalUsuario[]> {
  const raw = await parkosFetch<unknown>(
    `/api/v1/admin/usuarios/${uuidUsuario}/sucursales`,
  );
  return z.array(sucursalUsuarioSchema).parse(raw);
}

export async function asignarSucursal(
  uuidUsuario: string,
  uuidSucursal: string,
): Promise<void> {
  await parkosFetch(`/api/v1/admin/usuarios/${uuidUsuario}/sucursales`, {
    method: 'POST',
    body: JSON.stringify({ uuid_sucursal: uuidSucursal }),
  });
}

export async function desasignarSucursal(
  uuidUsuario: string,
  uuidSucursal: string,
): Promise<void> {
  await parkosFetch(
    `/api/v1/admin/usuarios/${uuidUsuario}/sucursales/${uuidSucursal}`,
    {
      method: 'DELETE',
    },
  );
}
