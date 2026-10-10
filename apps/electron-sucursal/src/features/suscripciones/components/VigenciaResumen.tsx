/**
 * `<VigenciaResumen />` — block showing the coverage window (inicio / fin)
 * of the subscription being sold, before confirming payment.
 *
 * The END date is editable but only to SHORTEN it: it must stay within
 * `[inicio, fin calculado por el plan]` (never beyond what was paid for; the
 * backend is the authority and answers 422 `fecha_fin_fuera_de_rango`). The
 * amount charged does NOT change (no proration). Without
 * `onFechaFinChange` the block is read-only.
 *
 * Controlled: the wizard owns `fechaFin` (`null`/`undefined` = plan end).
 */
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import {
  calcularFechaFinCobertura,
  formatFechaCO,
  validarFechaFin,
  type FechaFinError,
} from '../lib/vigencia';

export interface VigenciaResumenProps {
  /** `YYYY-MM-DD`. */
  fechaInicio: string;
  /** Plan duration in calendar days (backend `plan.duracion_dias`). */
  duracionDias: number;
  /** Operator-edited end (`YYYY-MM-DD`, or `''` while cleared). */
  fechaFin?: string | null;
  onFechaFinChange?: (fechaFin: string | null) => void;
  /** Message of a server-side rejection (422), shown next to the field. */
  errorServidor?: string | null;
  /** Increment to move the focus to the end-date input. */
  focusSignal?: number;
}

const DEFAULTS: Record<FechaFinError, string> = {
  vacia: 'Ingresa la fecha de fin de cobertura.',
  invalida: 'La fecha de fin no es válida.',
  antes_inicio: 'La fecha de fin no puede ser anterior al inicio ({{min}}).',
  despues_maximo:
    'La fecha de fin no puede superar el fin del plan ({{max}}). Para extender la vigencia usa otro plan o una renovación.',
};

export function VigenciaResumen({
  fechaInicio,
  duracionDias,
  fechaFin,
  onFechaFinChange,
  errorServidor,
  focusSignal,
}: VigenciaResumenProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const fechaFinPlan = calcularFechaFinCobertura(fechaInicio, duracionDias);
  const editable = onFechaFinChange !== undefined && fechaFinPlan !== null;

  const codigo: FechaFinError | null =
    editable && fechaFin != null ? validarFechaFin(fechaFin, fechaInicio, fechaFinPlan) : null;
  const mensaje =
    errorServidor ||
    (codigo
      ? t(`suscripciones:venta.paso6.vigencia.error.${codigo}`, {
          defaultValue: DEFAULTS[codigo],
          min: formatFechaCO(fechaInicio),
          max: fechaFinPlan === null ? '' : formatFechaCO(fechaFinPlan),
        })
      : null);

  // Never present an invalid/cleared date as the effective coverage end.
  const fechaFinEfectiva = fechaFin != null && fechaFin !== '' && !codigo ? fechaFin : fechaFinPlan;
  const valorInput = fechaFin ?? fechaFinPlan ?? '';

  useEffect(() => {
    if (focusSignal) inputRef.current?.focus();
  }, [focusSignal]);

  const ayudaId = 'venta-vigencia-fin-ayuda';
  const errorId = 'venta-vigencia-fin-error';
  return (
    <div
      className="rounded-md border border-border p-3 text-sm"
      data-testid="venta-vigencia"
    >
      <p className="font-medium">
        {t('suscripciones:venta.paso6.vigencia.titulo', { defaultValue: 'Vigencia de la suscripción' })}
      </p>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3">
        <dt className="text-muted-foreground">
          {t('suscripciones:venta.paso6.vigencia.inicio', { defaultValue: 'Inicio de cobertura' })}
        </dt>
        <dd data-testid="venta-vigencia-inicio">{formatFechaCO(fechaInicio)}</dd>
        <dt className="text-muted-foreground">
          {t('suscripciones:venta.paso6.vigencia.fin', { defaultValue: 'Fin de cobertura' })}
        </dt>
        <dd data-testid="venta-vigencia-fin">
          {fechaFinEfectiva === null ? '—' : formatFechaCO(fechaFinEfectiva)}
        </dd>
      </dl>
      {editable && (
        <div className="mt-3 space-y-1">
          <label htmlFor="venta-vigencia-fin-input" className="block text-muted-foreground">
            {t('suscripciones:venta.paso6.vigencia.ajustar', {
              defaultValue: 'Ajustar fecha de fin',
            })}
          </label>
          <div className="flex items-center gap-2">
            <Input
              ref={inputRef}
              id="venta-vigencia-fin-input"
              data-testid="venta-vigencia-fin-input"
              type="date"
              lang="es-CO"
              className="w-auto"
              min={fechaInicio}
              max={fechaFinPlan}
              value={valorInput}
              aria-invalid={mensaje ? true : undefined}
              aria-describedby={mensaje ? `${ayudaId} ${errorId}` : ayudaId}
              onChange={(e) => onFechaFinChange(e.target.value)}
            />
            {fechaFin != null && (
              <button
                type="button"
                className="text-sm underline underline-offset-2"
                data-testid="venta-vigencia-fin-restablecer"
                onClick={() => onFechaFinChange(null)}
              >
                {t('suscripciones:venta.paso6.vigencia.restablecer', {
                  defaultValue: 'Usar fin del plan',
                })}
              </button>
            )}
          </div>
          <p id={ayudaId} className="text-xs text-muted-foreground">
            {t('suscripciones:venta.paso6.vigencia.ayuda', {
              defaultValue:
                'Solo se puede acortar: entre {{min}} y {{max}}. El valor a cobrar no cambia.',
              min: formatFechaCO(fechaInicio),
              max: formatFechaCO(fechaFinPlan),
            })}
          </p>
          {mensaje && (
            <p
              id={errorId}
              data-testid="venta-vigencia-fin-error"
              className="text-sm text-destructive"
              role="alert"
            >
              {mensaje}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
