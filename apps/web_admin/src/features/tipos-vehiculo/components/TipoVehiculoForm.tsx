/**
 * `<TipoVehiculoForm />` — presentational form for create + edit tipo
 * vehiculo. Single field ``tipo`` (lowercase per the canonical seed).
 *
 * Mismo patrón que TarifaForm / CupoForm: container/presentational
 * split, el caller (TiposVehiculo.tsx) provee RHF form + state.
 * El form incluye su propio `<form>` y los buttons Cancel/Submit
 * (FormModal solo aporta el shell: título + descripción + error slot).
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
  tipoVehiculoCreateSchema,
  type TipoVehiculo,
  type TipoVehiculoCreateInput,
} from '../api/tipoVehiculoSchema';

export interface TipoVehiculoFormProps {
  form: UseFormReturn<TipoVehiculoCreateInput>;
  onSubmit: (values: TipoVehiculoCreateInput) => void;
  isSubmitting: boolean;
  isUpdate?: boolean;
  initialTipoVehiculo?: TipoVehiculo | null;
  onCancel: () => void;
}

export function TipoVehiculoForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
  initialTipoVehiculo = null,
  onCancel,
}: TipoVehiculoFormProps) {
  const { t } = useTranslation();

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="tipo-vehiculo-form"
      >
        <FormField
          control={form.control}
          name="tipo"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="tipo">
                {t(
                  'tiposVehiculo.field.tipo',
                  'Nombre del tipo de vehículo',
                )}
              </FormLabel>
              <FormControl>
                <Input
                  id="tipo"
                  data-testid="tipo-vehiculo-field-tipo"
                  placeholder="camion"
                  maxLength={64}
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) => field.onChange(e.target.value)}
                />
              </FormControl>
              <FormDescription>
                {t(
                  'tiposVehiculo.field.tipoHelp',
                  'El seed canónico usa lowercase (carro, moto, bicicleta, patineta, otro). 1..64 caracteres.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {initialTipoVehiculo !== null && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="tipo-vehiculo-form-editing"
          >
            {t(
              'tiposVehiculo.form.editingNotice',
              'Estás editando un tipo existente. El cambio publica una nueva versión; la anterior se cierra automáticamente.',
            )}
          </p>
        )}

        <div className="mt-2 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onCancel}
            disabled={isSubmitting}
            data-testid="tipo-vehiculo-cancel"
          >
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="tipo-vehiculo-submit"
          >
            {isSubmitting
              ? t('tiposVehiculo.form.submitting', 'Guardando…')
              : isUpdate
                ? t('tiposVehiculo.form.update', 'Actualizar')
                : t('tiposVehiculo.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

export function TipoVehiculoFormHarness(
  props: Omit<TipoVehiculoFormProps, 'form'>,
): JSX.Element {
  const form = useForm<TipoVehiculoCreateInput>({
    resolver: zodResolver(tipoVehiculoCreateSchema) as never,
    defaultValues: {
      tipo: '',
    },
  });
  return <TipoVehiculoForm {...props} form={form} />;
}
