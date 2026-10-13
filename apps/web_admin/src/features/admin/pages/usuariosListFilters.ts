/**
 * `usuariosListFilters.ts` — pure filtering helper for `<UsuariosList />`
 * (HU-F16.2, filtro por rol/sucursal/estado).
 *
 * Kept in its own module (not inline in `UsuariosList.tsx`) for two
 * reasons: it is directly unit-testable without rendering/mocking SWR
 * or fetch, and co-locating a non-component export in a page file trips
 * `react-refresh/only-export-components` (the page file must export
 * only the default component for Fast Refresh to work).
 *
 * `GET /admin/usuarios` takes no query params and is already bounded to
 * 100 rows (see `AdminUsuarioTable.tsx`'s docblock), so filtering the
 * already-fetched page client-side is the right shape here, not a
 * server round-trip.
 *
 * HU-X.8 follow-up: the branch filter was pulled out of the local
 * `UsuariosFiltros` state and now follows the global `SucursalContext`
 * (`useSucursal().selected`). The combobox writes through to
 * `setSelected`, so the topbar and the page filter stay in sync and
 * the only way to see users from "all branches" is to clear the
 * global context (the existing topbar `Cambiar sucursal` flow).
 */
import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';

export interface UsuariosFiltros {
  rol: string;
  estado: string;
}

export const FILTROS_VACIOS: UsuariosFiltros = { rol: '', estado: '' };

/**
 * `''` on rol/estado means "no filter" (matches the native `<select>`'s
 * empty "Todos/Todas" option). AND semantics across the three fields.
 *
 * The branch filter takes a separate `sucursalUuid` parameter because
 * the page no longer holds it locally — it follows the global
 * `SucursalContext`. Pass `null` to disable the branch filter
 * (the page falls back to this when the admin has not picked a branch
 * yet, showing every user across all permitted branches).
 */
export function filterUsuarios(
  rows: AdminUsuarioRead[],
  filtros: UsuariosFiltros,
  sucursalUuid: string | null,
): AdminUsuarioRead[] {
  return rows.filter((u) => {
    if (filtros.rol !== '' && u.rol !== filtros.rol) return false;
    if (filtros.estado !== '' && u.estado !== filtros.estado) return false;
    if (
      sucursalUuid !== null &&
      !u.sucursales.some((s) => s.uuid_sucursal === sucursalUuid)
    ) {
      return false;
    }
    return true;
  });
}
