/**
 * `<SucursalForm />` -- presentational form for creating a new branch
 * (IT-2.1, IT-2.7).
 *
 * DEC-F3.1-02 mirror: container/presentational split. The parent
 * (`<SucursalesList />`) owns submit state, validation errors, and the
 * HTTP call; this component only renders the RHF form fields.
 *
 * Accessibility (RNF-022 WCAG 2.1 AA, mirror of LoginForm):
 *   - All inputs have `<FormLabel htmlFor>` + `<FormControl id>` paired.
 *   - Zod validation errors surface as `<FormMessage role="alert">`.
 *   - Submit button shows `submitting` copy during submission; the
 *     parent passes that prop.
 *   - `aria-busy` on the form element while submitting.
 *
 * Required fields: `nombre`, `prefijo_nombre`. Everything else is
 * optional in the schema (matches backend `SucursalCreate`).
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

import { sucursalCreateSchema, type SucursalCreateInput } from '../api/sucursalSchema';

export interface SucursalFormProps {
  /** Caller's RHF form instance -- we re-render on every keystroke so the
   *  the caller can read `form.formState.errors` for the submit button
   *  disabled state. */
  form: UseFormReturn<SucursalCreateInput>;
  onSubmit: (values: SucursalCreateInput) => void;
  isSubmitting: boolean;
  /** Optional: when true the submit button label changes to "Actualizar"
   *  (reserved for a future update flow; IT-2 ships create-only). */
  isUpdate?: boolean;
}

export function SucursalForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
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

        <Button
          type="submit"
          className="w-full"
          disabled={isSubmitting}
          data-testid="sucursal-submit"
        >
          {isSubmitting
            ? t('sucursal.form.submitting')
            : isUpdate
              ? t('sucursal.form.update')
              : t('sucursal.form.create')}
        </Button>
      </form>
    </Form>
  );
}

/**
 * `<SucursalForm.Harness />` -- test convenience: a full Harness that
 * builds the RHF form with `zodResolver` so vitest unit tests can
 * exercise the field rendering and submit handler without
 * instantiating a parent container.
 */
export function SucursalFormHarness(props: Omit<SucursalFormProps, 'form'>) {
  const form = useForm<SucursalCreateInput>({
    resolver: zodResolver(sucursalCreateSchema),
    defaultValues: {
      nombre: '',
      prefijo_nombre: '',
      ciudad: '',
      telefono: '',
      direccion: '',
    },
  });
  return <SucursalForm {...props} form={form} />;
}
