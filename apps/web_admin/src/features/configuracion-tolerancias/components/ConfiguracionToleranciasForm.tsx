/**
 * `<ConfiguracionToleranciasForm />` — presentational form for create
 * + edit tolerancia.
 *
 * Toggle "Default global" vs "Override por sucursal":
 *   - Default global: ``uuid_sucursal=null``, persiste la fila con
 *     ``uuid_sucursal IS NULL`` (REQ-OP-12, SC-OP-06).
 *   - Override: BranchSelector pick; persiste el override per-branch.
 *
 * Two decimal inputs (``tolerancia_efectivo`` and
 * ``tolerancia_datafono``) — ``Numeric(18,4)`` server-side, coerced
 * to string in the schema. ``>= 0`` per the backend Pydantic.
 *
 * The form has its own `<form>` and the Cancel/Submit buttons; the
 * FormModal only owns the shell (title + description + error slot).
 */
import { useForm, type UseFormReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';

import {
  BranchSelector,
  type BranchOption,
} from '@/components/branch-selector/BranchSelector';
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

import {
  configuracionToleranciasCreateSchema,
  type ConfiguracionTolerancias,
  type ConfiguracionToleranciasCreateInput,
} from '../api/configuracionToleranciasSchema';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';

export interface ConfiguracionToleranciasFormProps {
  form: UseFormReturn<ConfiguracionToleranciasCreateInput>;
  onSubmit: (values: ConfiguracionToleranciasCreateInput) => void;
  isSubmitting: boolean;
  isUpdate?: boolean;
  initialTolerancia?: ConfiguracionTolerancias | null;
  onCancel: () => void;
}

export function ConfiguracionToleranciasForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
  initialTolerancia = null,
  onCancel,
}: ConfiguracionToleranciasFormProps) {
  const { t } = useTranslation();

  const { data: sucursalesResp } = useSWR(
    '/api/v1/empresa/sucursal?limit=200',
    async () => listSucursales({ limit: 200 }),
  );
  const sucursalOptions: BranchOption[] = (sucursalesResp ?? []).map((s) => ({
    uuid: s.uuid,
    nombre: s.nombre,
  }));

  // The toggle mirrors ``uuid_sucursal``: an empty string is the
  // sentinel for the "default global" branch. The form's onChange
  // translates the toggle to ``null`` (global) or a uuid (override).
  const isOverride = form.watch('uuid_sucursal') !== null;

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="configuracion-tolerancias-form"
      >
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="alcance"
              checked={!isOverride}
              onChange={() => form.setValue('uuid_sucursal', null)}
              data-testid="tolerancia-alcance-global"
            />
            {t('configuracionTolerancias.field.alcanceGlobal', 'Default global')}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="alcance"
              checked={isOverride}
              onChange={() => {
                if (sucursalOptions[0] !== undefined) {
                  form.setValue('uuid_sucursal', sucursalOptions[0].uuid);
                }
              }}
              data-testid="tolerancia-alcance-override"
            />
            {t('configuracionTolerancias.field.alcanceOverride', 'Override por sucursal')}
          </label>
        </div>

        {isOverride && (
          <FormField
            control={form.control}
            name="uuid_sucursal"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="uuid_sucursal">
                  {t('configuracionTolerancias.field.sucursal', 'Sucursal')}
                </FormLabel>
                <FormControl>
                  <BranchSelector
                    options={sucursalOptions}
                    value={field.value ?? null}
                    onChange={(uuid) => field.onChange(uuid)}
                  />
                </FormControl>
                <FormDescription>
                  {t(
                    'configuracionTolerancias.field.sucursalHelp',
                    'Este override reemplaza el default global solo para esta sucursal.',
                  )}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <FormField
          control={form.control}
          name="tolerancia_efectivo"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="tolerancia_efectivo">
                {t(
                  'configuracionTolerancias.field.toleranciaEfectivo',
                  'Tolerancia de efectivo (COP)',
                )}
              </FormLabel>
              <FormControl>
                <Input
                  id="tolerancia_efectivo"
                  data-testid="tolerancia-field-efectivo"
                  type="number"
                  step="0.0001"
                  min="0"
                  placeholder="100"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(e.target.value === '' ? null : e.target.value)
                  }
                />
              </FormControl>
              <FormDescription>
                {t(
                  'configuracionTolerancias.field.toleranciaEfectivoHelp',
                  'Diferencia máxima admisible en el conteo de efectivo. >= 0. Cuatro decimales.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="tolerancia_datafono"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="tolerancia_datafono">
                {t(
                  'configuracionTolerancias.field.toleranciaDatafono',
                  'Tolerancia de datáfono (COP)',
                )}
              </FormLabel>
              <FormControl>
                <Input
                  id="tolerancia_datafono"
                  data-testid="tolerancia-field-datafono"
                  type="number"
                  step="0.0001"
                  min="0"
                  placeholder="200"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(e.target.value === '' ? null : e.target.value)
                  }
                />
              </FormControl>
              <FormDescription>
                {t(
                  'configuracionTolerancias.field.toleranciaDatafonoHelp',
                  'Diferencia máxima admisible en el conteo de datáfono. >= 0. Cuatro decimales.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {initialTolerancia !== null && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="tolerancia-form-editing"
          >
            {t(
              'configuracionTolerancias.form.editingNotice',
              'Estás editando una configuración existente. El cambio publica una nueva versión; la anterior se cierra automáticamente.',
            )}
          </p>
        )}

        <div className="mt-2 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onCancel}
            disabled={isSubmitting}
            data-testid="tolerancia-cancel"
          >
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="tolerancia-submit"
          >
            {isSubmitting
              ? t('configuracionTolerancias.form.submitting', 'Guardando…')
              : isUpdate
                ? t('configuracionTolerancias.form.update', 'Actualizar')
                : t('configuracionTolerancias.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

export function ConfiguracionToleranciasFormHarness(
  props: Omit<ConfiguracionToleranciasFormProps, 'form'>,
): JSX.Element {
  const form = useForm<ConfiguracionToleranciasCreateInput>({
    resolver: zodResolver(configuracionToleranciasCreateSchema) as never,
    defaultValues: {
      uuid_sucursal: null,
      tolerancia_efectivo: null,
      tolerancia_datafono: null,
    },
  });
  return <ConfiguracionToleranciasForm {...props} form={form} />;
}
