/**
 * `<CierreDiarioForm />` — presentational form for the F10.3 Cierre
 * Diario page (REQ-OPS-164 + AD-4).
 *
 * Receives the per-session `sesiones[]` array + pre-computed `totals`
 * from the parent page (the page aggregates from
 * `useArqueoResumenPorSesion().data.sesiones[]`; this form is
 * presentational only — it does NOT fetch the resumen itself).
 *
 * Aggregate-justification rule (REQ-OPS-164 scenario 2 + AD-4): when
 * `Σ|valor_efectivo_reportado - valor_efectivo_esperado| +
 * |valor_datafono_reportado - valor_datafono_esperado|| > 0`,
 * `justificacion` is REQUIRED (`min(3)` after trim) and the
 * Confirmar button stays disabled while the field is invalid.
 *
 * Mirrors the F10.2 `<CerrarTurnoForm>` pattern: react-hook-form +
 * Zod superRefine for the strict-mode branch + shadcn `<Form>`
 * primitives (aria-invalid + aria-describedby + `<FormMessage
 * role="alert">`) per WCAG 2.1 AA.
 *
 * NO useCierreDiario() legacy helper — this is the NEW forward
 * path per REQ-OPS-166.
 */
import { useId } from 'react';
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

import type { ArqueoResumenPorSesion } from '../hooks/useArqueoResumenPorSesion';
import { formatFechaHoraCorta } from '../lib/format';

/**
 * Public shape that the `<CierreDiario />` page passes to the form.
 * Matches the hook's typed `sesiones[]` and adds aggregate totals
 * computed by the page (Σ over closed sessions per REQ-OPS-163).
 */
export interface CierreDiarioFormProps {
  sesiones: ArqueoResumenPorSesion['sesiones'];
  totals: {
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    diferencia: number;
  };
  cierreDiaExists: boolean;
  isSubmitting: boolean;
  fecha: string;
  form: UseFormReturn<{
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion: string;
  }>;
  onSubmit: (values: {
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion?: string;
  }) => Promise<void>;
  onCancel: () => void;
}

/**
 * Returns today's local ISO date (YYYY-MM-DD) — the page passes this
 * as `fecha` (the form uses it as the `<Input type="date">` default).
 */
function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * Format a COP integer as es-CO locale string. Used for the per-
 * session table cells + aggregate footer.
 */
function formatCOP(value: number | null): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString('es-CO');
}

export function CierreDiarioForm(props: {
  sesiones: ArqueoResumenPorSesion['sesiones'];
  totals: {
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    diferencia: number;
  };
  cierreDiaExists: boolean;
  isSubmitting: boolean;
  fecha: string;
  form: UseFormReturn<{
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion: string;
  }>;
  onSubmit: (values: {
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion?: string;
  }) => Promise<void>;
  onCancel: () => void;
}): JSX.Element {
  // 'common' agregado (antes solo 'caja') para poder usar
  // `t('common:loading')` en el botón de submit — mismo namespace ya
  // cargado por AbrirTurnoForm/CerrarTurnoForm para el mismo estado.
  const { t } = useTranslation(['caja', 'common']);
  const formId = useId();

  // Aggregate-justification rule: when Σ|diferencia|>0, the
  // justificacion field is REQUIRED at the UI level (REQ-OPS-164 +
  // AD-4). The Confirmar button stays disabled while the field is
  // empty/invalid.
  const requiresJustificacion = props.totals.diferencia > 0;
  const watchedJustificacion = props.form.watch('justificacion') ?? '';
  const justificacionOk =
    !requiresJustificacion ||
    (typeof watchedJustificacion === 'string' &&
      watchedJustificacion.trim().length >= 3);
  const isDisabled =
    props.isSubmitting ||
    props.cierreDiaExists ||
    props.totals.valor_efectivo_reportado <= 0 ||
    !justificacionOk;

  return (
    <Form {...props.form}>
      <form
        id={formId}
        data-testid="cierre-diario-form"
        onSubmit={props.form.handleSubmit(props.onSubmit)}
        className="flex flex-col gap-2"
      >
        {/* ── Per-session summary table ─────────────────────────────── */}
        <div className="overflow-x-auto rounded border border-border bg-card">
          <table
            data-testid="cierre-diario-sesiones"
            className="w-full text-sm"
          >
            <caption className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">
              {t('caja:cierreDiario.tabla.caption', {
                defaultValue: 'Sesiones del día',
              })}
            </caption>
            <thead>
              <tr className="border-b border-border bg-muted">
                <th scope="col" className="px-3 py-2 text-left">
                  {t('caja:cierreDiario.tabla.cajero', {
                    defaultValue: 'Cajero',
                  })}
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  {t('caja:cierreDiario.tabla.base', {
                    defaultValue: 'Base',
                  })}
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  {t('caja:cierreDiario.tabla.reportado', {
                    defaultValue: 'Reportado',
                  })}
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  {t('caja:cierreDiario.tabla.diferencia', {
                    defaultValue: 'Diferencia',
                  })}
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  {t('caja:cierreDiario.tabla.estado', {
                    defaultValue: 'Estado',
                  })}
                </th>
              </tr>
            </thead>
            <tbody>
              {props.sesiones.map((s: ArqueoResumenPorSesion['sesiones'][number]) => {
                const diferencia =
                  s.valor_efectivo_reportado !== null &&
                  s.valor_efectivo_esperado !== null
                    ? s.valor_efectivo_reportado -
                      s.valor_efectivo_esperado +
                      (s.valor_datafono_reportado ?? 0) -
                      (s.valor_datafono_esperado ?? 0)
                    : null;
                return (
                  <tr
                    key={s.uuid_sesion ?? `${s.uuid_usuario}-${s.timestamp_apertura}`}
                    className="border-b border-border"
                    data-testid="cierre-diario-sesion-row"
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {(s.uuid_usuario ?? '').slice(0, 8) || '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {s.timestamp_apertura
                        ? formatFechaHoraCorta(s.timestamp_apertura)
                        : '—'}
                    </td>
                    {/* Ajuste 2026-09-25 (directiva del operador): el
                        valor Esperado NO se muestra en pantalla (conteo
                        a ciegas — el supervisor no debe ver cuánto
                        "debería dar" antes de reportar el conteo real),
                        pero SIGUE evaluándose: `diferencia` (abajo) y el
                        estado de descuadre ya lo usan internamente sin
                        exponerlo. */}
                    <td className="px-3 py-2 text-right">
                      {formatCOP(s.valor_efectivo_reportado)}
                    </td>
                    <td
                      // Consistente con la fila de totales (tfoot, abajo):
                      // una diferencia != 0 se resalta en `text-destructive`,
                      // no solo en negrita.
                      className={
                        diferencia !== null && diferencia !== 0
                          ? 'px-3 py-2 text-right font-semibold text-destructive'
                          : 'px-3 py-2 text-right'
                      }
                    >
                      {diferencia === null ? '—' : formatCOP(diferencia)}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        // F31.3 rediseño: reemplaza el emerald/amber
                        // hardcodeado por los tokens success/warning +
                        // sus -foreground (mismo par `bg-X text-X-foreground`
                        // ya usado por `<SyncStatusBadge />`), sin variantes
                        // `dark:` manuales — el token resuelve el tema.
                        className={
                          s.estado === 'cerrado'
                            ? 'inline-flex items-center rounded bg-success px-2 py-0.5 text-xs text-success-foreground'
                            : 'inline-flex items-center rounded bg-warning px-2 py-0.5 text-xs text-warning-foreground'
                        }
                      >
                        {s.estado ?? '—'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr
                data-testid="cierre-diario-totals"
                className="border-t-2 border-border bg-muted font-semibold"
              >
                <td colSpan={2} className="px-3 py-2">
                  Σ
                </td>
                <td className="px-3 py-2 text-right">
                  {formatCOP(props.totals.valor_efectivo_reportado)}
                </td>
                <td
                  className={
                    props.totals.diferencia > 0
                      ? 'px-3 py-2 text-right text-destructive'
                      : 'px-3 py-2 text-right'
                  }
                >
                  {formatCOP(props.totals.diferencia)}
                </td>
                <td className="px-3 py-2">—</td>
              </tr>
            </tfoot>
          </table>
        </div>

        {/* ── Fecha picker (REQ-OPS-164 + AD-6) ─────────────────────── */}
        <FormItem className="flex flex-col gap-1">
          <FormLabel htmlFor="cierre-diario-fecha">
            {t('caja:cierreDiario.fecha', { defaultValue: 'Fecha' })}
          </FormLabel>
          <FormControl>
            <Input
              id="cierre-diario-fecha"
              data-testid="cierre-diario-fecha"
              type="date"
              value={props.fecha}
              max={todayISO()}
              readOnly
              aria-describedby="cierre-diario-fecha-desc"
            />
          </FormControl>
          <FormDescription id="cierre-diario-fecha-desc">
            {t('caja:cierreDiario.fechaDesc', {
              defaultValue: 'Solo se permite el cierre del día actual.',
            })}
          </FormDescription>
        </FormItem>

        {/* ── Efectivo reportado ────────────────────────────────────── */}
        <FormField
          control={props.form.control}
          name="valor_efectivo_reportado"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t('caja:valorEfectivoReportado', {
                  defaultValue: 'Efectivo contado',
                })}
              </FormLabel>
              <FormControl>
                <Input
                  data-testid="cierre-diario-valor-efectivo"
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  aria-describedby="cierre-diario-valor-efectivo-msg"
                  value={
                    typeof field.value === 'number'
                      ? String(field.value)
                      : ''
                  }
                  onChange={(e) =>
                    field.onChange(
                      e.target.value === ''
                        ? 0
                        : Number.parseInt(e.target.value, 10) || 0,
                    )
                  }
                  onBlur={field.onBlur}
                  name={field.name}
                />
              </FormControl>
              <FormMessage
                id="cierre-diario-valor-efectivo-msg"
                data-testid="cierre-diario-valor-efectivo-error"
              />
            </FormItem>
          )}
        />

        {/* ── Datáfono reportado ────────────────────────────────────── */}
        <FormField
          control={props.form.control}
          name="valor_datafono_reportado"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t('caja:valorDatafonoReportado', {
                  defaultValue: 'Datáfono contado',
                })}
              </FormLabel>
              <FormControl>
                <Input
                  data-testid="cierre-diario-valor-datafono"
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  value={
                    typeof field.value === 'number'
                      ? String(field.value)
                      : ''
                  }
                  onChange={(e) =>
                    field.onChange(
                      e.target.value === ''
                        ? 0
                        : Number.parseInt(e.target.value, 10) || 0,
                    )
                  }
                  onBlur={field.onBlur}
                  name={field.name}
                />
              </FormControl>
              <FormMessage data-testid="cierre-diario-valor-datafono-error" />
            </FormItem>
          )}
        />

        {/* ── Justificación (REQUIRED when Σ|diferencia|>0) ─────────── */}
        {requiresJustificacion && (
          <FormField
            control={props.form.control}
            name="justificacion"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  {t('caja:justificacion', {
                    defaultValue: 'Justificación',
                  })}
                </FormLabel>
                <FormControl>
                  <Input
                    data-testid="cierre-diario-justificacion"
                    type="text"
                    aria-required="true"
                    aria-describedby="cierre-diario-justificacion-msg"
                    value={field.value ?? ''}
                    onChange={field.onChange}
                    onBlur={field.onBlur}
                    name={field.name}
                  />
                </FormControl>
                <FormDescription>
                  {t('caja:justificacionRequeridaStrict', {
                    defaultValue:
                      'Requerida (mín. 3 caracteres) cuando hay diferencia.',
                  })}
                </FormDescription>
                <FormMessage
                  id="cierre-diario-justificacion-msg"
                  data-testid="cierre-diario-justificacion-error"
                />
              </FormItem>
            )}
          />
        )}

        {/* ── Buttons ──────────────────────────────────────────────── */}
        <div className="flex flex-wrap gap-2 pt-2">
          <Button
            type="submit"
            data-testid="cierre-diario-confirmar"
            disabled={isDisabled}
            aria-disabled={isDisabled}
          >
            {/* Estado loading visual — `isSubmitting` ya existía en la
                lógica (usado en `isDisabled`) pero el botón nunca
                cambiaba de texto, a diferencia de AbrirTurnoForm /
                CerrarTurnoForm / ArqueoParcial (mismo patrón "Cargando…"
                durante el submit). */}
            {props.isSubmitting
              ? t('common:loading', { defaultValue: 'Cargando…' })
              : t('caja:cierreDiario.confirmar', {
                  defaultValue: 'Confirmar cierre diario',
                })}
          </Button>
          <Button
            type="button"
            variant="ghost"
            data-testid="cierre-diario-cancelar"
            onClick={props.onCancel}
          >
            {t('caja:cierreDiario.cancelar', { defaultValue: 'Cancelar' })}
          </Button>
        </div>
      </form>
    </Form>
  );
}