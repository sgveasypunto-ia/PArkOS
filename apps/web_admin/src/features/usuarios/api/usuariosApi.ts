import { parkosFetch } from '@/lib/fetch';
import type {
  Usuario,
  UsuarioCreate,
  UsuarioUpdate,
  UsuarioListResponse,
  Permiso,
  PermisoUsuario,
  Sesion,
  LoginHistorico,
  SucursalUsuario,
} from './usuariosSchema';

export async function getUsuarios(): Promise<UsuarioListResponse> {
  return parkosFetch<UsuarioListResponse>('/api/v1/admin/usuarios');
}

export async function getUsuario(uuid: string): Promise<Usuario> {
  return parkosFetch<Usuario>(`/api/v1/admin/usuarios/${uuid}`);
}

export async function createUsuario(data: UsuarioCreate): Promise<Usuario> {
  return parkosFetch<Usuario>('/api/v1/admin/usuarios', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateUsuario(
  uuid: string,
  data: UsuarioUpdate,
): Promise<Usuario> {
  return parkosFetch<Usuario>(`/api/v1/admin/usuarios/${uuid}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function getPermisos(): Promise<Permiso[]> {
  return parkosFetch<Permiso[]>('/api/v1/admin/permisos');
}

export async function getPermisosUsuario(
  uuidUsuario: string,
): Promise<PermisoUsuario[]> {
  return parkosFetch<PermisoUsuario[]>(
    `/api/v1/admin/usuarios/${uuidUsuario}/permisos`,
  );
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
  return parkosFetch<Sesion[]>(
    `/api/v1/admin/usuarios/${uuidUsuario}/sesiones?activas=true`,
  );
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
  return parkosFetch<LoginHistorico[]>(
    `/api/v1/admin/usuarios/${uuidUsuario}/login-historico`,
  );
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
  return parkosFetch<SucursalUsuario[]>(
    `/api/v1/admin/usuarios/${uuidUsuario}/sucursales`,
  );
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
