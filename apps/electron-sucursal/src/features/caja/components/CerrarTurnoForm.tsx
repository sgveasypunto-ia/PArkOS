/**
 * `<CerrarTurnoForm />` — presentational puro (F3.3 — T3, DEC-F3.3-06 verbatim).
 *
 * Recibe props `{ form, onSubmit, isSubmitting, error, sesion, onCancel }`
 * (DEC-F3.1-02 verbatim + DEC-F3.3-06 placeholder arqueo). Lee `sesion`
 * via props — NO consume `useSesionActiva` (presentational puro).
 *
 * Renderiza:
 *   - Resumen del turno arriba del form (uuid, timestamp apertura vía
 *     `formatTiempoTranscurrido`, valores iniciales vía `formatCOP`,
 *     observaciones si truthy).
 *   - Form con 3 campos decimales (valor_final_efectivo/datafono +
 *     observaciones_cierre opcional).
 *   - Botones "Confirmar cierre" + "Cancelar" (`variant="ghost"`).
 *
 * Accesibilidad (RNF-022 WCAG 2.1 AA — REQ-OPS-122 + REQ-OPS-124):
 *   - `<Form {...form}>` wrap con FormProvider (form.tsx:33).
 *   - `<FormLabel htmlFor>` + `<FormControl id>` via `useFormField()`.
 *   - `<Input type="number" inputMode="decimal" step="0.01">` (DEC-F3.3-02).
 *   - `<FormMessage role="alert">` para 404 `sesion_not_found` UX.
 *   - Botones `aria-disabled={isSubmitting}` + `data-testid` para tests.
 *
 * DEC-F3.3-06 placeholder: F3.3 NO implementa arqueo completo (tolerancia +
 * justificación + alerta `descuadre_critico`) — Fase 10 HU-F10.x entrega
 * el flujo completo con `POST /caja/arqueo` + `tipo_arqueo='cierre_turno'`.
 */
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import type { CerrarTurnoInput } from '../api/schemas/turnoSchema';
import type { SesionRead } from '../api/sesionActivaApi';
import { formatCOP, formatTiempoTranscurrido } from '../lib/format';

/**
 * Estado de error que `<CerrarTurno>` pasa a `<CerrarTurnoForm />`.
 *  - sesion_already_closed → <FormMessage role="alert">{t('sesionYaCerrada')}</FormMessage>
 *  - network              → <FormMessage role="alert">{t('errors:serverError')}</FormMessage>
 */
export type CerrarTurnoErrorState =
  | { kind: 'sesion_already_closed' }
  | { kind: 'network' }
  | null;

export interface CerrarTurnoFormProps {
  form: UseFormReturn<CerrarTurnoInput>;
  onSubmit: (data: CerrarTurnoInput) => Promise<void>;
  isSubmitting: boolean;
  error: CerrarTurnoErrorState;
  sesion: SesionRead;
  onCancel: () => void;
}

export function CerrarTurnoForm({
  form,
  onSubmit,
  isSubmitting,
  error,
  sesion,
  onCancel,
}: CerrarTurnoFormProps): JSX.Element {
  const { t } = useTranslation(['caja', 'common']);

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        noValidate
        aria-labelledby="cerrar-turno-title"
        data-testid="cerrar-turno-form"
      >
        <h1 id="cerrar-turno-title">{t('caja:cerrarTurno')}</h1>

        {/* Resumen del turno (placeholder F10.x completa con arqueo). */}
        <section data-testid="cerrar-turno-resumen" aria-label="Resumen del turno">
          <p>
            <strong>UUID:</strong> {sesion.uuid}
          </p>
          <p>
            <strong>{t('caja:valorInicialEfectivo')}:</strong>{' '}
            {formatCOP(sesion.valor_inicial_efectivo)}
          </p>
          <p>
            <strong>{t('caja:valorInicialDatafono')}:</strong>{' '}
            {formatCOP(sesion.valor_inicial_datafono)}
          </p>
          <p data-testid="cerrar-turno-apertura">
            <strong>Apertura:</strong>{' '}
            {formatTiempoTranscurrido(sesion.timestamp_apertura)}
          </p>
          {sesion.observaciones !== null &&
            sesion.observaciones !== undefined &&
            sesion.observaciones !== '' && (
              <p>
                <strong>{t('caja:observaciones')}:</strong> {sesion.observaciones}
              </p>
            )}
        </section>

        <FormField
          control={form.control}
          name="valor_final_efectivo"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('caja:valorFinalEfectivo')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  data-testid="cerrar-turno-valor-efectivo"
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    field.onChange(raw === '' ? 0 : Number(raw));
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="valor_final_datafono"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('caja:valorFinalDatafono')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  data-testid="cerrar-turno-valor-datafono"
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    field.onChange(raw === '' ? 0 : Number(raw));
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="observaciones_cierre"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('caja:observaciones')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="text"
                  data-testid="cerrar-turno-observaciones"
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>Opcional</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {error?.kind === 'sesion_already_closed' && (
          <FormMessage role="alert" data-testid="cerrar-turno-error-sesion-ya-cerrada">
            {t('caja:sesionYaCerrada')}
          </FormMessage>
        )}

        <Button
          type="submit"
          disabled={isSubmitting}
          aria-disabled={isSubmitting}
          data-testid="cerrar-turno-confirmar"
        >
          {isSubmitting ? t('common:loading') : t('caja:confirmarCierre')}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={isSubmitting}
          aria-disabled={isSubmitting}
          data-testid="cerrar-turno-cancelar"
        >
          {t('common:cancel')}
        </Button>
      </form>
    </Form>
  );
}