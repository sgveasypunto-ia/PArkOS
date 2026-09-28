/**
 * `AdminUsuarioTable.tsx` — accessible HTML <table> rendering every
 * active admin/operator with their current branch assignments.
 *
 * Decisions (PR3 of the web_admin redesign):
 *   - HTML <table> semantic, no library. The dataset is bounded by
 *     `GET /admin/usuarios` which returns at most 100 active rows.
 *     Client-side pagination slices that list; we are NOT loading
 *     thousands of rows.
 *   - <caption class="sr-only"> + <th scope="col"> wired so axe-core
 *     keeps WCAG 2.1 AA green.
 *   - "Sucursales" column renders one <Badge> per assignment with a
 *     data-testid pattern that the e2e spec asserts against. The
 *     Badge label is the UUID short prefix when no friendly name is
 *     cached yet — never a UUID slice that's actually a role.
 *   - Actions column exposes "Asignar sucursales" (opens the manager
 *     modal). Edit is intentionally out of scope: the backend has no
 *     PUT endpoint, so the UI cannot mutate fields other than the
 *     branch list.
 */
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';

export interface SucursalChip {
  uuid: string;
  nombre?: string | null;
}

export interface AdminUsuarioTableProps {
  rows: AdminUsuarioRead[];
  /** Map of user_uuid -> branch assignments for the listed users. */
  asignacionesByUser: Record<string, SucursalChip[]>;
  isLoading: boolean;
  onAssignSucursales: (user: AdminUsuarioRead) => void;
}

function displayName(user: AdminUsuarioRead): string {
  const full = [user.nombre, user.apellido].filter(Boolean).join(' ');
  return full || user.email || user.uuid.slice(0, 8);
}

export function AdminUsuarioTable({
  rows,
  asignacionesByUser,
  isLoading,
  onAssignSucursales,
}: AdminUsuarioTableProps): JSX.Element {
  const { t } = useTranslation();

  if (isLoading && rows.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        className="text-sm text-muted-foreground"
        data-testid="admin-table-loading"
      >
        {t('gestionUsuarios.loading', 'Cargando usuarios…')}
      </p>
    );
  }

  if (rows.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        className="text-sm text-muted-foreground"
        data-testid="admin-table-empty"
      >
        {t(
          'gestionUsuarios.empty',
          'Aún no hay usuarios administradores. Creá el primero con "+ Nuevo usuario".',
        )}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <caption className="sr-only">
          {t(
            'gestionUsuarios.tableCaption',
            'Listado de usuarios administradores y operadores',
          )}
        </caption>
        <thead>
          <tr className="border-b bg-muted/40 text-left">
            <th scope="col" className="px-3 py-2">
              {t('gestionUsuarios.table.email', 'Correo')}
            </th>
            <th scope="col" className="px-3 py-2">
              {t('gestionUsuarios.table.nombre', 'Nombre')}
            </th>
            <th scope="col" className="px-3 py-2">
              {t('gestionUsuarios.table.rol', 'Rol')}
            </th>
            <th scope="col" className="px-3 py-2">
              {t('gestionUsuarios.table.sucursales', 'Sucursales')}
            </th>
            <th scope="col" className="px-3 py-2">
              {t('gestionUsuarios.table.estado', 'Estado')}
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              {t('gestionUsuarios.table.acciones', 'Acciones')}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((user) => {
            const chips = asignacionesByUser[user.uuid] ?? [];
            return (
              <tr
                key={user.uuid}
                data-testid={`admin-row-${user.uuid}`}
                className="border-b last:border-b-0"
              >
                <th
                  scope="row"
                  className="px-3 py-2 text-left align-top font-normal"
                >
                  <span className="block font-medium">{user.email ?? '—'}</span>
                  <span className="text-muted-foreground block font-mono text-[11px]">
                    {user.uuid}
                  </span>
                </th>
                <td className="px-3 py-2 align-top">{displayName(user)}</td>
                <td className="px-3 py-2 align-top">
                  <Badge variant="outline">{user.rol ?? '—'}</Badge>
                </td>
                <td className="px-3 py-2 align-top">
                  {chips.length === 0 ? (
                    <span className="text-muted-foreground text-xs">
                      {t('gestionUsuarios.table.sinSucursales', '—')}
                    </span>
                  ) : (
                    <ul className="flex flex-wrap gap-1" aria-label="Sucursales">
                      {chips.map((chip) => (
                        <li key={chip.uuid}>
                          <Badge
                            variant="secondary"
                            data-testid={`admin-row-${user.uuid}-sucursal-${chip.uuid}`}
                          >
                            {chip.nombre ?? chip.uuid.slice(0, 8)}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
                <td className="px-3 py-2 align-top">
                  <Badge
                    variant={user.estado === 'activo' ? 'success' : 'outline'}
                  >
                    {user.estado}
                  </Badge>
                </td>
                <td className="px-3 py-2 align-top text-right">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onAssignSucursales(user)}
                    data-testid={`admin-row-${user.uuid}-assign`}
                  >
                    {t('gestionUsuarios.actions.assignSucursales', 'Asignar sucursales')}
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
