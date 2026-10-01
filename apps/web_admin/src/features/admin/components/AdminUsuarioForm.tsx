/**
 * `<AdminUsuarioForm />` — presentational form for creating an admin
 * user with optional branch assignment (IT-1.4).
 *
 * Container/Presentational split (mirror of `LoginForm` /
 * `SucursalForm`):
 *   - Container `<UsuariosList />` owns submit state, error state,
 *     and the HTTP call.
 *   - This component renders the RHF form fields. The password field
 *     is plaintext at the edge — bcrypt happens server-side.
 *
 * Accessibility (RNF-022 WCAG 2.1 AA):
 *   - Every input has `<FormLabel htmlFor>` paired with `id`.
 *   - Zod errors surface via `<FormMessage role="alert">`.
 *   - Submit button shows "submitting" copy while pending.
 *   - Branch assignment is OPTIONAL — the user can be created
 *     without any branches and have them attached later via
 *     `POST /admin/usuarios/{uuid}/sucursales`.
 */
import { useState } from 'react';
import type { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';

import { ROLES, type AdminUsuarioCreateInput } from '../api/adminUsuarioSchema';

export interface AdminUsuarioFormProps {
  form: ReturnType<typeof useForm<AdminUsuarioCreateInput>>;
  onSubmit: (values: AdminUsuarioCreateInput) => void;
  isSubmitting: boolean;
  /** Available branch UUIDs to choose from for `sucursales_asignadas`. */
  availableBranches: { uuid: string; nombre: string | null }[];
}

export function AdminUsuarioForm({
  form,
  onSubmit,
  isSubmitting,
  availableBranches,
}: AdminUsuarioFormProps) {
  const { t } = useTranslation();
  const [showOptional, setShowOptional] = useState(false);

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="admin-usuario-form"
      >
        <fieldset disabled={isSubmitting} className="space-y-4">
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="email">{t('admin.email')}</FormLabel>
                <FormControl>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="username"
                    data-testid="admin-field-email"
                    {...field}
                    value={field.value ?? ''}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="password">{t('admin.password')}</FormLabel>
                <FormControl>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="new-password"
                    data-testid="admin-field-password"
                    {...field}
                    value={field.value ?? ''}
                  />
                </FormControl>
                <FormDescription>{t('admin.passwordHelp')}</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="rol"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="rol">{t('admin.rol')}</FormLabel>
                <FormControl>
                  <select
                    id="rol"
                    data-testid="admin-field-rol"
                    {...field}
                    value={field.value ?? 'operador'}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {t(`admin.rol.${r}`)}
                      </option>
                    ))}
                  </select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <button
            type="button"
            onClick={() => setShowOptional((s) => !s)}
            className="text-xs text-muted-foreground underline"
            data-testid="admin-toggle-optional"
          >
            {showOptional ? t('admin.hideOptional') : t('admin.showOptional')}
          </button>

          {showOptional && (
            <div className="space-y-4 rounded-md border bg-muted/40 p-3">
              <FormField
                control={form.control}
                name="nombre"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="nombre">{t('admin.nombre')}</FormLabel>
                    <FormControl>
                      <Input
                        id="nombre"
                        data-testid="admin-field-nombre"
                        {...field}
                        value={field.value ?? ''}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="apellido"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="apellido">{t('admin.apellido')}</FormLabel>
                    <FormControl>
                      <Input
                        id="apellido"
                        data-testid="admin-field-apellido"
                        {...field}
                        value={field.value ?? ''}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="cedula"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="cedula">{t('admin.cedula')}</FormLabel>
                    <FormControl>
                      <Input
                        id="cedula"
                        data-testid="admin-field-cedula"
                        {...field}
                        value={field.value ?? ''}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />

              <div>
                <span className="mb-2 block text-sm font-medium">{t('admin.sucursalesLabel')}</span>
                {availableBranches.length === 0 && (
                  <p className="text-xs text-muted-foreground" data-testid="admin-no-branches">
                    {t('admin.noBranchesAvailable')}
                  </p>
                )}
                {availableBranches.map((b) => (
                  <FormField
                    key={b.uuid}
                    control={form.control}
                    name="sucursales_asignadas"
                    render={({ field }) => {
                      const value: string[] = Array.isArray(field.value) ? field.value : [];
                      const checked = value.includes(b.uuid);
                      return (
                        <FormItem>
                          <label
                            htmlFor={`sucursal-${b.uuid}`}
                            className="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1 text-sm hover:bg-accent/40"
                          >
                            <input
                              id={`sucursal-${b.uuid}`}
                              type="checkbox"
                              data-testid={`admin-branch-${b.uuid}`}
                              checked={checked}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  field.onChange([...value, b.uuid]);
                                } else {
                                  field.onChange(value.filter((u) => u !== b.uuid));
                                }
                              }}
                              className="h-4 w-4 rounded border-input"
                            />
                            <span>{b.nombre ?? b.uuid}</span>
                          </label>
                        </FormItem>
                      );
                    }}
                  />
                ))}
              </div>
            </div>
          )}
        </fieldset>

        <Button type="submit" className="w-full" disabled={isSubmitting} data-testid="admin-submit">
          {isSubmitting ? t('admin.submitting') : t('admin.submit')}
        </Button>
      </form>
    </Form>
  );
}
