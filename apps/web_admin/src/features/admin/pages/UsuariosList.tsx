/**
 * `<UsuariosList />` — IT-1.4 + PR3 of the web_admin redesign.
 *
 * Container that:
 *   - Lists every active admin/operator user via SWR.
 *   - Lets the admin create a new user (modal with the original
 *     AdminUsuarioForm, unchanged contract).
 *   - Lets the admin assign/unassign branches per user via the
 *     AdminUsuarioSucursalesManager modal.
 *
 * Edit by row is intentionally NOT exposed: the backend has no
 * PUT `/admin/usuarios/{uuid}` endpoint, so any "Editar" button
 * would silently no-op. The roadmap lists this as a follow-up.
 *
 * Cross-branch scope: the list is global by design (IT-1.4 admin
 * user management is admin-wide, not per-sucursal). The picker
 * switch does NOT invalidate this list.
 */
import { useState } from 'react';
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';

import type { BranchOption } from '@/components/branch-selector/BranchSelector';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';

import { useSucursalOptions } from '@/features/sucursales/hooks/useSucursalesDirectorio';

import { AdminUsuarioForm } from '../components/AdminUsuarioForm';
import { AdminUsuarioTable } from '../components/AdminUsuarioTable';
import { AdminUsuarioSucursalesManager } from '../components/AdminUsuarioSucursalesManager';
import {
  adminUsuarioCreateSchema,
  type AdminUsuarioCreateInput,
  type AdminUsuarioRead,
} from '../api/adminUsuarioSchema';
import { useAdminUsuarios } from '../hooks/useAdminUsuarios';

function CreateUserForm(props: {
  onSubmit: (values: AdminUsuarioCreateInput) => void;
  isSubmitting: boolean;
  availableBranches: BranchOption[];
}): JSX.Element {
  const form = useForm<AdminUsuarioCreateInput>({
    resolver: zodResolver(adminUsuarioCreateSchema),
    defaultValues: {
      email: '',
      password: '',
      rol: 'operador',
      nombre: '',
      apellido: '',
      cedula: '',
      sucursales_asignadas: [],
    },
  });
  return (
    <AdminUsuarioForm
      form={form}
      onSubmit={props.onSubmit}
      isSubmitting={props.isSubmitting}
      availableBranches={props.availableBranches}
    />
  );
}

export default function UsuariosList(): JSX.Element {
  const { t } = useTranslation();

  const { usuarios, isLoading, error, refresh, create, assignBranch, unassignBranch } =
    useAdminUsuarios();

  const [createOpen, setCreateOpen] = useState(false);
  const [assignTarget, setAssignTarget] = useState<AdminUsuarioRead | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // Which row in the table has its Sucursales panel expanded. Mutually
  // exclusive: opening one row closes the previous. Keeping the state
  // at the page level lets the table itself stay a pure renderer.
  const [expandedUserUuid, setExpandedUserUuid] = useState<string | null>(null);

  const branchDirectory = useSucursalOptions();

  // Per-user branch assignments are intentionally NOT preloaded here.
  // The lazy row panel in AdminUsuarioTable reads them on demand via
  // the shared `useAdminUsuarioSucursales` SWR hook, and `assignBranch`
  // / `unassignBranch` invalidate that per-user key so the modal and
  // the table's panel stay in sync without an extra round-trip.

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

      <AdminUsuarioTable
        rows={usuarios ?? []}
        isLoading={isLoading}
        expandedUserUuid={expandedUserUuid}
        onToggleExpanded={(uuid) =>
          setExpandedUserUuid((prev) => (prev === uuid ? null : uuid))
        }
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

            {createError !== null && (
              <p
                role="alert"
                aria-live="assertive"
                className="mt-3 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                data-testid="admin-create-error"
              >
                {createError}
              </p>
            )}

            <div className="mt-4">
              <CreateUserForm
                onSubmit={onCreate}
                isSubmitting={submitting}
                availableBranches={branchDirectory.options}
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
