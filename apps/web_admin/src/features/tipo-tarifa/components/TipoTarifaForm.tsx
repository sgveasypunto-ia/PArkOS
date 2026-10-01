/**
 * `<TipoTarifaForm />` — presentational form for create + edit tipo
 * tarifa. Single field ``tipo`` (lowercase per the canonical seed).
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
  tipoTarifaCreateSchema,
  type TipoTarifa,
  type TipoTarifaCreateInput,
} from '../api/tipoTarifaSchema';

export interface TipoTarifaFormProps {
  form: UseFormReturn<TipoTarifaCreateInput>;
  onSubmit: (values: TipoTarifaCreateInput) => void;
  isSubmitting: boolean;
  isUpdate?: boolean;
  initialTipoTarifa?: TipoTarifa | null;
  onCancel: () => void;
}

export function TipoTarifaForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
  initialTipoTarifa = null,
  onCancel,
}: TipoTarifaFormProps) {
  const { t } = useTranslation();

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="tipo-tarifa-form"
      >
        <FormField
          control={form.control}
          name="tipo"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="tipo">
                {t('tipoTarifa.field.tipo', 'Nombre de la modalidad')}
              </FormLabel>
              <FormControl>
                <Input
                  id="tipo"
                  data-testid="tipo-tarifa-field-tipo"
                  placeholder="hora"
                  maxLength={64}
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) => field.onChange(e.target.value)}
                />
              </FormControl>
              <FormDescription>
                {t(
                  'tipoTarifa.field.tipoHelp',
                  'El seed canónico usa lowercase (hora, fraccion, plena, nocturna). 1..64 caracteres.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {initialTipoTarifa !== null && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="tipo-tarifa-form-editing"
          >
            {t(
              'tipoTarifa.form.editingNotice',
              'Estás editando una modalidad existente. El cambio publica una nueva versión; la anterior se cierra automáticamente.',
            )}
          </p>
        )}

        <div className="mt-2 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onCancel}
            disabled={isSubmitting}
            data-testid="tipo-tarifa-cancel"
          >
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="tipo-tarifa-submit"
          >
            {isSubmitting
              ? t('tipoTarifa.form.submitting', 'Guardando…')
              : isUpdate
                ? t('tipoTarifa.form.update', 'Actualizar')
                : t('tipoTarifa.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

export function TipoTarifaFormHarness(
  props: Omit<TipoTarifaFormProps, 'form'>,
): JSX.Element {
  const form = useForm<TipoTarifaCreateInput>({
    resolver: zodResolver(tipoTarifaCreateSchema) as never,
    defaultValues: {
      tipo: '',
    },
  });
  return <TipoTarifaForm {...props} form={form} />;
}
