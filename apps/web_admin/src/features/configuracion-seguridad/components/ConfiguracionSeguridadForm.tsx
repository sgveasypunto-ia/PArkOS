/**
 * `<ConfiguracionSeguridadForm />` — presentational form for create
 * + edit seguridad. The submit goes through a confirmation step
 * (see ConfiguracionSeguridad.tsx) because the values are
 * operationally sensitive: changing ``minutos_bloqueo_login``
 * invalidates in-flight lockouts; changing ``max_intentos_login``
 * affects every operator across the tenant.
 *
 * Fields:
 *   - alcance: "default global" vs "override por sucursal" toggle
 *   - ``dias_expiracion_password`` (forward-compat; hidden by the
 *     page in the initial render but the form is ready to accept it
 *     when the password rotation flow lands).
 *   - ``max_intentos_login`` (1..20)
 *   - ``minutos_bloqueo_login`` (1..1440)
 */
import { useForm, type UseFormReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';

import { BranchSelector } from '@/components/branch-selector/BranchSelector';
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
  configuracionSeguridadCreateSchema,
  type ConfiguracionSeguridad,
  type ConfiguracionSeguridadCreateInput,
} from '../api/configuracionSeguridadSchema';
import { useSucursalOptions } from '@/features/sucursales/hooks/useSucursalesDirectorio';

export interface ConfiguracionSeguridadFormProps {
  form: UseFormReturn<ConfiguracionSeguridadCreateInput>;
  onSubmit: (values: ConfiguracionSeguridadCreateInput) => void;
  /** Called when the user clicks the submit button — the page uses it
   * to open a confirmation modal before actually submitting. */
  onRequestSubmit: () => void;
  isSubmitting: boolean;
  isUpdate?: boolean;
  initialSeguridad?: ConfiguracionSeguridad | null;
  onCancel: () => void;
}

export function ConfiguracionSeguridadForm({
  form,
  onRequestSubmit,
  isSubmitting,
  isUpdate = false,
  initialSeguridad = null,
  onCancel,
}: ConfiguracionSeguridadFormProps) {
  const { t } = useTranslation();

  const { options: sucursalOptions } = useSucursalOptions();

  const isOverride = form.watch('uuid_sucursal') !== null;

  return (
    <Form {...form}>
      <form
        onSubmit={(event) => {
          // Intercept the submit: trigger the page's confirmation
          // modal instead of letting the form submit directly. The
          // modal calls onSubmit(values) if the operator confirms.
          event.preventDefault();
          onRequestSubmit();
        }}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="configuracion-seguridad-form"
      >
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="alcance"
              checked={!isOverride}
              onChange={() => form.setValue('uuid_sucursal', null)}
              data-testid="seguridad-alcance-global"
            />
            {t('configuracionSeguridad.field.alcanceGlobal', 'Default global')}
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
              data-testid="seguridad-alcance-override"
            />
            {t('configuracionSeguridad.field.alcanceOverride', 'Override por sucursal')}
          </label>
        </div>

        {isOverride && (
          <FormField
            control={form.control}
            name="uuid_sucursal"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="uuid_sucursal">
                  {t('configuracionSeguridad.field.sucursal', 'Sucursal')}
                </FormLabel>
                <FormControl>
                  <BranchSelector
                    options={sucursalOptions}
                    value={field.value ?? null}
                    onChange={(uuid) => field.onChange(uuid)}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <FormField
          control={form.control}
          name="max_intentos_login"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="max_intentos_login">
                {t(
                  'configuracionSeguridad.field.maxIntentos',
                  'Máx. intentos de login',
                )}
              </FormLabel>
              <FormControl>
                <Input
                  id="max_intentos_login"
                  data-testid="seguridad-field-max-intentos"
                  type="number"
                  step="1"
                  min="1"
                  max="20"
                  placeholder="5"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(
                      e.target.value === '' ? null : Number(e.target.value),
                    )
                  }
                />
              </FormControl>
              <FormDescription>
                {t(
                  'configuracionSeguridad.field.maxIntentosHelp',
                  'Entre 1 y 20. El default canónico es 5.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="minutos_bloqueo_login"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="minutos_bloqueo_login">
                {t(
                  'configuracionSeguridad.field.minutosBloqueo',
                  'Minutos de bloqueo',
                )}
              </FormLabel>
              <FormControl>
                <Input
                  id="minutos_bloqueo_login"
                  data-testid="seguridad-field-minutos-bloqueo"
                  type="number"
                  step="1"
                  min="1"
                  max="1440"
                  placeholder="15"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) =>
                    field.onChange(
                      e.target.value === '' ? null : Number(e.target.value),
                    )
                  }
                />
              </FormControl>
              <FormDescription>
                {t(
                  'configuracionSeguridad.field.minutosBloqueoHelp',
                  'Entre 1 y 1440 (24h). El default canónico es 15.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {initialSeguridad !== null && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="seguridad-form-editing"
          >
            {t(
              'configuracionSeguridad.form.editingNotice',
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
            data-testid="seguridad-cancel"
          >
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="seguridad-submit"
          >
            {isSubmitting
              ? t('configuracionSeguridad.form.submitting', 'Guardando…')
              : isUpdate
                ? t('configuracionSeguridad.form.update', 'Actualizar')
                : t('configuracionSeguridad.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

export function ConfiguracionSeguridadFormHarness(
  props: Omit<ConfiguracionSeguridadFormProps, 'form'>,
): JSX.Element {
  const form = useForm<ConfiguracionSeguridadCreateInput>({
    resolver: zodResolver(configuracionSeguridadCreateSchema) as never,
    defaultValues: {
      uuid_sucursal: null,
      dias_expiracion_password: null,
      max_intentos_login: null,
      minutos_bloqueo_login: null,
    },
  });
  return <ConfiguracionSeguridadForm {...props} form={form} />;
}
