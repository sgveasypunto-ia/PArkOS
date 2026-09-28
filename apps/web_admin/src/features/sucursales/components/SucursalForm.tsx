/**
 * `<SucursalForm />` -- presentational form for creating + editing a
 * branch (IT-2.1, IT-2.7).
 *
 * DEC-F3.1-02 mirror: container/presentational split. The parent
 * (`<SeleccionarSucursal />`) owns submit state, validation errors, and
 * the HTTP call; this component only renders the RHF form fields.
 *
 * Accessibility (RNF-022 WCAG 2.1 AA, mirror of LoginForm):
 *   - All inputs have `<FormLabel htmlFor>` + `<FormControl id>` paired.
 *   - Zod validation errors surface as `<FormMessage role="alert">`.
 *   - Submit button shows `submitting` copy during submission; the
 *     parent passes that prop.
 *   - `aria-busy` on the form element while submitting.
 *
 * Required fields: `nombre`, `prefijo_nombre`. Everything else is
 * optional in the schema (matches backend `SucursalCreate` /
 * `SucursalUpdate`).
 */
import { useForm, type UseFormReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
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

import {
  sucursalCreateSchema,
  type Sucursal,
  type SucursalCreateInput,
} from '../api/sucursalSchema';

export interface SucursalFormProps {
  /** Caller's RHF form instance -- we re-render on every keystroke so the
   *  the caller can read `form.formState.errors` for the submit button
   *  disabled state. */
  form: UseFormReturn<SucursalCreateInput>;
  onSubmit: (values: SucursalCreateInput) => void;
  isSubmitting: boolean;
  /** When true the submit button label changes to "Actualizar" (PUT). */
  isUpdate?: boolean;
  /** Optional prefill for edit; null on create. */
  initialSucursal?: Sucursal | null;
  /** Close the parent modal (cancel button). */
  onCancel?: () => void;
}

export function SucursalForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
  initialSucursal = null,
  onCancel,
}: SucursalFormProps) {
  const { t } = useTranslation();
  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="sucursal-form"
      >
        <FormField
          control={form.control}
          name="nombre"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="nombre">{t('sucursal.field.nombre')}</FormLabel>
              <FormControl>
                <Input
                  id="nombre"
                  data-testid="sucursal-field-nombre"
                  placeholder="Sucursal Centro"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>{t('sucursal.field.nombreHelp')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="prefijo_nombre"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="prefijo_nombre">{t('sucursal.field.prefijo')}</FormLabel>
              <FormControl>
                <Input
                  id="prefijo_nombre"
                  data-testid="sucursal-field-prefijo"
                  placeholder="BOG-CEN"
                  maxLength={7}
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>{t('sucursal.field.prefijoHelp')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="ciudad"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="ciudad">{t('sucursal.field.ciudad')}</FormLabel>
                <FormControl>
                  <Input
                    id="ciudad"
                    data-testid="sucursal-field-ciudad"
                    placeholder="Bogota"
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
            name="telefono"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="telefono">{t('sucursal.field.telefono')}</FormLabel>
                <FormControl>
                  <Input
                    id="telefono"
                    data-testid="sucursal-field-telefono"
                    placeholder="+57 1 234 5678"
                    {...field}
                    value={field.value ?? ''}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="direccion"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="direccion">{t('sucursal.field.direccion')}</FormLabel>
              <FormControl>
                <Input
                  id="direccion"
                  data-testid="sucursal-field-direccion"
                  placeholder="Cra 7 # 32-16"
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
          name="horario"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="horario">{t('sucursal.field.horario')}</FormLabel>
              <FormControl>
                <Input
                  id="horario"
                  data-testid="sucursal-field-horario"
                  placeholder="Lun-Vie 8:00-18:00 / Sab 9:00-13:00"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>{t('sucursal.field.horarioHelp')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="uuid_tipo_sucursal"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="uuid_tipo_sucursal">
                  {t('sucursal.field.uuidTipoSucursal')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="uuid_tipo_sucursal"
                    data-testid="sucursal-field-uuid-tipo-sucursal"
                    placeholder="00000000-0000-0000-0000-000000000000"
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
            name="uuid_empresa"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="uuid_empresa">
                  {t('sucursal.field.uuidEmpresa')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="uuid_empresa"
                    data-testid="sucursal-field-uuid-empresa"
                    placeholder="00000000-0000-0000-0000-000000000000"
                    {...field}
                    value={field.value ?? ''}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        {initialSucursal !== null && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="sucursal-form-editing"
          >
            {t(
              'sucursal.form.editingNotice',
              'Estás editando una versión existente. El cambio publica una nueva versión; la anterior se cierra automáticamente.',
            )}
          </p>
        )}

        <div className="mt-2 flex items-center justify-end gap-2">
          {onCancel && (
            <Button
              type="button"
              variant="ghost"
              onClick={onCancel}
              disabled={isSubmitting}
              data-testid="sucursal-cancel"
            >
              {t('common.cancel', 'Cancelar')}
            </Button>
          )}
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="sucursal-submit"
          >
            {isSubmitting
              ? t('sucursal.form.submitting')
              : isUpdate
                ? t('sucursal.form.update')
                : t('sucursal.form.create')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

/**
 * `<SucursalFormHarness />` -- builds the RHF form with `zodResolver`
 * and seeds `defaultValues` from `initialSucursal` when present. Used
 * by the page container for both create (initialSucursal=null) and
 * edit (initialSucursal=<row>) flows. Mirror of CupoFormHarness /
 * TarifaFormHarness.
 */
export function SucursalFormHarness(
  props: Omit<SucursalFormProps, 'form'>,
): JSX.Element {
  const initial = props.initialSucursal ?? null;
  const form = useForm<SucursalCreateInput>({
    resolver: zodResolver(sucursalCreateSchema),
    defaultValues: {
      nombre: initial?.nombre ?? '',
      prefijo_nombre: initial?.prefijo_nombre ?? '',
      ciudad: initial?.ciudad ?? '',
      telefono: initial?.telefono ?? '',
      direccion: initial?.direccion ?? '',
      horario: initial?.horario ?? null,
      uuid_tipo_sucursal: initial?.uuid_tipo_sucursal ?? null,
      uuid_empresa: initial?.uuid_empresa ?? null,
    },
  });
  return <SucursalForm {...props} form={form} />;
}
