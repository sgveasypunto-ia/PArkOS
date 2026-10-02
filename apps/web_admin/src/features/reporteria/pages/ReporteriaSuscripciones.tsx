/**
 * `<ReporteriaSuscripciones />` — subscription reportería container
 * (HU-F17.4, web_admin).
 *
 * Two sections, both fed by the single
 * `GET /admin/reporteria/suscripciones/cohorte` endpoint (cross-branch,
 * every branch the admin can see — same reasoning the HU-F17.2 occupancy
 * heatmap and HU-F17.3 FE tab already document, so there is no branch
 * selector on this page):
 *
 *   - Cohortes de retención (`<SuscripcionesCohorte />`) — the BR1
 *     heatmap, date range bounds which cohort MONTHS are included
 *     (`fecha_inicio_cobertura`), defaults to the last 12 cohort months.
 *   - Próximas a vencer (`<SuscripcionesPorVencer />`) — top-20 alert
 *     list, independent of the date range (it always looks at "from
 *     today forward", same as its REQ-OPS-181 prior art).
 *
 * Registered at `/reporteria/suscripciones` — same precedent as
 * `/reporteria/financiera` (HU-F17.3): a route added to `App.tsx` with
 * no separate entry in `lib/admin-sections.ts` (that file drives the
 * Home page's permission-gated cards; the HU-F17.3 financial reportería
 * page does not have one either, confirmed by grep before adding this
 * page — no drift, following the established pattern as-is).
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useReporteriaSuscripcionesCohorte } from '../hooks/useReporteria';
import { SuscripcionesCohorte } from '../components/SuscripcionesCohorte';
import { SuscripcionesPorVencer } from '../components/SuscripcionesPorVencer';
import { DateRangePicker, type DateRange } from '../components/DateRangePicker';
import { todayISO } from '../components/dateRange';
import { Button } from '@/components/ui/button';
import { exportToCsv } from '@/lib/export/csv';
import type {
  CohorteRetencionCell,
  SuscripcionPorVencerItem,
} from '../api/reporteriaSchema';

/** Last 12 cohort months (UTC), ending today — BR1's default window. */
function defaultCohorteRange(): DateRange {
  const today = new Date();
  const hasta = todayISO();
  const desdeDate = new Date(
    Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - 11, 1),
  );
  const desde = desdeDate.toISOString().slice(0, 10);
  return { fecha_desde: desde, fecha_hasta: hasta };
}

export default function ReporteriaSuscripciones() {
  const { t } = useTranslation();
  const [range, setRange] = useState<DateRange>(() => defaultCohorteRange());

  const query = useMemo(
    () => ({ desde: range.fecha_desde, hasta: range.fecha_hasta }),
    [range],
  );
  const cohorte = useReporteriaSuscripcionesCohorte(query);

  const rangeInvalid =
    range.fecha_desde > range.fecha_hasta ||
    !/^\d{4}-\d{2}-\d{2}$/.test(range.fecha_desde) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(range.fecha_hasta);

  const handleExportCohortes = () => {
    const rows = cohorte.data?.data ?? [];
    exportToCsv<CohorteRetencionCell>(
      `cohortes-suscripciones-${range.fecha_desde}-a-${range.fecha_hasta}.csv`,
      [
        { header: 'Mes de cohorte', accessor: (r) => r.mes_cohorte },
        { header: 'Meses desde el alta', accessor: (r) => r.mes_offset },
        { header: 'Tamaño de la cohorte', accessor: (r) => r.cohorte_size },
        { header: 'Retenidos', accessor: (r) => r.retenidos },
        { header: '% de retención', accessor: (r) => r.porcentaje_retencion.toFixed(2) },
      ],
      rows,
    );
  };

  const handleExportPorVencer = () => {
    const rows = cohorte.data?.proximas_a_vencer ?? [];
    exportToCsv<SuscripcionPorVencerItem>(
      `suscripciones-por-vencer-${todayISO()}.csv`,
      [
        { header: 'Cliente', accessor: (r) => r.uuid_cliente ?? '' },
        { header: 'Sucursal', accessor: (r) => r.uuid_sucursal ?? '' },
        { header: 'Fecha de vencimiento', accessor: (r) => r.fecha_vencimiento },
        { header: 'Días restantes', accessor: (r) => r.dias_para_vencer },
      ],
      rows,
    );
  };

  return (
    <main
      className="min-h-screen bg-background p-6"
      data-testid="page-reporteria-suscripciones"
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <header className="border-b pb-4">
          <h1 className="text-3xl font-bold tracking-tight">
            {t('reporteriaSuscripciones.title', 'Reportería de suscripciones')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t(
              'reporteriaSuscripciones.subtitle',
              'Cohortes de retención y suscripciones próximas a vencer.',
            )}
          </p>
        </header>

        <section
          aria-label={t('reporteriaSuscripciones.cohorte.label', 'Cohortes de retención')}
          className="flex flex-col gap-3 rounded-lg border bg-card p-4"
          data-testid="reporteria-suscripciones-cohorte-section"
        >
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold">
              {t('reporteriaSuscripciones.cohorte.title', 'Cohortes de retención')}
            </h2>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleExportCohortes}
              disabled={!cohorte.data || cohorte.data.data.length === 0}
              data-testid="reporteria-suscripciones-cohorte-export-csv"
            >
              {t('reporteria.exportCsv', 'Exportar CSV')}
            </Button>
          </div>
          <DateRangePicker
            value={range}
            onChange={setRange}
            disabled={cohorte.isLoading && !cohorte.data}
          />
          {rangeInvalid ? null : cohorte.error ? (
            <p
              role="alert"
              aria-live="assertive"
              data-testid="reporteria-suscripciones-cohorte-error"
              className="text-sm text-destructive"
            >
              {cohorte.error.message}
            </p>
          ) : (
            <SuscripcionesCohorte
              cohortes={cohorte.data?.cohortes ?? []}
              data={cohorte.data?.data ?? []}
              maxOffsetMeses={cohorte.data?.max_offset_meses ?? 12}
              title={t(
                'reporteriaSuscripciones.cohorte.heatmapTitle',
                'Retención por cohorte de alta ({{desde}} → {{hasta}})',
                { desde: range.fecha_desde, hasta: range.fecha_hasta },
              )}
            />
          )}
        </section>

        <section
          aria-label={t('reporteriaSuscripciones.porVencer.label', 'Próximas a vencer')}
          className="flex flex-col gap-3 rounded-lg border bg-card p-4"
          data-testid="reporteria-suscripciones-por-vencer-section"
        >
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold">
              {t('reporteriaSuscripciones.porVencer.title', 'Próximas a vencer (top 20)')}
            </h2>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleExportPorVencer}
              disabled={!cohorte.data || cohorte.data.proximas_a_vencer.length === 0}
              data-testid="reporteria-suscripciones-por-vencer-export-csv"
            >
              {t('reporteria.exportCsv', 'Exportar CSV')}
            </Button>
          </div>
          <SuscripcionesPorVencer
            items={cohorte.data?.proximas_a_vencer ?? []}
            isLoading={cohorte.isLoading}
            error={cohorte.error}
            caption={t(
              'reporteriaSuscripciones.porVencer.caption',
              'Suscripciones próximas a vencer',
            )}
          />
        </section>
      </div>
    </main>
  );
}
