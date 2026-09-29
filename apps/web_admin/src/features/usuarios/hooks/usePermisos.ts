import useSWR from 'swr';
import { getPermisos, getPermisosUsuario } from '../api/usuariosApi';
import type { Permiso, PermisoUsuario } from '../api/usuariosSchema';

export function usePermisos() {
  const { data, error, isLoading, mutate } = useSWR<Permiso[]>(
    'permisos',
    getPermisos,
  );

  return {
    permisos: data ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function usePermisosUsuario(uuidUsuario: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<PermisoUsuario[]>(
    uuidUsuario ? `permisos-usuario-${uuidUsuario}` : null,
    () => getPermisosUsuario(uuidUsuario!),
  );

  return {
    permisosUsuario: data ?? [],
    isLoading,
    error,
    mutate,
  };
}
