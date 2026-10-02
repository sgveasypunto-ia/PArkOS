/**
 * `<EstanciaPanel />` — stay-time (tiempo de estancia) stats for HU-F17.2
 * (BR1).
 *
 * Renders the per-day ``promedio``/``maximo``/``minimo`` stay-time rollup
 * the backend computes in-query (never persisted, BR1). Lives inside the
 * "Totales del período" section, right under `<ReporteOperacionalPanel />`
 * — same date range, same data source
 * (`GET /admin/reporteria/operacional`), one extra array (`tiempos_estancia`)
 * on the same response. A day with zero completed stays (every ingreso
 * still parked, or its only exit was voided) simply has no row — there is
 * nothing to average.
 */
import { useTranslation } from 'react-i18next';

import type { ReporteEstanciaItem } from '../api/reporteriaSchema';

export interface EstanciaPanelProps {
  items: ReporteEstanciaItem[];
  isLoading: boolean;
  error: Error | null | undefined;
}

function formatDuration(seconds: number): string {
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours <= 0) return `${minutes}min`;
  return `${hours}h ${minutes}min`;
}

export function EstanciaPanel({ items, isLoading, error }: EstanciaPanelProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="reporteria-estancia-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {error.message}
      </p>
    );
  }

  if (isLoading && items.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="reporteria-estancia-loading"
        className="text-sm text-muted-foreground"
      >
        {t('reporteria.estancia.loading', 'Cargando tiempos de estancia...')}
      </p>
    );
  }

  if (items.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="reporteria-estancia-empty"
        className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
      >
        {t(
          'reporteria.estancia.empty',
          'No hay estancias completas en el rango seleccionado.',
        )}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2" data-testid="reporteria-estancia-panel">
      <h3 className="text-sm font-semibold text-muted-foreground">
        {t('reporteria.estancia.title', 'Tiempos de estancia por día')}
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="reporteria-estancia-table">
          <caption className="sr-only">
            {t('reporteria.estancia.title', 'Tiempos de estancia por día')}
          </caption>
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th scope="col" className="p-1">
                {t('reporteria.estancia.fecha', 'Fecha')}
              </th>
              <th scope="col" className="p-1 text-right">
                {t('reporteria.estancia.muestras', 'Estancias')}
              </th>
              <th scope="col" className="p-1 text-right">
                {t('reporteria.estancia.promedio', 'Promedio')}
              </th>
              <th scope="col" className="p-1 text-right">
                {t('reporteria.estancia.maximo', 'Máximo')}
              </th>
              <th scope="col" className="p-1 text-right">
                {t('reporteria.estancia.minimo', 'Mínimo')}
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.fecha} data-testid={`reporteria-estancia-row-${item.fecha}`}>
                <td className="p-1 tabular-nums">{item.fecha}</td>
                <td className="p-1 text-right tabular-nums">{item.muestras}</td>
                <td className="p-1 text-right tabular-nums">
                  {formatDuration(item.promedio_segundos)}
                </td>
                <td className="p-1 text-right tabular-nums">
                  {formatDuration(item.maximo_segundos)}
                </td>
                <td className="p-1 text-right tabular-nums">
                  {formatDuration(item.minimo_segundos)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
