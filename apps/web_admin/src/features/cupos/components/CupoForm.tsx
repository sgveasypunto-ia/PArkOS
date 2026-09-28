/**
 * `<CupoForm />` — presentational form for create + edit cupo.
 *
 * Fields:
 *   - `uuid_sucursal` (BranchSelector).
 *   - `cantidad` (integer, >= 0). The backend Pydantic constraint is
 *     ``z.number().int().min(0)``; we coerce to string in the schema
 *     to match the wire format the api layer expects, but the form
 *     input is a plain number.
 *   - `vigente_desde` (datetime-local, optional).
 *
 * The error message for the ``cantidad_bajo_ingresos_activos`` guard
 * lives in the page (Cupos.tsx) — it carries the operator-readable
 * detail with ``activos`` and ``solicitada`` to make the rejection
 * actionable. The form only knows about the lower-level Zod
 * validation.
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
  cupoCreateSchema,
  type Cupo,
  type CupoCreateInput,
} from '../api/cupoSchema';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';

export interface CupoFormProps {
  form: UseFormReturn<CupoCreateInput>;
  onSubmit: (values: CupoCreateInput) => void;
  isSubmitting: boolean;
  isUpdate?: boolean;
  initialCupo?: Cupo | null;
  onCancel: () => void;
}

export function CupoForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
  initialCupo = null,
  onCancel,
}: CupoFormProps) {
  const { t } = useTranslation();

  const { data: sucursalesResp } = useSWR(
    '/api/v1/empresa/sucursal?limit=200',
    async () => listSucursales({ limit: 200 }),
  );
  const sucursalOptions: BranchOption[] = (sucursalesResp ?? []).map((s) => ({
    uuid: s.uuid,
    nombre: s.nombre,
  }));

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="cupo-form"
      >
        <FormField
          control={form.control}
          name="uuid_sucursal"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="uuid_sucursal">
                {t('cupos.field.sucursal', 'Sucursal')}
              </FormLabel>
              <FormControl>
                <BranchSelector
                  options={sucursalOptions}
                  value={field.value ?? null}
                  onChange={(uuid) => field.onChange(uuid)}
                />
              </FormControl>
              <FormDescription>
                {t('cupos.field.sucursalHelp', 'El cupo pertenece a esta sucursal.')}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="cantidad"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="cantidad">
                {t('cupos.field.cantidad', 'Cantidad máxima de vehículos')}
              </FormLabel>
              <FormControl>
                <Input
                  id="cantidad"
                  data-testid="cupo-field-cantidad"
                  type="number"
                  step="1"
                  min="0"
                  placeholder="50"
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
                  'cupos.field.cantidadHelp',
                  'Debe ser >= 0. Una cantidad menor que los ingresos activos es rechazada.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="vigente_desde"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="vigente_desde">
                {t('cupos.field.vigenteDesde', 'Vigente desde (opcional)')}
              </FormLabel>
              <FormControl>
                <Input
                  id="vigente_desde"
                  data-testid="cupo-field-vigente-desde"
                  type="datetime-local"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === '') {
                      field.onChange(null);
                      return;
                    }
                    field.onChange(`${raw}:00+00:00`);
                  }}
                />
              </FormControl>
              <FormDescription>
                {t(
                  'cupos.field.vigenteDesdeHelp',
                  'Vacío = ahora. Una fecha futura programa un cambio de cupo.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {initialCupo !== null && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="cupo-form-editing"
          >
            {t(
              'cupos.form.editingNotice',
              'Estás editando una versión existente. El cambio publica una nueva versión; la anterior se cierra automáticamente.',
            )}
          </p>
        )}

        <div className="mt-2 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onCancel}
            disabled={isSubmitting}
            data-testid="cupo-cancel"
          >
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="cupo-submit"
          >
            {isSubmitting
              ? t('cupos.form.submitting', 'Guardando…')
              : isUpdate
                ? t('cupos.form.update', 'Actualizar')
                : t('cupos.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

export function CupoFormHarness(props: Omit<CupoFormProps, 'form'>): JSX.Element {
  const initial = props.initialCupo;
  const form = useForm<CupoCreateInput>({
    resolver: zodResolver(cupoCreateSchema) as never,
    defaultValues: {
      uuid_sucursal: initial?.uuid_sucursal ?? null,
      uuid_tipo_vehiculo: initial?.uuid_tipo_vehiculo ?? null,
      cantidad: initial?.cantidad ?? null,
      vigente_desde: initial?.vigente_desde ?? null,
    },
  });
  return <CupoForm {...props} form={form} />;
}
