/**
 * `<VigenciaResumen />` — isolated block showing the coverage window
 * (inicio / fin) of the subscription being sold, before confirming payment.
 *
 * Kept self-contained (props in, markup out) so the end date can later be
 * made editable without touching the wizard.
 */
import { useTranslation } from 'react-i18next';
import { calcularFechaFinCobertura, formatFechaCO } from '../lib/vigencia';

export interface VigenciaResumenProps {
  /** `YYYY-MM-DD`. */
  fechaInicio: string;
  /** Plan duration in calendar days (backend `plan.duracion_dias`). */
  duracionDias: number;
}

export function VigenciaResumen({ fechaInicio, duracionDias }: VigenciaResumenProps) {
  const { t } = useTranslation();
  const fechaFin = calcularFechaFinCobertura(fechaInicio, duracionDias);
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
          {fechaFin === null ? '—' : formatFechaCO(fechaFin)}
        </dd>
      </dl>
    </div>
  );
}
