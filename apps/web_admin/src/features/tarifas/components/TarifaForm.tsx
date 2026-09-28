/**
 * `<TarifaForm />` — presentational form for create + edit tarifa.
 *
 * DEC-F3.1-02 mirror: container/presentational split. The parent
 * (`<Tarifas />`) owns submit state, the SWR mutations, the error
 * mapping from typed error classes (`TarifaOverlapError`,
 * `TarifaSucursalInmutableError`), and the SWR revalidation.
 *
 * Renders a complete `<form>` so it can be slotted inside any
 * `FormModal` without producing nested forms. The submit button is
 * part of the form; the FormModal shell no longer renders its own.
 *
 * Fields:
 *   - `uuid_sucursal` (BranchSelector) — the tarifa belongs to one
 *     branch.
 *   - `uuid_tipo_vehiculo` (select, optional) — NULL for "any vehicle
 *     type". Filled with `useTiposVehiculo`'s HARDCODED_CATALOG fallback.
 *   - `uuid_tipo_tarifa` (select, optional) — same with `useTipoTarifa`.
 *   - `valor`, `valor_plena` — Numeric(18,4). `valor > 0`, `valor_plena
 *     >= 0`. Coerced to string for the wire format.
 *   - `vigente_desde` (datetime-local, optional) — empty = "starts
 *     now" (server default). A future date schedules a rate change.
 *     The form normalizes the naive browser string to `+00:00` before
 *     submitting.
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
  tarifaCreateSchema,
  type Tarifa,
  type TarifaCreateInput,
} from '../api/tarifaSchema';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import { useTiposVehiculo } from '@/features/tipos-vehiculo/hooks/useTiposVehiculo';
import { useTipoTarifa } from '@/features/tipo-tarifa/hooks/useTipoTarifa';

export interface TarifaFormProps {
  form: UseFormReturn<TarifaCreateInput>;
  onSubmit: (values: TarifaCreateInput) => void;
  isSubmitting: boolean;
  /** Update mode renders "Actualizar" + PUT semantics in the parent. */
  isUpdate?: boolean;
  /** Optional prefill from the row being edited (PUT). */
  initialTarifa?: Tarifa | null;
  /** Close the parent modal (e.g. cancel button). */
  onCancel: () => void;
}

export function TarifaForm({
  form,
  onSubmit,
  isSubmitting,
  isUpdate = false,
  initialTarifa = null,
  onCancel,
}: TarifaFormProps) {
  const { t } = useTranslation();

  const { data: sucursalesResp } = useSWR(
    '/api/v1/empresa/sucursal?limit=200',
    async () => listSucursales({ limit: 200 }),
  );
  const sucursalOptions: BranchOption[] = (sucursalesResp ?? []).map((s) => ({
    uuid: s.uuid,
    nombre: s.nombre,
  }));

  const { tipos: tiposVehiculo } = useTiposVehiculo();
  const { tipos: tiposTarifa } = useTipoTarifa();

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="tarifa-form"
      >
        <FormField
          control={form.control}
          name="uuid_sucursal"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="uuid_sucursal">
                {t('tarifas.field.sucursal', 'Sucursal')}
              </FormLabel>
              <FormControl>
                <BranchSelector
                  options={sucursalOptions}
                  value={field.value ?? null}
                  onChange={(uuid) => field.onChange(uuid)}
                />
              </FormControl>
              <FormDescription>
                {t('tarifas.field.sucursalHelp', 'La tarifa pertenece a esta sucursal.')}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="uuid_tipo_vehiculo"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="uuid_tipo_vehiculo">
                  {t('tarifas.field.tipoVehiculo', 'Tipo de vehículo (opcional)')}
                </FormLabel>
                <FormControl>
                  <select
                    id="uuid_tipo_vehiculo"
                    data-testid="tarifa-field-tipo-vehiculo"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                    className="block w-full rounded-md border bg-background px-3 py-2 text-sm"
                  >
                    <option value="">
                      {t('tarifas.field.tipoVehiculoAny', 'Cualquiera')}
                    </option>
                    {tiposVehiculo.map((t) => (
                      <option key={t.uuid} value={t.uuid}>
                        {t.tipo ?? t.uuid}
                      </option>
                    ))}
                  </select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="uuid_tipo_tarifa"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="uuid_tipo_tarifa">
                  {t('tarifas.field.tipoTarifa', 'Modalidad (opcional)')}
                </FormLabel>
                <FormControl>
                  <select
                    id="uuid_tipo_tarifa"
                    data-testid="tarifa-field-tipo-tarifa"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                    className="block w-full rounded-md border bg-background px-3 py-2 text-sm"
                  >
                    <option value="">
                      {t('tarifas.field.tipoTarifaAny', 'Cualquiera')}
                    </option>
                    {tiposTarifa.map((t) => (
                      <option key={t.uuid} value={t.uuid}>
                        {t.tipo ?? t.uuid}
                      </option>
                    ))}
                  </select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="valor"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="valor">
                  {t('tarifas.field.valor', 'Valor por hora')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="valor"
                    data-testid="tarifa-field-valor"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="1500"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorHelp', 'Debe ser > 0. Cuatro decimales.')}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="valor_plena"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="valor_plena">
                  {t('tarifas.field.valorPlena', 'Valor plena')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="valor_plena"
                    data-testid="tarifa-field-valor-plena"
                    type="number"
                    step="0.0001"
                    min="0"
                    placeholder="2000"
                    {...field}
                    value={field.value ?? ''}
                    onChange={(e) =>
                      field.onChange(e.target.value === '' ? null : e.target.value)
                    }
                  />
                </FormControl>
                <FormDescription>
                  {t('tarifas.field.valorPlenaHelp', 'Debe ser >= 0. Cuatro decimales.')}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="vigente_desde"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="vigente_desde">
                {t('tarifas.field.vigenteDesde', 'Vigente desde (opcional)')}
              </FormLabel>
              <FormControl>
                <Input
                  id="vigente_desde"
                  data-testid="tarifa-field-vigente-desde"
                  type="datetime-local"
                  {...field}
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === '') {
                      field.onChange(null);
                      return;
                    }
                    // The browser emits a naive ISO string ("2026-12-01T08:00").
                    // The Pydantic schema requires an offset; we tag the
                    // operator's intent as UTC so the server's bi-temporal
                    // predicate uses the right boundary.
                    field.onChange(`${raw}:00+00:00`);
                  }}
                />
              </FormControl>
              <FormDescription>
                {t(
                  'tarifas.field.vigenteDesdeHelp',
                  'Vacío = ahora. Una fecha futura programa un cambio de tarifa.',
                )}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {initialTarifa !== null && (
          <p
            className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
            data-testid="tarifa-form-editing"
          >
            {t(
              'tarifas.form.editingNotice',
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
            data-testid="tarifa-cancel"
          >
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="tarifa-submit"
          >
            {isSubmitting
              ? t('tarifas.form.submitting', 'Guardando…')
              : isUpdate
                ? t('tarifas.form.update', 'Actualizar')
                : t('tarifas.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

export function TarifaFormHarness(
  props: Omit<TarifaFormProps, 'form'>,
): JSX.Element {
  const form = useForm<TarifaCreateInput>({
    resolver: zodResolver(tarifaCreateSchema) as never,
    defaultValues: {
      uuid_sucursal: null,
      uuid_tipo_vehiculo: null,
      uuid_tipo_tarifa: null,
      valor: null,
      valor_plena: null,
      vigente_desde: null,
    },
  });
  return <TarifaForm {...props} form={form} />;
}
