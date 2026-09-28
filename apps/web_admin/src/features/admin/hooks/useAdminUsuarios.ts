/**
 * `useAdminUsuarios.ts` — SWR hook that owns the GET
 * `/api/v1/admin/usuarios` cache for the Gestión de Usuarios screen.
 *
 * The cache key is static (`/api/v1/admin/usuarios`) — the endpoint is
 * cross-branch by design (IT-1.4 admin user management is global), so
 * switching the picker does NOT invalidate this list. Mutations from
 * `AdminUsuarioTable` and the create/edit dialogs call `mutate()` to
 * revalidate after a successful write.
 */
import useSWR from 'swr';

import {
  listAdminUsuarios,
  createAdminUsuario,
  asignarAdminUsuarioSucursal,
  desasignarAdminUsuarioSucursal,
} from '../api/adminUsuariosApi';
import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';

const KEY = '/api/v1/admin/usuarios';

export interface UseAdminUsuariosReturn {
  usuarios: AdminUsuarioRead[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<AdminUsuarioRead[] | undefined>;
  create: typeof createAdminUsuario;
  assignBranch: (usuarioUuid: string, sucursalUuid: string) => Promise<void>;
  unassignBranch: (usuarioUuid: string, sucursalUuid: string) => Promise<void>;
}

export function useAdminUsuarios(): UseAdminUsuariosReturn {
  const { data, error, isLoading, mutate } = useSWR<AdminUsuarioRead[]>(
    KEY,
    listAdminUsuarios,
    { revalidateOnFocus: false },
  );

  async function assignBranch(
    usuarioUuid: string,
    sucursalUuid: string,
  ): Promise<void> {
    await asignarAdminUsuarioSucursal(usuarioUuid, sucursalUuid);
    await mutate();
  }

  async function unassignBranch(
    usuarioUuid: string,
    sucursalUuid: string,
  ): Promise<void> {
    await desasignarAdminUsuarioSucursal(usuarioUuid, sucursalUuid);
    await mutate();
  }

  return {
    usuarios: data,
    isLoading,
    error,
    refresh: mutate,
    create: createAdminUsuario,
    assignBranch,
    unassignBranch,
  };
}
