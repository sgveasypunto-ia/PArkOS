/**
 * `AdminUsuarioTable.tsx` — accessible HTML <table> rendering every
 * active admin/operator with their current branch assignments.
 *
 * Decisions (PR3 of the web_admin redesign, HU-F16.col):
 *   - HTML <table> semantic, no library. The dataset is bounded by
 *     `GET /admin/usuarios` which returns at most 100 active rows.
 *     Client-side pagination slices that list; we are NOT loading
 *     thousands of rows.
 *   - <caption class="sr-only"> + <th scope="col"> wired so axe-core
 *     keeps WCAG 2.1 AA green.
 *   - "Sucursales" column is LAZY: the cell shows a "Ver" / "Ocultar"
 *     toggle, and the assignment list is fetched only when the cell is
 *     expanded via the existing `useAdminUsuarioSucursales` hook. This
 *     keeps the table free of the N+1 we removed in commit 812badc: no
 *     request fires on render. SWR's per-key cache means re-opening a
 *     row that was already loaded (e.g. by the assignment modal) costs
 *     zero.
 *   - Mutual exclusion of the expanded cell (`expandedUserUuid: string
 *     | null`) prevents the user from leaving N panels open and
 *     turning the table into a streaming waterfall.
 *   - Actions column exposes "Asignar sucursales" (opens the manager
 *     modal). Edit is intentionally out of scope: the backend has no
 *     PUT endpoint, so the UI cannot mutate fields other than the
 *     branch list.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';

import { useAdminUsuarioSucursales } from '../hooks/useAdminUsuarioSucursales';
import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';

export interface AdminUsuarioTableProps {
  rows: AdminUsuarioRead[];
  isLoading: boolean;
  /**
   * UUID of the row whose Sucursales panel is currently expanded.
   * `null` means no row is expanded. The table does not own this
   * state; the parent page does, so two tables (none today, but future)
   * could share it.
   */
  expandedUserUuid: string | null;
  /** Toggle handler. Pass the same uuid to close it, another to switch. */
  onToggleExpanded: (usuarioUuid: string) => void;
  onAssignSucursales: (user: AdminUsuarioRead) => void;
}

function displayName(user: AdminUsuarioRead): string {
  const full = [user.nombre, user.apellido].filter(Boolean).join(' ');
  return full || user.email || user.uuid.slice(0, 8);
}

/**
 * Panel rendered inside the Sucursales cell. Owns its own SWR via the
 * shared `useAdminUsuarioSucursales` hook, so when the same user was
 * already loaded by the assignment modal this component reads the cache
 * and renders synchronously without a network round-trip. There is
 * exactly ONE instance per row in the DOM, keyed off `isExpanded` at
 * the call site, so the data-testids cannot collide.
 */
function SucursalesPanel({
  usuarioUuid,
  panelId,
}: {
  usuarioUuid: string;
  panelId: string;
}): JSX.Element {
  const { t } = useTranslation();
  const { asignaciones, isLoading, error } = useAdminUsuarioSucursales(usuarioUuid);
  const { sucursales, isLoading: directoryLoading } = useSucursalesDirectorio();

  const directoryByUuid = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of sucursales) {
      if (s.nombre) map.set(s.uuid, s.nombre);
    }
    return map;
  }, [sucursales]);

  // Show the loading state until BOTH the per-user assignments and
  // the shared branch directory have settled. Without this, the first
  // open of a row would render the short-uuid fallback instead of the
  // friendly name, because the directory cache can be empty until the
  // fetch resolves.
  if (isLoading || directoryLoading) {
    return (
      <p
        role="status"
        aria-live="polite"
        className="text-muted-foreground text-xs"
        data-testid={`admin-row-${usuarioUuid}-panel-loading`}
      >
        {t('gestionUsuarios.sucursales.loading', 'Cargando sucursales…')}
      </p>
    );
  }

  if (error !== undefined) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        className="text-destructive text-xs"
        data-testid={`admin-row-${usuarioUuid}-panel-error`}
      >
        {t(
          'gestionUsuarios.sucursales.error',
          'No se pudieron cargar las sucursales.',
        )}
      </p>
    );
  }

  const items = asignaciones ?? [];

  if (items.length === 0) {
    return (
      <p
        className="text-muted-foreground text-xs"
        data-testid={`admin-row-${usuarioUuid}-panel-empty`}
      >
        {t('gestionUsuarios.sucursales.empty', 'Sin sucursales asignadas.')}
      </p>
    );
  }

  return (
    <ul
      id={panelId}
      className="flex flex-wrap gap-1"
      aria-label={t(
        'gestionUsuarios.sucursales.panelLabel',
        'Sucursales asignadas',
      )}
    >
      {items.map((a) => {
        const label = directoryByUuid.get(a.uuid_sucursal) ?? a.uuid_sucursal.slice(0, 8);
        return (
          <li key={a.uuid_sucursal}>
            <Badge
              variant="secondary"
              data-testid={`admin-row-${usuarioUuid}-chip-${a.uuid_sucursal}`}
            >
              <span>{label}</span>
            </Badge>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Cell content for the Sucursales column. Encapsulates the toggle and
 * the panel; the table body stays linear.
 */
function SucursalesCell({
  user,
  expandedUserUuid,
  onToggleExpanded,
}: {
  user: AdminUsuarioRead;
  expandedUserUuid: string | null;
  onToggleExpanded: (usuarioUuid: string) => void;
}): JSX.Element {
  const { t } = useTranslation();
  const isExpanded = expandedUserUuid === user.uuid;
  const panelId = `admin-row-${user.uuid}-panel`;

  // The pre-count is intentionally NOT fetched here. Showing a count
  // would mean a request per row at render time, which is the N+1 we
  // removed. The label stays as "Ver" / "Ocultar"; the count is
  // available in the panel itself once the user opens it.
  return (
    <div className="flex flex-col gap-1">
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => onToggleExpanded(user.uuid)}
        aria-expanded={isExpanded}
        aria-controls={panelId}
        data-testid={`admin-row-${user.uuid}-toggle-sucursales`}
      >
        {isExpanded
          ? t('gestionUsuarios.sucursales.hide', 'Ocultar')
          : t('gestionUsuarios.sucursales.view', 'Ver')}
      </Button>
      {isExpanded && <SucursalesPanel usuarioUuid={user.uuid} panelId={panelId} />}
    </div>
  );
}

export function AdminUsuarioTable({
  rows,
  isLoading,
  expandedUserUuid,
  onToggleExpanded,
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
                <SucursalesCell
                  user={user}
                  expandedUserUuid={expandedUserUuid}
                  onToggleExpanded={onToggleExpanded}
                />
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
