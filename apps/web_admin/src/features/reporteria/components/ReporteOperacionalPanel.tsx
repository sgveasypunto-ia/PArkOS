/**
 * `<ReporteOperacionalPanel />` — presentational totals panel for HU-F17.1.
 *
 * Renders the grand-total rollup returned by ``GET /admin/reporteria/operacional``
 * as a row of KPI cards. The per-day breakdown is intentionally hidden
 * behind the tabs already on the page — this panel is the "at a glance"
 * surface, not the detail. Same WCAG 2.1 AA conventions as the rest of
 * the feature (status/alert roles, sr-only label).
 *
 * Two money values are shown on purpose: ``monto_facturado_total`` (gross
 * invoiced) and ``monto_cobrado_total`` (net of voids). When the two
 * diverge materially it usually means invoices customers walked away
 * from — visible at a glance, no extra round-trip.
 */
import { useTranslation } from 'react-i18next';

import type { ReporteOperacionalResponse } from '../api/reporteriaSchema';

export interface ReporteOperacionalPanelProps {
  data: ReporteOperacionalResponse | undefined;
  isLoading: boolean;
  error: Error | null | undefined;
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: 'COP',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().slice(0, 10);
}

export function ReporteOperacionalPanel({
  data,
  isLoading,
  error,
}: ReporteOperacionalPanelProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="reporteria-operacional-error"
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
        data-testid="reporteria-operacional-loading"
        className="text-sm text-muted-foreground"
      >
        {t('reporteria.loading', 'Cargando...')}
      </p>
    );
  }

  if (!data) return null;

  const t0 = data.totales;
  return (
    <div
      className="flex flex-col gap-3"
      data-testid="reporteria-operacional-panel"
    >
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {t('reporteria.totales.rango', 'Rango: {{desde}} → {{hasta}}', {
          desde: formatDate(data.fecha_desde),
          hasta: formatDate(data.fecha_hasta),
        })}
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <KpiCard
          label={t('reporteria.totales.ingresos', 'Ingresos')}
          value={String(t0.ingresos_count)}
        />
        <KpiCard
          label={t('reporteria.totales.ingresosActivos', 'Ingresos activos')}
          value={String(t0.ingresos_activos_count)}
        />
        <KpiCard
          label={t('reporteria.totales.salidas', 'Salidas')}
          value={String(t0.salidas_count)}
        />
        <KpiCard
          label={t('reporteria.totales.facturas', 'Facturas')}
          value={String(t0.facturas_emitidas_count)}
        />
        <KpiCard
          label={t('reporteria.totales.facturado', 'Monto facturado')}
          value={formatMoney(t0.monto_facturado_total)}
        />
        <KpiCard
          label={t('reporteria.totales.cobrado', 'Monto cobrado')}
          value={formatMoney(t0.monto_cobrado_total)}
        />
      </div>
    </div>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <article
      className="rounded-lg border bg-card p-3 text-card-foreground shadow-sm"
      data-testid={`reporteria-kpi-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
    </article>
  );
}