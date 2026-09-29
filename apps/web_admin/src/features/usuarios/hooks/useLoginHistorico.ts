import useSWR from 'swr';
import { getSesionesActivas, getLoginHistorico } from '../api/usuariosApi';
import type { Sesion, LoginHistorico } from '../api/usuariosSchema';

export function useSesionesActivas(uuidUsuario: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<Sesion[]>(
    uuidUsuario ? `sesiones-activas-${uuidUsuario}` : null,
    () => getSesionesActivas(uuidUsuario!),
  );

  return {
    sesiones: data ?? [],
    isLoading,
    error,
    mutate,
  };
}

export function useLoginHistorico(uuidUsuario: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<LoginHistorico[]>(
    uuidUsuario ? `login-historico-${uuidUsuario}` : null,
    () => getLoginHistorico(uuidUsuario!),
  );

  return {
    loginHistorico: data ?? [],
    isLoading,
    error,
    mutate,
  };
}
