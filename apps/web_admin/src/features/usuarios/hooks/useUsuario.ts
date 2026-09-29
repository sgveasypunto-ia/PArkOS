import useSWR from 'swr';
import { getUsuario, getUsuarios } from '../api/usuariosApi';
import type { Usuario, UsuarioListResponse } from '../api/usuariosSchema';

export function useUsuarios() {
  const { data, error, isLoading, mutate } = useSWR<UsuarioListResponse>(
    'usuarios',
    getUsuarios,
  );

  return {
    usuarios: data?.items ?? [],
    total: data?.total ?? 0,
    isLoading,
    error,
    mutate,
  };
}

export function useUsuario(uuid: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<Usuario>(
    uuid ? `usuario-${uuid}` : null,
    () => getUsuario(uuid!),
  );

  return {
    usuario: data,
    isLoading,
    error,
    mutate,
  };
}
