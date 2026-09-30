/**
 * `<OcupacionPanel />` — presentational breakdown for HU-F17.1.
 *
 * Renders one card per vehicle type with current `activos` vs
 * `cupo_maximo` and the derived `disponible` (the backend computes the
 * subtraction — we just display it; an XSS-style negative value means
 * the branch has no `cantidad_vehiculos_sucursal` row for that type
 * yet, and we surface "N/A" so the admin knows it's a configuration
 * gap rather than a real over-capacity state).
 *
 * Per-type occupancy breakdown is what an admin uses to spot a
 * branch that's over-capacity in one vehicle class and under-utilised
 * in another. The flat layout (cards in a grid) reads faster at a
 * glance than a single table when the number of tipos is small
 * (typically 2-4: Auto, Moto, Bicicleta, Patineta).
 */
import { useTranslation } from 'react-i18next';

import type { OcupacionResponse } from '../api/reporteriaSchema';

export interface OcupacionPanelProps {
  data: OcupacionResponse | undefined;
  isLoading: boolean;
  error: Error | null | undefined;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toISOString().replace('T', ' ').slice(0, 19);
}

export function OcupacionPanel({ data, isLoading, error }: OcupacionPanelProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="reporteria-ocupacion-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {error.message}
      </p>
    );
  }

  if (isLoading && !data) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="reporteria-ocupacion-loading"
        className="text-sm text-muted-foreground"
      >
        {t('reporteria.loading', 'Cargando ocupación...')}
      </p>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="reporteria-ocupacion-empty"
        className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
      >
        {t(
          'reporteria.ocupacion.empty',
          'No hay tipos de vehículo configurados para esta sucursal.',
        )}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3" data-testid="reporteria-ocupacion-panel">
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {t('reporteria.ocupacion.generadoEn', 'Generado en {{ts}}', {
          ts: formatTimestamp(data.generado_en),
        })}
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {data.items.map((item) => {
          const disponibleLabel =
            item.disponible < 0
              ? t('reporteria.ocupacion.na', 'N/A')
              : item.disponible;
          const disponibleState =
            item.disponible < 0
              ? 'border-destructive/40 bg-destructive/10 text-destructive'
              : item.disponible === 0
                ? 'border-amber-400/40 bg-amber-50 text-amber-900'
                : 'border-emerald-400/40 bg-emerald-50 text-emerald-900';
          return (
            <article
              key={item.uuid_tipo_vehiculo}
              className={`rounded-lg border p-4 ${disponibleState}`}
              data-testid={`reporteria-ocupacion-card-${item.tipo}`}
            >
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {item.tipo}
              </p>
              <p className="mt-2 text-3xl font-semibold tabular-nums">
                {disponibleLabel}
              </p>
              <p className="mt-2 text-xs">
                {t('reporteria.ocupacion.activosDe', '{{activos}} de {{cupo}} activos', {
                  activos: item.activos,
                  cupo: item.cupo_maximo,
                })}
              </p>
            </article>
          );
        })}
      </div>
    </div>
  );
}