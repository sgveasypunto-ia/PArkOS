/**
 * `AdminUsuarioTable.tsx` — accessible HTML <table> rendering every
 * active admin/operator with their currently-open branch assignments.
 *
 * Decisions (PR3 of the web_admin redesign, HU-F16.col):
 *   - HTML <table> semantic, no library. The dataset is bounded by
 *     `GET /admin/usuarios` which returns at most 100 active rows.
 *     Client-side pagination slices that list; we are NOT loading
 *     thousands of rows.
 *   - <caption class="sr-only"> + <th scope="col"> wired so axe-core
 *     keeps WCAG 2.1 AA green.
 *   - "Sucursales" column is INLINE: each row shows the chips
 *     directly from `user.sucursales`, which the backend embeds on
 *     the list endpoint (no per-row round-trip, no client-side
 *     directory lookup, no N+1). This replaces the previous
 *     "Ver / Ocultar" toggle + lazy panel that existed back when the
 *     backend returned one row at a time without the embedded
 *     assignments (commit 9330f93).
 *   - The assignment MODAL (`AdminUsuarioSucursalesManager`) still
 *     consumes the per-user endpoint (`/admin/usuarios/{uuid}/sucursales`)
 *     via `useAdminUsuarioSucursales` because the modal needs the
 *     full bi-temporal lifecycle fields, not just the summary.
 *   - Actions column exposes "Asignar sucursales" (opens the manager
 *     modal). Edit is intentionally out of scope: the backend has no
 *     PUT endpoint, so the UI cannot mutate fields other than the
 *     branch list.
 */
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import type {
  AdminUsuarioRead,
  SucursalAsignadaResumen,
} from '../api/adminUsuarioSchema';

export interface AdminUsuarioTableProps {
  rows: AdminUsuarioRead[];
  isLoading: boolean;
  onAssignSucursales: (user: AdminUsuarioRead) => void;
}

function displayName(user: AdminUsuarioRead): string {
  const full = [user.nombre, user.apellido].filter(Boolean).join(' ');
  return full || user.email || user.uuid.slice(0, 8);
}

/**
 * Fallback chain for a branch label when the backend payload has no
 * `nombre` (closed-branch assignment: the user keeps a vestigial link
 * to a branch whose currently-open version no longer exists).
 *
 *   1. ``nombre`` -- friendly name from the backend, populated when the
 *      branch's currently-open row is present.
 *   2. ``prefijo_nombre`` -- the human-meaningful prefix even when the
 *      branch itself has been closed.
 *   3. First 8 chars of the uuid -- last-resort stable identifier.
 */
function chipLabel(s: SucursalAsignadaResumen): string {
  return s.nombre ?? s.prefijo_nombre ?? s.uuid_sucursal.slice(0, 8);
}

/**
 * Cell content for the Sucursales column. Renders the user's
 * currently-open branch assignments as inline chips, directly from
 * `user.sucursales`. The backend embeds the list on the parent
 * ``GET /admin/usuarios`` payload, so no extra fetch fires here.
 *
 * Visual pattern matches the assignment modal (`AdminUsuarioSucursalesManager`)
 * -- same `<ul className="flex flex-wrap gap-1"><li><Badge>…</Badge></li></ul>`
 * structure -- so a row in the table and the modal show the same
 * chip styling for the same branch.
 */
function SucursalesCell({
  user,
}: {
  user: AdminUsuarioRead;
}): JSX.Element {
  const { t } = useTranslation();
  const items = user.sucursales ?? [];

  if (items.length === 0) {
    return (
      <span
        className="text-muted-foreground text-xs"
        data-testid={`admin-row-${user.uuid}-sucursales-empty`}
      >
        {t('gestionUsuarios.sucursales.empty', 'Sin sucursales asignadas.')}
      </span>
    );
  }

  return (
    <ul
      className="flex flex-wrap gap-1"
      aria-label={t(
        'gestionUsuarios.sucursales.panelLabel',
        'Sucursales asignadas',
      )}
      data-testid={`admin-row-${user.uuid}-sucursales-chips`}
    >
      {items.map((s) => (
        <li key={s.uuid_sucursal}>
          <Badge
            variant="secondary"
            data-testid={`admin-row-${user.uuid}-chip-${s.uuid_sucursal}`}
          >
            <span>{chipLabel(s)}</span>
          </Badge>
        </li>
      ))}
    </ul>
  );
}

export function AdminUsuarioTable({
  rows,
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
          {rows.map((user) => (
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
                <SucursalesCell user={user} />
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
