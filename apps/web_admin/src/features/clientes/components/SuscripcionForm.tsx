/**
 * `<SuscripcionForm />` — crear/editar una suscripción (HU-F20.2, RHF +
 * Zod). Mounted from `<ClienteSuscripciones />` inside a `<Dialog>`
 * (mirrors `NuevaVersionDialog.tsx`'s wiring style).
 *
 * Fields: plan (`uuid_tipo_subscripcion`), `fecha_inicio_cobertura`,
 * `fecha_vencimiento` (auto-suggested from the plan's `duracion_dias`,
 * still editable), `dias_alerta_pre_vencimiento` (1-90, CU-06 BR4), plus
 * a repeatable "Vehículos" section so the e2e flow "crear suscripción
 * con 2 vehículos" (plan.md HU-F20.2 "Pruebas") has somewhere to attach
 * them -- `subscripciones_cliente` itself carries no vehiculo FK; each
 * selected vehiculo becomes its own `POST /subscripcion-vehiculos` call
 * AFTER the subscripcion is created/updated (mirrors the two-step shape
 * `venta_suscripcion` already uses server-side: create the subscripcion
 * row first, then bulk-attach vehiculos).
 *
 * BR2 (PT-3, no proration): the "Monto del primer periodo" panel is
 * read-only and shows the FULL plan valor (the sale always charges the
 * whole plan, regardless of the start date) -- it is NEVER sent to the
 * backend as a charge; `SubscripcionesClienteCreate`/`Update` have no
 * such field.
 *
 * Error mapping: the 3 new 422 codes this HU introduces
 * (`placa_con_suscripcion_vigente`, `cantidad_vehiculos_excede_plan`,
 * `tipo_vehiculo_mixto_no_permitido`) are vehiculo-level errors (they can
 * only come back from the per-vehiculo `POST /subscripcion-vehiculos`
 * call), so they're surfaced inline on the specific vehiculo row that
 * failed -- the subscripcion itself was already saved successfully by
 * that point.
 */
import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useRef, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';
import { z } from 'zod';

import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { listCatalog } from '@/features/catalogos/api/catalogApi';
import { useSucursal } from '@/lib/sucursal-context';

import {
  createSubscripcionVehiculo,
  listVehiculos,
  type SubscripcionCliente,
} from '../api/clientesApi';

const suscripcionFormSchema = z.object({
  uuid_tipo_subscripcion: z.string().uuid(),
  fecha_inicio_cobertura: z.string().min(1),
  fecha_vencimiento: z.string().min(1),
  dias_alerta_pre_vencimiento: z.coerce.number().int().min(1).max(90),
  vehiculos: z.array(z.object({ uuid_vehiculo: z.string() })),
});

type SuscripcionFormValues = z.infer<typeof suscripcionFormSchema>;

export interface SuscripcionFormSubmitValues {
  uuid_tipo_subscripcion: string;
  fecha_inicio_cobertura: string;
  fecha_vencimiento: string;
  dias_alerta_pre_vencimiento: number;
}

export interface SuscripcionFormProps {
  /** `undefined` == crear; otherwise edita esta fila vigente. */
  subscripcion?: SubscripcionCliente;
  onSubmit: (values: SuscripcionFormSubmitValues) => Promise<SubscripcionCliente>;
  onDone: () => void;
  onCancel: () => void;
}

function addDaysIso(fechaIso: string, dias: number): string {
  const d = new Date(fechaIso);
  if (Number.isNaN(d.getTime())) return '';
  d.setUTCDate(d.getUTCDate() + dias);
  return d.toISOString().slice(0, 10);
}

export function SuscripcionForm({
  subscripcion,
  onSubmit,
  onDone,
  onCancel,
}: SuscripcionFormProps): JSX.Element {
  const { t } = useTranslation();
  const { selected: uuidSucursal } = useSucursal();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [vehiculoErrors, setVehiculoErrors] = useState<Record<number, string>>({});

  const { data: planes } = useSWR(
    '/catalogos/tipo-subscripciones',
    () => listCatalog('tipo-subscripciones'),
    { revalidateOnFocus: false },
  );
  const { data: vehiculosDisponibles } = useSWR(
    '/clientes/vehiculos/picker',
    async () => (await listVehiculos({ limit: 200 })).items,
    { revalidateOnFocus: false },
  );

  const form = useForm<SuscripcionFormValues>({
    resolver: zodResolver(suscripcionFormSchema),
    defaultValues: {
      uuid_tipo_subscripcion: subscripcion?.uuid_tipo_subscripcion ?? '',
      fecha_inicio_cobertura:
        subscripcion?.fecha_inicio_cobertura ?? new Date().toISOString().slice(0, 10),
      fecha_vencimiento: subscripcion?.fecha_vencimiento ?? '',
      dias_alerta_pre_vencimiento: subscripcion?.dias_alerta_pre_vencimiento ?? 7,
      vehiculos: [],
    },
  });

  const { fields, append, remove } = useFieldArray({ control: form.control, name: 'vehiculos' });

  const uuidTipoSubscripcion = form.watch('uuid_tipo_subscripcion');
  const fechaInicio = form.watch('fecha_inicio_cobertura');
  const planSeleccionado = (planes ?? []).find((p) => p.uuid === uuidTipoSubscripcion) ?? null;

  // CREATE mode only: suggest fecha_vencimiento from the plan's
  // duracion_dias, without clobbering a value the admin already edited
  // by hand away from the last auto-suggestion.
  const autoComputedRef = useRef<string>('');
  useEffect(() => {
    if (subscripcion) return; // edit mode: never auto-overwrite
    if (!planSeleccionado || !fechaInicio) return;
    const duracionDias = Number(planSeleccionado.duracion_dias ?? 0);
    if (!duracionDias) return;
    const computed = addDaysIso(fechaInicio, duracionDias);
    const current = form.getValues('fecha_vencimiento');
    if (current === '' || current === autoComputedRef.current) {
      form.setValue('fecha_vencimiento', computed, { shouldValidate: true });
      autoComputedRef.current = computed;
    }
  }, [subscripcion, planSeleccionado, fechaInicio, form]);

  const valorPlan =
    planSeleccionado && planSeleccionado.valor !== null && planSeleccionado.valor !== ''
      ? Number(planSeleccionado.valor)
      : Number.NaN;
  const montoReferencia = Number.isFinite(valorPlan) ? valorPlan : null;

  function mapVehiculoError(e: unknown): string {
    const message = e instanceof Error ? e.message : '';
    if (/placa_con_suscripcion_vigente/.test(message)) {
      return t(
        'suscripcionForm.errorPlacaVigente',
        'Ese vehículo ya tiene una suscripción vigente activa.',
      );
    }
    if (/cantidad_vehiculos_excede_plan/.test(message)) {
      return t(
        'suscripcionForm.errorCantidadExcede',
        'Se superó la cantidad máxima de vehículos permitida por el plan.',
      );
    }
    if (/tipo_vehiculo_mixto_no_permitido/.test(message)) {
      return t(
        'suscripcionForm.errorTipoMixto',
        'Este plan exige que todos los vehículos sean del mismo tipo.',
      );
    }
    if (/vehiculo_ya_inscrito/.test(message)) {
      return t(
        'suscripcionForm.errorYaInscrito',
        'Ese vehículo ya está inscrito en esta suscripción.',
      );
    }
    return t('suscripcionForm.errorVehiculoGenerico', 'No se pudo agregar el vehículo.');
  }

  function mapSubscripcionError(e: unknown): string {
    const message = e instanceof Error ? e.message : '';
    if (/numero_identificacion_duplicado/i.test(message)) {
      return t('suscripcionForm.errorDuplicado', 'Ya existe un registro con esos datos.');
    }
    return t('suscripcionForm.error', 'No se pudo guardar la suscripción. Reintentá.');
  }

  async function handleSubmit(values: SuscripcionFormValues): Promise<void> {
    setIsSubmitting(true);
    setSubmitError(null);
    setVehiculoErrors({});
    try {
      const saved = await onSubmit({
        uuid_tipo_subscripcion: values.uuid_tipo_subscripcion,
        fecha_inicio_cobertura: values.fecha_inicio_cobertura,
        fecha_vencimiento: values.fecha_vencimiento,
        dias_alerta_pre_vencimiento: values.dias_alerta_pre_vencimiento,
      });

      const errors: Record<number, string> = {};
      for (let i = 0; i < values.vehiculos.length; i += 1) {
        const uuidVehiculo = values.vehiculos[i]?.uuid_vehiculo;
        if (!uuidVehiculo) continue;
        try {
          await createSubscripcionVehiculo({
            uuid_subscripcion_cliente: saved.uuid,
            uuid_vehiculo: uuidVehiculo,
          });
        } catch (e) {
          errors[i] = mapVehiculoError(e);
        }
      }

      if (Object.keys(errors).length > 0) {
        setVehiculoErrors(errors);
        setSubmitError(
          t(
            'suscripcionForm.vehiculosParcialError',
            'La suscripción se guardó, pero algunos vehículos no se pudieron agregar (ver detalle abajo).',
          ),
        );
        return;
      }

      onDone();
    } catch (e) {
      setSubmitError(mapSubscripcionError(e));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(handleSubmit)}
        className="space-y-4"
        noValidate
        data-testid="suscripcion-form"
      >
        {submitError !== null && (
          <p
            role="alert"
            aria-live="assertive"
            data-testid="suscripcion-form-submit-error"
            className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {submitError}
          </p>
        )}

        {!uuidSucursal && !subscripcion && (
          <p
            role="alert"
            data-testid="suscripcion-form-sin-sucursal"
            className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {t(
              'suscripcionForm.sinSucursal',
              'Elegí una sucursal en el selector del topbar antes de crear una suscripción.',
            )}
          </p>
        )}

        <FormField
          control={form.control}
          name="uuid_tipo_subscripcion"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="suscripcion-plan">
                {t('suscripcionForm.plan', 'Plan')}
              </FormLabel>
              <FormControl>
                <select
                  id="suscripcion-plan"
                  data-testid="suscripcion-field-plan"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  {...field}
                >
                  <option value="">{t('suscripcionForm.planPlaceholder', 'Seleccioná un plan')}</option>
                  {(planes ?? []).map((p) => (
                    <option key={p.uuid} value={p.uuid}>
                      {String(p.tipo ?? p.uuid)}
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
          name="fecha_inicio_cobertura"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="suscripcion-fecha-inicio">
                {t('suscripcionForm.fechaInicio', 'Fecha de inicio de cobertura')}
              </FormLabel>
              <FormControl>
                <Input
                  id="suscripcion-fecha-inicio"
                  type="date"
                  data-testid="suscripcion-field-fecha-inicio"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="fecha_vencimiento"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="suscripcion-fecha-vencimiento">
                {t('suscripcionForm.fechaVencimiento', 'Fecha de vencimiento')}
              </FormLabel>
              <FormControl>
                <Input
                  id="suscripcion-fecha-vencimiento"
                  type="date"
                  data-testid="suscripcion-field-fecha-vencimiento"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="dias_alerta_pre_vencimiento"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="suscripcion-dias-alerta">
                {t('suscripcionForm.diasAlerta', 'Días de alerta antes del vencimiento')}
              </FormLabel>
              <FormControl>
                <Input
                  id="suscripcion-dias-alerta"
                  type="number"
                  min={1}
                  max={90}
                  data-testid="suscripcion-field-dias-alerta"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div
          className="rounded-md border bg-muted/30 px-3 py-2 text-sm"
          data-testid="suscripcion-monto-referencia"
        >
          <span className="font-medium">
            {t('suscripcionForm.montoReferencia', 'Monto del primer periodo (plan completo)')}
          </span>
          <span className="text-muted-foreground block">
            {montoReferencia !== null
              ? t('suscripcionForm.montoReferenciaValor', '{{monto}} (informativo, no es un cobro real)', {
                  monto: montoReferencia.toLocaleString('es-CO', {
                    style: 'currency',
                    currency: 'COP',
                    maximumFractionDigits: 0,
                  }),
                })
              : t('suscripcionForm.montoReferenciaSinDatos', 'Seleccioná un plan.')}
          </span>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('suscripcionForm.vehiculos', 'Vehículos')}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => append({ uuid_vehiculo: '' })}
              data-testid="suscripcion-agregar-vehiculo"
            >
              {t('suscripcionForm.agregarVehiculo', 'Agregar vehículo')}
            </Button>
          </div>
          {fields.length === 0 && (
            <p className="text-sm text-muted-foreground">
              {t('suscripcionForm.sinVehiculos', 'Sin vehículos agregados.')}
            </p>
          )}
          {fields.map((field, index) => (
            <div key={field.id} className="flex items-start gap-2" data-testid={`suscripcion-vehiculo-row-${index}`}>
              <FormField
                control={form.control}
                name={`vehiculos.${index}.uuid_vehiculo`}
                render={({ field: selectField }) => (
                  <FormItem className="flex-1">
                    <FormControl>
                      <select
                        data-testid={`suscripcion-vehiculo-select-${index}`}
                        className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        {...selectField}
                      >
                        <option value="">
                          {t('suscripcionForm.vehiculoPlaceholder', 'Seleccioná un vehículo')}
                        </option>
                        {(vehiculosDisponibles ?? []).map((v) => (
                          <option key={v.uuid} value={v.uuid}>
                            {v.placa ?? v.uuid}
                          </option>
                        ))}
                      </select>
                    </FormControl>
                    {vehiculoErrors[index] !== undefined && (
                      <p
                        role="alert"
                        data-testid={`suscripcion-vehiculo-error-${index}`}
                        className="text-destructive text-xs"
                      >
                        {vehiculoErrors[index]}
                      </p>
                    )}
                  </FormItem>
                )}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => remove(index)}
                data-testid={`suscripcion-quitar-vehiculo-${index}`}
              >
                {t('common.remove', 'Quitar')}
              </Button>
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting || (!uuidSucursal && !subscripcion)}
            data-testid="suscripcion-form-submit"
          >
            {isSubmitting ? t('common.saving', 'Guardando…') : t('common.save', 'Guardar')}
          </Button>
        </div>
      </form>
    </Form>
  );
}
