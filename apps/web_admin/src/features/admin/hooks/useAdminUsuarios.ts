/**
 * `useAdminUsuarios.ts` — SWR hook that owns the GET
 * `/api/v1/admin/usuarios` cache for the Gestión de Usuarios screen.
 *
 * The cache key is static (`/api/v1/admin/usuarios`) — the endpoint is
 * cross-branch by design (IT-1.4 admin user management is global), so
 * switching the picker does NOT invalidate this list. Mutations from
 * `AdminUsuarioTable` and the create/edit dialogs call `mutate()` to
 * revalidate after a successful write.
 *
 * Why `assignBranch` / `unassignBranch` also invalidate the per-user
 * key: the assignment modal and the lazy row panel in the table both
 * read from `useAdminUsuarioSucursales(uuid)`, which uses the SWR key
 * `/api/v1/admin/usuarios/{uuid}/sucursales`. Without this invalidate
 * the modal's `await refresh()` updates its own copy but the table's
 * expanded row stays stale until the next focus revalidation. Mutating
 * the per-user key globally keeps both consumers in sync with zero
 * extra network round-trip on the consumer side — they re-read the
 * already-fresh cache.
 */
import useSWR, { mutate as globalMutate } from 'swr';

import {
  listAdminUsuarios,
  createAdminUsuario,
  asignarAdminUsuarioSucursal,
  desasignarAdminUsuarioSucursal,
} from '../api/adminUsuariosApi';
import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';

const KEY = '/api/v1/admin/usuarios';

function perUserKey(uuid: string): string {
  return `/api/v1/admin/usuarios/${uuid}/sucursales`;
}

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
    // The modal already awaits its own `refresh()`; this invalidate is
    // for every OTHER consumer of the same key (the table's expanded
    // row panel), which has no local mutate handle.
    await globalMutate(perUserKey(usuarioUuid));
  }

  async function unassignBranch(
    usuarioUuid: string,
    sucursalUuid: string,
  ): Promise<void> {
    await desasignarAdminUsuarioSucursal(usuarioUuid, sucursalUuid);
    await mutate();
    await globalMutate(perUserKey(usuarioUuid));
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
