/**
 * `usuariosListFilters.ts` — pure filtering helper for `<UsuariosList />`
 * (HU-F16.2, filtro por rol/sucursal/estado; HU-F9, filtro por texto).
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
 * `setSelected`, so the topbar and the page filter stay in sync.
 *
 * HU-F9 follow-up: a free-text search (matches `email`, `nombre`, and
 * `apellido` case-insensitively) was added in the page header; it is
 * the ONLY field that lives in the same shape as the page-local filters
 * (rol, estado) because the search is page-scoped, not branch-scoped
 * (clearing the branch does NOT clear the search and vice versa).
 */
import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';

export interface UsuariosFiltros {
  rol: string;
  estado: string;
  /**
   * Free-text query. Empty string disables the filter. Compared
   * case-insensitively against `email`, `nombre`, and `apellido`.
   * "admin" matches `admin@parkos.local` and `Admin Dev` alike.
   */
  search: string;
}

export const FILTROS_VACIOS: UsuariosFiltros = { rol: '', estado: '', search: '' };

/**
 * `''` on rol/estado/search means "no filter" (matches the native
 * `<select>`'s empty "Todos/Todas" option AND the empty search box).
 * AND semantics across all four fields.
 *
 * The branch filter takes a separate `sucursalUuid` parameter because
 * the page no longer holds it locally — it follows the global
 * `SucursalContext`. Pass `null` to disable the branch filter (the
 * page falls back to this when the admin has not picked a branch
 * yet, or has explicitly picked "Todas las sucursales", showing every
 * user across all permitted branches).
 */
export function filterUsuarios(
  rows: AdminUsuarioRead[],
  filtros: UsuariosFiltros,
  sucursalUuid: string | null,
): AdminUsuarioRead[] {
  const q = filtros.search.trim().toLowerCase();
  return rows.filter((u) => {
    if (filtros.rol !== '' && u.rol !== filtros.rol) return false;
    if (filtros.estado !== '' && u.estado !== filtros.estado) return false;
    if (
      sucursalUuid !== null &&
      !u.sucursales.some((s) => s.uuid_sucursal === sucursalUuid)
    ) {
      return false;
    }
    if (q !== '') {
      const email = (u.email ?? '').toLowerCase();
      const fullName = [u.nombre, u.apellido]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      if (!email.includes(q) && !fullName.includes(q)) return false;
    }
    return true;
  });
}
