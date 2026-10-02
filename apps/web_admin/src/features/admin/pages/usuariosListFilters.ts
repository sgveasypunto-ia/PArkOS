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
 */
import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';

export interface UsuariosFiltros {
  rol: string;
  sucursal: string;
  estado: string;
}

export const FILTROS_VACIOS: UsuariosFiltros = { rol: '', sucursal: '', estado: '' };

/**
 * `''` on any field means "no filter" (matches the native `<select>`'s
 * empty "Todos/Todas" option). AND semantics across the three fields.
 */
export function filterUsuarios(
  rows: AdminUsuarioRead[],
  filtros: UsuariosFiltros,
): AdminUsuarioRead[] {
  return rows.filter((u) => {
    if (filtros.rol !== '' && u.rol !== filtros.rol) return false;
    if (filtros.estado !== '' && u.estado !== filtros.estado) return false;
    if (
      filtros.sucursal !== '' &&
      !u.sucursales.some((s) => s.uuid_sucursal === filtros.sucursal)
    ) {
      return false;
    }
    return true;
  });
}
