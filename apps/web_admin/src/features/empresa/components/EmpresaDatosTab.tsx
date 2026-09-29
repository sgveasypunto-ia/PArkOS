/**
 * `EmpresaDatosTab` — tab "Datos" del singleton Empresa
 * (HU-F15.2 de `plan.md:3537`).
 *
 * Form con RHF + Zod (`empresaUpdateSchema`) con tres campos:
 *   - `nombre`: razón social (string, requerido, max 255).
 *   - `nit`: NIT colombiano. Validación adicional inline con
 *     `validarNitModulo11` (T1) para mostrar el detalle del cálculo
 *     (DV esperado vs recibido) ANTES del round-trip al backend.
 *   - `regimen`: dropdown nativo con `comun` / `simplificado` (el
 *     schema Pydantic acepta string libre; el cliente restringe a
 *     estas dos opciones para evitar 422 silenciosos).
 *
 * Container/presentational split (mirror de `SucursalForm`):
 *   - `<EmpresaDatosTab />` es el contenedor: maneja loading, submit
 *     y mutación del SWR cache.
 *   - `<EmpresaDatosForm />` es presentational: recibe el form y
 *     maneja solo el render.
 */
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';

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
import { validarNitModulo11 } from '@/lib/validation/nit';

import {
  empresaUpdateSchema,
  type Empresa,
  type EmpresaUpdateInput,
} from '../api/empresaSchema';
import { updateEmpresa } from '../api/empresaApi';
import { useEmpresa } from '../hooks/useEmpresa';

interface EmpresaDatosFormProps {
  form: ReturnType<typeof useForm<EmpresaUpdateInput>>;
  onSubmit: (values: EmpresaUpdateInput) => void;
  isSubmitting: boolean;
}

function EmpresaDatosForm({
  form,
  onSubmit,
  isSubmitting,
}: EmpresaDatosFormProps): JSX.Element {
  const { t } = useTranslation();
  const nitValue = form.watch('nit');

  // Validación módulo 11 inline — solo se muestra si el NIT tiene al
  // menos cuerpo + DV (>= 2 dígitos después de normalizar). Mientras
  // el operador tipea, no se le molesta con el error.
  const nitNormalized = (nitValue ?? '').replace(/\D+/g, '');
  const nitValidation =
    nitNormalized.length >= 2 ? validarNitModulo11(nitValue ?? '') : null;
  const nitShowError =
    nitValidation !== null && !nitValidation.ok && nitNormalized.length >= 2;

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="empresa-datos-form"
      >
        <FormField
          control={form.control}
          name="nombre"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="nombre">
                {t('empresa.datos.nombre', 'Razón social')}
              </FormLabel>
              <FormControl>
                <Input
                  id="nombre"
                  data-testid="empresa-datos-nombre"
                  placeholder="Parkos S.A.S."
                  maxLength={255}
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
          name="nit"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="nit">
                {t('empresa.datos.nit', 'NIT')}
              </FormLabel>
              <FormControl>
                <Input
                  id="nit"
                  data-testid="empresa-datos-nit"
                  placeholder="900.123.456-7"
                  inputMode="numeric"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>
                {t(
                  'empresa.datos.nitHelp',
                  'Con o sin DV. Se valida con el algoritmo módulo 11 de la DIAN.',
                )}
              </FormDescription>
              {nitShowError ? (
                <p
                  role="alert"
                  data-testid="empresa-datos-nit-error"
                  className="text-sm font-medium text-destructive"
                >
                  {nitValidation?.message}
                </p>
              ) : null}
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="regimen"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="regimen">
                {t('empresa.datos.regimen', 'Régimen tributario')}
              </FormLabel>
              <FormControl>
                <select
                  id="regimen"
                  data-testid="empresa-datos-regimen"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  {...field}
                  value={field.value ?? 'comun'}
                >
                  <option value="comun">
                    {t('empresa.datos.regimenComun', 'Común')}
                  </option>
                  <option value="simplificado">
                    {t('empresa.datos.regimenSimplificado', 'Simplificado')}
                  </option>
                </select>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex items-center justify-end gap-2">
          <Button
            type="submit"
            disabled={isSubmitting || (nitShowError ?? false)}
            data-testid="empresa-datos-submit"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                {t('empresa.datos.submitting', 'Guardando…')}
              </>
            ) : (
              t('empresa.datos.submit', 'Guardar datos')
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function pickRegimen(raw: string | null | undefined): 'comun' | 'simplificado' {
  return raw === 'simplificado' ? 'simplificado' : 'comun';
}

export function EmpresaDatosTab(): JSX.Element {
  const { t } = useTranslation();
  const { empresa, isLoading, error, refresh } = useEmpresa();

  const form = useForm<EmpresaUpdateInput>({
    resolver: zodResolver(empresaUpdateSchema),
    defaultValues: {
      nombre: empresa?.nombre ?? '',
      nit: empresa?.nit ?? '',
      regimen: pickRegimen(empresa?.regimen),
    },
  });

  // Re-seed when the singleton resolves after first render.
  useEffect(() => {
    if (empresa === null) return;
    form.reset({
      nombre: empresa.nombre ?? '',
      nit: empresa.nit ?? '',
      regimen: pickRegimen(empresa.regimen),
    });
    // We intentionally depend only on `empresa` UUID — changing other
    // fields would cause an infinite reset loop while typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empresa?.uuid]);

  async function onSubmit(values: EmpresaUpdateInput): Promise<void> {
    if (empresa === null) return;
    await updateEmpresa(empresa.uuid, values);
    await refresh();
  }

  if (isLoading) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="empresa-datos-loading"
        className="text-sm text-muted-foreground"
      >
        {t('common.loading', 'Cargando…')}
      </p>
    );
  }

  if (error !== undefined) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="empresa-datos-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {error.message}
      </p>
    );
  }

  if (empresa === null) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="empresa-datos-empty"
        className="rounded-md border border-dashed bg-muted/40 px-3 py-4 text-sm text-muted-foreground"
      >
        {t(
          'empresa.datos.empty',
          'Aún no se sembró el singleton Empresa. Pedile al equipo de plataforma que corra el seed correspondiente.',
        )}
      </p>
    );
  }

  return (
    <EmpresaDatosFormShell
      empresa={empresa}
      form={form}
      onSubmit={(values) => {
        void onSubmit(values);
      }}
    />
  );
}

/**
 * Wrapper que mantiene al EmpresaDatosTab como componente de una
 * sola exportación (sigue el contrato del `<TabsContent value="datos">`)
 * pero separa el form del manejo de loading/error. No agrega
 * comportamiento nuevo — solo claridad de lectura.
 */
function EmpresaDatosFormShell({
  empresa,
  form,
  onSubmit,
}: {
  empresa: Empresa;
  form: ReturnType<typeof useForm<EmpresaUpdateInput>>;
  onSubmit: (values: EmpresaUpdateInput) => void;
}): JSX.Element {
  const { t } = useTranslation();
  const isSubmitting = form.formState.isSubmitting;

  return (
    <div className="space-y-4">
      <p
        className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
        data-testid="empresa-datos-editing"
      >
        {t(
          'empresa.datos.editingNotice',
          'Estás editando el singleton Empresa. El cambio publica una nueva versión bi-temporal; la anterior se cierra automáticamente.',
        )}
      </p>
      <EmpresaDatosForm
        form={form}
        onSubmit={onSubmit}
        isSubmitting={isSubmitting}
      />
      <p
        className="text-xs text-muted-foreground"
        data-testid="empresa-datos-uuid"
      >
        {t('empresa.datos.uuid', 'UUID: {{uuid}}', { uuid: empresa.uuid })}
      </p>
    </div>
  );
}
