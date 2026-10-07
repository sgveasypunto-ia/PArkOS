/**
 * `<ResolucionForm />` — create / edit-numbering form for HU-F15.3
 * "Resoluciones" (DIAN).
 *
 * Container/presentational split, mirrors
 * `features/tarifas/components/TarifaForm.tsx`'s shape (`<Form>` +
 * `FormField`/`FormItem`/`FormLabel`/`FormControl`/`FormMessage`,
 * `useForm` + `zodResolver` in a `*Harness` wrapper). One deliberate drift
 * from that precedent: the Harness owns the `createResolucionFacturacion` /
 * `updateResolucionFacturacion` call AND the 422/409 field-level error
 * mapping itself, because those errors map to fields only the Harness's
 * `form` instance can `setError` on.
 *
 * Two modes, same fields:
 *   - create: empty form (dates default to today).
 *   - edit (`resolucion` prop): prefilled from a vigente row; submit calls
 *     `PUT` which is bi-temporal on the backend (closes the version, inserts
 *     a new one). This is how a resolucion created WITHOUT numbering gets its
 *     `prefijo` + `rango_desde`/`rango_hasta`, which electronic-invoice
 *     emission requires (`resolucion_sin_prefijo` otherwise).
 *
 * `uuid_sucursal` is NOT a visible field — it is pinned to the branch this
 * tab is scoped to (the harness's `uuidSucursal` prop, pinned again at
 * submit time as defense-in-depth).
 */
import { useState } from 'react';
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
  createResolucionFacturacion,
  ResolucionFacturacionNumeracionError,
  ResolucionFacturacionVigenciaError,
  updateResolucionFacturacion,
} from '../api/resolucionFacturacionApi';
import {
  PREFIJO_MAX_LENGTH,
  resolucionFacturacionCreateSchema,
  type ResolucionFacturacion,
  type ResolucionFacturacionCreateInput,
  type ResolucionFacturacionFormValues,
} from '../api/resolucionFacturacionSchema';

export interface ResolucionFormProps {
  form: UseFormReturn<
    ResolucionFacturacionFormValues,
    unknown,
    ResolucionFacturacionCreateInput
  >;
  onSubmit: (values: ResolucionFacturacionCreateInput) => void | Promise<void>;
  isSubmitting: boolean;
  onCancel: () => void;
  /** `true` when editing an existing resolucion (changes the submit label). */
  isEdit?: boolean;
  /** Non-field-level submit error (network/unexpected). The
   * `fecha_fin_vigencia` 422 guard is NOT routed here — it is set directly
   * on `form` (via `form.setError`) so it renders through that field's own
   * `<FormMessage />`, right where the operator needs to fix it. */
  submitError?: string | null;
}

/** Props only the harness consumes — never reaches the presentational
 *  form, same pattern as `TarifaFormHarnessExtraProps`. */
interface ResolucionFormHarnessExtraProps {
  /** Branch this tab is scoped to (`SucursalDetalle`'s route uuid, NOT the
   * topbar's active branch — see `ResolucionesDIAN.tsx`'s own docstring). */
  uuidSucursal: string;
  onCreated: (resolucion: ResolucionFacturacion) => void;
  onCancel: () => void;
  /** Vigente row to correct/complete. Absent = create mode. */
  resolucion?: ResolucionFacturacion;
}

function hoyComoFecha(): string {
  /** `YYYY-MM-DD` for today, LOCAL time (not `toISOString()`, which is UTC
   * and can roll the date near midnight) — same reasoning as
   * `useParametrizacionEfectiva.ts::formatFechaEfectiva`. */
  const now = new Date();
  const pad = (n: number): string => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function ResolucionForm({
  form,
  onSubmit,
  isSubmitting,
  onCancel,
  isEdit = false,
  submitError = null,
}: ResolucionFormProps) {
  const { t } = useTranslation();

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="resolucion-form"
      >
        {submitError && (
          <p
            role="alert"
            data-testid="resolucion-form-error"
            className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {submitError}
          </p>
        )}

        <FormField
          control={form.control}
          name="numero_resolucion"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="numero_resolucion">
                {t('resoluciones.field.numero', 'Número de resolución')}
              </FormLabel>
              <FormControl>
                <Input
                  id="numero_resolucion"
                  data-testid="resolucion-field-numero"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <FormField
            control={form.control}
            name="fecha_resolucion"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="fecha_resolucion">
                  {t('resoluciones.field.fechaResolucion', 'Fecha de la resolución')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="fecha_resolucion"
                    data-testid="resolucion-field-fecha-resolucion"
                    type="date"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="fecha_inicio_vigencia"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="fecha_inicio_vigencia">
                  {t('resoluciones.field.inicioVigencia', 'Vigente desde')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="fecha_inicio_vigencia"
                    data-testid="resolucion-field-fecha-inicio"
                    type="date"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="fecha_fin_vigencia"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="fecha_fin_vigencia">
                  {t('resoluciones.field.finVigencia', 'Vigente hasta')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="fecha_fin_vigencia"
                    data-testid="resolucion-field-fecha-fin"
                    type="date"
                    {...field}
                  />
                </FormControl>
                <FormDescription>
                  {t(
                    'resoluciones.field.finVigenciaHelp',
                    'Debe ser posterior a "Vigente desde".',
                  )}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <FormField
            control={form.control}
            name="prefijo"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="prefijo">
                  {t('resoluciones.field.prefijo', 'Prefijo')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="prefijo"
                    data-testid="resolucion-field-prefijo"
                    autoComplete="off"
                    maxLength={PREFIJO_MAX_LENGTH}
                    className="uppercase"
                    {...field}
                    onChange={(e) => field.onChange(e.target.value.toUpperCase())}
                  />
                </FormControl>
                <FormDescription>
                  {t(
                    'resoluciones.field.prefijoHelp',
                    'Letras y números, hasta 4 caracteres (ej. SETP).',
                  )}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="rango_desde"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="rango_desde">
                  {t('resoluciones.field.rangoDesde', 'Rango desde')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="rango_desde"
                    data-testid="resolucion-field-rango-desde"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    step={1}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="rango_hasta"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="rango_hasta">
                  {t('resoluciones.field.rangoHasta', 'Rango hasta')}
                </FormLabel>
                <FormControl>
                  <Input
                    id="rango_hasta"
                    data-testid="resolucion-field-rango-hasta"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    step={1}
                    {...field}
                  />
                </FormControl>
                <FormDescription>
                  {t(
                    'resoluciones.field.rangoHastaHelp',
                    'Debe ser mayor o igual a "Rango desde".',
                  )}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="mt-2 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onCancel}
            disabled={isSubmitting}
            data-testid="resolucion-cancel"
          >
            {t('common.cancel', 'Cancelar')}
          </Button>
          <Button type="submit" disabled={isSubmitting} data-testid="resolucion-submit">
            {isSubmitting
              ? t('resoluciones.form.submitting', 'Guardando…')
              : isEdit
                ? t('resoluciones.form.save', 'Guardar numeración')
                : t('resoluciones.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function formValuesFrom(
  uuidSucursal: string,
  resolucion: ResolucionFacturacion | undefined,
): ResolucionFacturacionFormValues {
  if (resolucion) {
    return {
      uuid_sucursal: uuidSucursal,
      numero_resolucion: resolucion.numero_resolucion ?? '',
      fecha_resolucion: resolucion.fecha_resolucion ?? hoyComoFecha(),
      fecha_inicio_vigencia: resolucion.fecha_inicio_vigencia ?? hoyComoFecha(),
      fecha_fin_vigencia: resolucion.fecha_fin_vigencia ?? '',
      prefijo: resolucion.prefijo ?? '',
      rango_desde: resolucion.rango_desde ?? '',
      rango_hasta: resolucion.rango_hasta ?? '',
    };
  }
  return {
    uuid_sucursal: uuidSucursal,
    numero_resolucion: '',
    fecha_resolucion: hoyComoFecha(),
    fecha_inicio_vigencia: hoyComoFecha(),
    fecha_fin_vigencia: '',
    prefijo: '',
    rango_desde: '',
    rango_hasta: '',
  };
}

export function ResolucionFormHarness({
  uuidSucursal,
  onCreated,
  onCancel,
  resolucion,
}: ResolucionFormHarnessExtraProps): JSX.Element {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<
    ResolucionFacturacionFormValues,
    unknown,
    ResolucionFacturacionCreateInput
  >({
    resolver: zodResolver(resolucionFacturacionCreateSchema) as never,
    defaultValues: formValuesFrom(uuidSucursal, resolucion),
  });

  async function handleSubmit(values: ResolucionFacturacionCreateInput): Promise<void> {
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      // Re-pin uuid_sucursal at submit time — defense-in-depth against any
      // caller-side drift, same rule `TarifaForm.tsx`'s module docstring
      // documents for its own `uuid_sucursal` field.
      const payload = { ...values, uuid_sucursal: uuidSucursal };
      const guardada = resolucion
        ? await updateResolucionFacturacion(resolucion.uuid, payload)
        : await createResolucionFacturacion(payload);
      onCreated(guardada);
    } catch (err) {
      if (err instanceof ResolucionFacturacionVigenciaError) {
        form.setError('fecha_fin_vigencia', { type: 'server', message: err.message });
        return;
      }
      if (err instanceof ResolucionFacturacionNumeracionError) {
        form.setError(err.campo, { type: 'server', message: err.message });
        return;
      }
      setSubmitError(
        err instanceof Error
          ? err.message
          : resolucion
            ? 'No se pudo guardar la resolución.'
            : 'No se pudo crear la resolución.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <ResolucionForm
      form={form}
      onSubmit={handleSubmit}
      isSubmitting={isSubmitting}
      onCancel={onCancel}
      isEdit={resolucion !== undefined}
      submitError={submitError}
    />
  );
}
