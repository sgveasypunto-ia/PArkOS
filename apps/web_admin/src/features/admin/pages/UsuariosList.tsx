/**
 * `<UsuariosList />` — IT-1.4 + PR3 of the web_admin redesign, filter
 * bar + create-wizard added by HU-F16.2.
 *
 * Container that:
 *   - Lists every active admin/operator user via SWR.
 *   - Filters that list client-side by rol / sucursal / estado
 *     (HU-F16.2) -- `GET /admin/usuarios` takes no query params and the
 *     endpoint is already bounded to 100 rows (see
 *     `AdminUsuarioTable.tsx`'s docblock), so filtering the already-
 *     fetched page is the right shape here, not a server round-trip.
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
 */
import { useMemo, useState } from 'react';
import * as React from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';

import { useSucursalOptions } from '@/features/sucursales/hooks/useSucursalesDirectorio';

import { AdminUsuarioTable } from '../components/AdminUsuarioTable';
import { AdminUsuarioSucursalesManager } from '../components/AdminUsuarioSucursalesManager';
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

  const [createOpen, setCreateOpen] = useState(false);
  const [assignTarget, setAssignTarget] = useState<AdminUsuarioRead | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [filtros, setFiltros] = useState<UsuariosFiltros>(FILTROS_VACIOS);

  const branchDirectory = useSucursalOptions();

  const filteredUsuarios = useMemo(
    () => filterUsuarios(usuarios ?? [], filtros),
    [usuarios, filtros],
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
      className="flex min-h-screen flex-col gap-4 bg-background p-4"
      data-testid="page-usuarios"
    >
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">
            {t('gestionUsuarios.title', 'Gestión de usuarios')}
          </h1>
          <p className="text-muted-foreground text-sm">
            {t(
              'gestionUsuarios.subtitle',
              'Crea, lista y asigna sucursales a usuarios administradores y operadores.',
            )}
          </p>
        </div>
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
      </header>

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
          {t('gestionUsuarios.filtros.sucursalLabel', 'Sucursal')}
          <select
            data-testid="admin-filter-sucursal"
            value={filtros.sucursal}
            onChange={(e) => setFiltros((f) => ({ ...f, sucursal: e.target.value }))}
            className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="">{t('gestionUsuarios.filtros.todas', 'Todas')}</option>
            {branchDirectory.options.map((s) => (
              <option key={s.uuid} value={s.uuid}>
                {s.nombre ?? s.uuid}
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
