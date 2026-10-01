import useSWR from 'swr';
import { getSucursalesUsuario } from '../api/usuariosApi';
import type { SucursalUsuario } from '../api/usuariosSchema';

export function useSucursalesUsuario(uuidUsuario: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<SucursalUsuario[]>(
    uuidUsuario ? `sucursales-usuario-${uuidUsuario}` : null,
    () => getSucursalesUsuario(uuidUsuario!),
  );

  return {
    sucursalesUsuario: data ?? [],
    isLoading,
    error,
    mutate,
  };
}
