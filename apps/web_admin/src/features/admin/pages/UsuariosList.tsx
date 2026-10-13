/**
 * `<UsuariosList />` — IT-1.4 + PR3 of the web_admin redesign, filter
 * bar + create-wizard added by HU-F16.2; page-local free-text search
 * added by HU-F9.
 *
 * Container that:
 *   - Lists every active admin/operator user via SWR.
 *   - Filters that list client-side by rol / estado / search query /
 *     sucursal (HU-F16.2 + HU-F9) -- `GET /admin/usuarios` takes no
 *     query params and the endpoint is already bounded to 100 rows
 *     (see `AdminUsuarioTable.tsx`'s docblock), so filtering the
 *     already-fetched page is the right shape here, not a server
 *     round-trip.
 *   - Lets the admin create a new user via the 3-step `<UsuarioCrear />`
 *     wizard (HU-F16.2 -- replaces the old single-shot
 *     `AdminUsuarioForm`/`CreateUserForm` for the CREATE flow only).
 *   - Lets the admin assign/unassign branches per user via the
 *     AdminUsuarioSucursalesManager modal.
 *
 * Field editing lives on the detail screen (`/usuarios/{uuid}`), which
 * the table links to from the email and the "Detalle" button. That
 * screen (`features/usuarios/pages/UsuarioDetalle.tsx`) uses a totally
 * separate component tree (`UsuarioForm.tsx` under `features/usuarios/`)
 * and its own Zod schemas (`features/usuarios/api/usuariosSchema.ts`) --
 * it is NOT touched by the HU-F16.2 wizard, which only replaces the
 * CREATE flow on this page.
 *
 * Cross-branch scope: the list is global by design (IT-1.4 admin
 * user management is admin-wide, not per-sucursal). The picker
 * switch does NOT invalidate this list.
 *
 * Branch picker (HU-X.8 + HU-F9 follow-ups): the inline
 * `<SucursalFilterCombobox>` lives in the page header (same row as
 * the "+ Nuevo usuario" button) so the layout mirrors the reporteria
 * surfaces (`/reporteria`, `/reporteria/financiera`). The combobox
 * writes through to the global `SucursalContext` (same hook as the
 * topbar BranchSelector and the same hook as `/reporteria/financiera`,
 * `/cupos`, `/tarifas`, `/reporteria`). Picking a branch here ALSO
 * changes the topbar selection -- that is the intended write-through
 * behaviour. The picker now offers a "Todas las sucursales"
 * pseudo-option (HU-F9) that sets `selected = null` and shows every
 * user across all permitted branches.
 *
 * Search (HU-F9) + filter row (HU-fix-usuarios-alignment): the
 * `<UsuarioSearchInput>` and the `rol` / `estado` selects are all
 * peers inside a single flex cluster below the page header
 * (`data-testid="admin-filtros"`), so the four filters are visually
 * grouped (search, rol, estado) and the branch picker stays alone
 * in the header next to the "+ Nuevo usuario" button. The search
 * filters the already-fetched list by `email`, `nombre`, and
 * `apellido` (case-insensitive `includes`). Clearing the search is
 * a no-op against the rest of the filters (rol / estado / branch).
 *
 * HU-fix-usuarios-alignment: the "Actual: <nombre>" hint that used
 * to render below the SucursalFilterCombobox's input was removed
 * at the component source (one component, three call sites aligned
 * at once). The hint was redundant with the input's own value and
 * was breaking the vertical alignment of the page header's `flex
 * items-end` cluster: the extra paragraph made the combobox column
 * taller than the search input (label+input) and the "+ Nuevo
 * usuario" button, so the input visually shifted upward. Removing
 * it leaves the three columns at the same effective height.
 */
import { useMemo, useState } from 'react';
import * as React from 'react';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { useSucursal } from '@/lib/sucursal-context';

import { useSucursalOptions } from '@/features/sucursales/hooks/useSucursalesDirectorio';

import { AdminUsuarioTable } from '../components/AdminUsuarioTable';
import { AdminUsuarioSucursalesManager } from '../components/AdminUsuarioSucursalesManager';
import { SucursalFilterCombobox } from '../components/SucursalFilterCombobox';
import { UsuarioSearchInput } from '../components/UsuarioSearchInput';
import {
  ESTADOS,
  ROLES,
  type AdminUsuarioCreateInput,
  type AdminUsuarioRead,
} from '../api/adminUsuarioSchema';
import { useAdminUsuarios } from '../hooks/useAdminUsuarios';
import { UsuarioCrear } from './UsuarioCrear';
import { FILTROS_VACIOS, filterUsuarios, type UsuariosFiltros } from './usuariosListFilters';

export default function UsuariosList(): JSX.Element {
  const { t } = useTranslation();

  const { usuarios, isLoading, error, refresh, create, assignBranch, unassignBranch } =
    useAdminUsuarios();

  const { selected: selectedSucursal, setSelected } = useSucursal();

  const [createOpen, setCreateOpen] = useState(false);
  const [assignTarget, setAssignTarget] = useState<AdminUsuarioRead | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [filtros, setFiltros] = useState<UsuariosFiltros>(FILTROS_VACIOS);

  const branchDirectory = useSucursalOptions();

  const filteredUsuarios = useMemo(
    () => filterUsuarios(usuarios ?? [], filtros, selectedSucursal),
    [usuarios, filtros, selectedSucursal],
  );

  // Branch assignments are rendered INLINE in the table from
  // `user.sucursales` (embedded by the backend on the list payload),
  // so no per-row fetch is needed here. Mutations from the assignment
  // modal call `assignBranch` / `unassignBranch`, which revalidate the
  // list key (`useAdminUsuarios`) — the table chips refresh in place.

  async function onCreate(values: AdminUsuarioCreateInput): Promise<void> {
    setSubmitting(true);
    setCreateError(null);
    try {
      await create(values);
      setCreateOpen(false);
      await refresh();
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'error');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main
      className="flex flex-1 flex-col gap-6 bg-background p-4 md:p-6 lg:p-8"
      data-testid="page-usuarios"
    >
      <PageHeader
        title={t('gestionUsuarios.title', 'Gestión de usuarios')}
        subtitle={t(
          'gestionUsuarios.subtitle',
          'Crea, lista y asigna sucursales a usuarios administradores y operadores.',
        )}
        actions={
          <div className="flex flex-wrap items-end gap-3">
            <SucursalFilterCombobox
              options={branchDirectory.sucursales.map((s) => ({
                uuid: s.uuid,
                nombre: s.nombre,
                prefijo_nombre: s.prefijo_nombre,
              }))}
              value={selectedSucursal ?? ''}
              onChange={(uuid) => setSelected(uuid || null)}
              label={t('gestionUsuarios.filtros.sucursalLabel', 'Sucursal')}
              placeholder={t(
                'gestionUsuarios.filtros.sucursalCombobox.search',
                'Buscar por nombre, prefijo o UUID…',
              )}
              allLabel={t(
                'gestionUsuarios.filtros.todas',
                'Todas las sucursales',
              )}
              testId="admin-filter-sucursal"
            />
            <Button
              type="button"
              onClick={() => {
                setCreateOpen(true);
                setCreateError(null);
              }}
              data-testid="admin-new"
            >
              {t('gestionUsuarios.newUser', '+ Nuevo usuario')}
            </Button>
          </div>
        }
      />

      {error !== undefined && (
        <p
          role="alert"
          aria-live="assertive"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          data-testid="admin-error"
        >
          {t(
            'gestionUsuarios.error',
            'No se pudo cargar el listado. Reintentá.',
          )}
        </p>
      )}

      <div className="flex flex-wrap items-end gap-3" data-testid="admin-filtros">
        <UsuarioSearchInput
          value={filtros.search}
          onChange={(v) => setFiltros((f) => ({ ...f, search: v }))}
          testId="admin-search-usuario"
        />
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t('gestionUsuarios.filtros.rolLabel', 'Rol')}
          <select
            data-testid="admin-filter-rol"
            value={filtros.rol}
            onChange={(e) => setFiltros((f) => ({ ...f, rol: e.target.value }))}
            className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="">{t('gestionUsuarios.filtros.todos', 'Todos')}</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`admin.rol.${r}`)}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t('gestionUsuarios.filtros.estadoLabel', 'Estado')}
          <select
            data-testid="admin-filter-estado"
            value={filtros.estado}
            onChange={(e) => setFiltros((f) => ({ ...f, estado: e.target.value }))}
            className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="">{t('gestionUsuarios.filtros.todos', 'Todos')}</option>
            {ESTADOS.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
        </label>
      </div>

      <AdminUsuarioTable
        rows={filteredUsuarios}
        isLoading={isLoading}
        onAssignSucursales={(u) => setAssignTarget(u)}
      />

      {/* Create modal */}
      <Dialog
        open={createOpen}
        onOpenChange={(o) => {
          if (!o) setCreateOpen(false);
        }}
        contentProps={
          {
            'data-testid': 'admin-create-modal',
          } as React.HTMLAttributes<HTMLDivElement> & {
            'data-testid'?: string;
          }
        }
      >
        <Card className="mx-auto max-w-2xl shadow-elevation-2">
          <CardContent className="p-6">
            <DialogTitle>
              {t('gestionUsuarios.modal.create', 'Crear nuevo usuario')}
            </DialogTitle>
            <DialogDescription>
              {t(
                'gestionUsuarios.modal.createDescription',
                'Cargá los datos del usuario. La contraseña se cifra (bcrypt) en el servidor.',
              )}
            </DialogDescription>

            <div className="mt-4">
              <UsuarioCrear
                onSubmit={onCreate}
                isSubmitting={submitting}
                availableBranches={branchDirectory.options}
                submitError={createError}
              />
            </div>
          </CardContent>
        </Card>
      </Dialog>

      {/* Assign-sucursales modal */}
      <AdminUsuarioSucursalesManager
        user={assignTarget}
        onClose={() => setAssignTarget(null)}
        onAssign={assignBranch}
        onUnassign={unassignBranch}
      />
    </main>
  );
}
