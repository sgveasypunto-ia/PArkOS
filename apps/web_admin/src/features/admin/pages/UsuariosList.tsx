/**
 * `<UsuariosList />` — admin user management page (IT-1.4).
 *
 * Container that loads active branches via SWR (for the branch
 * assignment checkboxes) and renders an `<AdminUsuarioForm />` that
 * POSTs to `/api/v1/admin/usuarios` with the chosen
 * `sucursales_asignadas`.
 *
 * Why a focused create-only page: the IT-1.4 endpoint already supports
 * editing via the `POST /admin/usuarios/{uuid}/sucursales` and
 * `DELETE /admin/usuarios/{uuid}/sucursales/{sucursal_uuid}` siblings
 * (PR2). Adding list/edit UI here is out of scope for IT-1.4.
 */
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { AdminUsuarioForm } from '../components/AdminUsuarioForm';
import { createAdminUsuario } from '../api/adminUsuariosApi';
import { adminUsuarioCreateSchema, type AdminUsuarioCreateInput } from '../api/adminUsuarioSchema';
import { parkosFetchRaw } from '@/lib/fetch';

interface BranchOption {
  uuid: string;
  nombre: string | null;
}

export default function UsuariosList() {
  const { t } = useTranslation();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successUuid, setSuccessUuid] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // List of permitted branches — admin can only assign users to branches
  // they have access to (sucursales_permitidas from JWT).
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

  const branches = useSWR<BranchOption[]>(
    '/api/v1/sucursales',
    async () => {
      const res = await parkosFetchRaw('/api/v1/sucursales', {
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as { items: BranchOption[] };
      return body.items ?? [];
    },
    { revalidateOnFocus: false },
  );

  const onSubmit = async (values: AdminUsuarioCreateInput) => {
    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessUuid(null);
    try {
      const created = await createAdminUsuario(values);
      setSuccessUuid(created.uuid);
      form.reset({
        email: '',
        password: '',
        rol: 'operador',
        nombre: '',
        apellido: '',
        cedula: '',
        sucursales_asignadas: [],
      });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'unknown error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main
      className="flex min-h-screen flex-col gap-4 bg-background p-4"
      data-testid="page-usuarios"
    >
      <header>
        <h1 className="text-2xl font-semibold">{t('admin.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('admin.subtitle')}</p>
      </header>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>{t('admin.createTitle')}</CardTitle>
        </CardHeader>
        <CardContent>
          {successUuid && (
            <p
              role="status"
              aria-live="polite"
              data-testid="admin-success"
              className="mb-3 rounded-md border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300"
            >
              {t('admin.created', { uuid: successUuid })}
            </p>
          )}

          {errorMessage && (
            <p
              role="alert"
              aria-live="assertive"
              data-testid="admin-error"
              className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {errorMessage}
            </p>
          )}

          <AdminUsuarioForm
            form={form}
            onSubmit={onSubmit}
            isSubmitting={isSubmitting}
            availableBranches={branches.data ?? []}
          />
        </CardContent>
      </Card>
    </main>
  );
}
