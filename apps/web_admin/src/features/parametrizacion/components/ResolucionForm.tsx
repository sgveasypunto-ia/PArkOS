/**
 * `<ResolucionForm />` — creation form for HU-F15.3 "Resoluciones" (DIAN).
 *
 * Container/presentational split, mirrors
 * `features/tarifas/components/TarifaForm.tsx`'s shape (`<Form>` +
 * `FormField`/`FormItem`/`FormLabel`/`FormControl`/`FormMessage`,
 * `useForm` + `zodResolver` in a `*Harness` wrapper). One deliberate drift
 * from that precedent: `TarifaFormHarness` only builds the form and lets
 * the PAGE (`Tarifas.tsx`) own the SWR mutation + typed-error mapping; here
 * the Harness owns the `createResolucionFacturacion` call AND the 422
 * field-level error mapping itself. Reason: this form is CREATE-only (no
 * edit mode, unlike tarifas) and its only typed error
 * (`ResolucionFacturacionVigenciaError`) maps to exactly one field
 * (`fecha_fin_vigencia`) that only the Harness's `form` instance can set
 * via `form.setError` — splitting that across the container
 * (`ResolucionesDIAN.tsx`) would mean passing the `form` object out of the
 * harness, defeating the harness/presentational split's whole point.
 * `ResolucionesDIAN.tsx` only needs to know "did a resolución get created"
 * (`onCreated`) and "did the operator cancel" (`onCancel`).
 *
 * `uuid_sucursal` is NOT a visible field — it is pinned to the branch this
 * tab is scoped to (the harness's `uuidSucursal` prop, pinned again at
 * submit time as defense-in-depth, same rule `TarifaForm.tsx` documents
 * for its own `uuid_sucursal`). The other 4 fields (`numero_resolucion`,
 * `fecha_resolucion`, `fecha_inicio_vigencia`, `fecha_fin_vigencia`) are the
 * only user input this screen collects — `prefijo`, `rango_desde` and
 * `rango_hasta` are server-assigned (REQ-X3) and never appear in this form.
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
  ResolucionFacturacionVigenciaError,
} from '../api/resolucionFacturacionApi';
import {
  resolucionFacturacionCreateSchema,
  type ResolucionFacturacion,
  type ResolucionFacturacionCreateInput,
} from '../api/resolucionFacturacionSchema';

export interface ResolucionFormProps {
  form: UseFormReturn<ResolucionFacturacionCreateInput>;
  onSubmit: (values: ResolucionFacturacionCreateInput) => void | Promise<void>;
  isSubmitting: boolean;
  onCancel: () => void;
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
              : t('resoluciones.form.create', 'Crear')}
          </Button>
        </div>
      </form>
    </Form>
  );
}

export function ResolucionFormHarness({
  uuidSucursal,
  onCreated,
  onCancel,
}: ResolucionFormHarnessExtraProps): JSX.Element {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<ResolucionFacturacionCreateInput>({
    resolver: zodResolver(resolucionFacturacionCreateSchema) as never,
    defaultValues: {
      uuid_sucursal: uuidSucursal,
      numero_resolucion: '',
      fecha_resolucion: hoyComoFecha(),
      fecha_inicio_vigencia: hoyComoFecha(),
      fecha_fin_vigencia: '',
    },
  });

  async function handleSubmit(values: ResolucionFacturacionCreateInput): Promise<void> {
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      // Re-pin uuid_sucursal at submit time — defense-in-depth against any
      // caller-side drift, same rule `TarifaForm.tsx`'s module docstring
      // documents for its own `uuid_sucursal` field.
      const creada = await createResolucionFacturacion({ ...values, uuid_sucursal: uuidSucursal });
      onCreated(creada);
    } catch (err) {
      if (err instanceof ResolucionFacturacionVigenciaError) {
        form.setError('fecha_fin_vigencia', { type: 'server', message: err.message });
        return;
      }
      setSubmitError(
        err instanceof Error ? err.message : 'No se pudo crear la resolución.',
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
      submitError={submitError}
    />
  );
}
