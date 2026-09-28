/**
 * `useAdminUsuarioSucursales.ts` — per-user branch assignment SWR.
 *
 * One cache entry per `usuarioUuid`. The list refreshes after
 * assign/unassign (callers pass `mutate` into the mutation handlers).
 *
 * The endpoint returns the user's currently OPEN branch assignments
 * (rows where `vigente_hasta IS NULL`), so the modal renders the
 * chips without any client-side filtering on `estado`.
 */
import useSWR from 'swr';

import { listAdminUsuarioSucursales } from '../api/adminUsuariosApi';
import type { AdminSucursalAsignadaRead } from '../api/adminUsuarioSchema';

function buildKey(uuid: string | null): string | null {
  return uuid === null ? null : `/api/v1/admin/usuarios/${uuid}/sucursales`;
}

export function useAdminUsuarioSucursales(
  usuarioUuid: string | null,
): {
  asignaciones: AdminSucursalAsignadaRead[] | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<AdminSucursalAsignadaRead[] | undefined>;
} {
  const { data, error, isLoading, mutate } = useSWR<AdminSucursalAsignadaRead[]>(
    buildKey(usuarioUuid),
    listAdminUsuarioSucursales,
    { revalidateOnFocus: false },
  );
  return { asignaciones: data, isLoading, error, refresh: mutate };
}
