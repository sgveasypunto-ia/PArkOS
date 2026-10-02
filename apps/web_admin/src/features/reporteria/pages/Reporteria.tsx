/**
 * `<Reporteria />` — operational report container (HU-F17.1/HU-F17.2,
 * web_admin).
 *
 * Top section: the "Totales del período" panel (KPIs from
 * ``GET /admin/reporteria/operacional``), the HU-F17.2 stay-time rollup
 * (``<EstanciaPanel />``, same response's ``tiempos_estancia`` field,
 * BR1), and a date-range picker (default = current month) with four
 * preset shortcuts (hoy, ayer, últimos 7 días, este mes). The picker
 * drives BOTH the operacional endpoint's SWR key AND the HU-F17.2
 * cross-branch heatmap below — branch switch and range switch
 * invalidate both caches.
 *
 * Bottom section: a Radix-Tabs drill-down with three tabs (Ingresos
 * | Salidas | Ocupación) showing the raw rows for the active branch.
 * The drill-down does NOT honour the date range: those endpoints
 * return the latest N entries, and the totals panel above already
 * covers the same range at aggregate level. Wiring the drill-down
 * to the range would require backend support for ``fecha_ingreso__gte``
 * and ``fecha_salida__gte`` on the existing endpoints, which is out of
 * scope here (known drift vs. plan.md, deliberately not retrofitted by
 * HU-F17.2 — see that HU's apply report). The Ocupación tab additionally
 * renders the HU-F17.2 heatmap (``GET /admin/reporteria/ocupacion``,
 * reusing ``<HeatmapOcupacion />`` from HU-F17.1) below the existing
 * per-tipo cupo/activos cards — cross-branch (every branch the admin can
 * see), unlike the rest of this page which is scoped to ``selected``.
 *
 * Branch context comes from ``useSucursal()``; this page lives inside
 * the branch-scoped route group (gated by ``<RequireSucursal>`` in
 * ``App.tsx``), so an admin without a selected branch never reaches
 * here — we render a placeholder rather than a confusing 400.
 *
 * RNF-022 (WCAG 2.1 AA): Tabs and triggers come from Radix so keyboard
 * navigation (Left/Right, Home/End) and ``aria-controls``/
 * ``aria-selected`` are correct; the per-tab containers carry
 * ``aria-labelledby`` for screen readers. The date range picker is a
 * separate ``<DateRangePicker />`` component with its own a11y surface
 * (labels, status, alert).
 */
import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';

import { parkosFetchRaw } from '@/lib/fetch';
import { useSucursal } from '@/lib/sucursal-context';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { HeatmapOcupacion } from '@/components/charts/HeatmapOcupacion';
import { exportToCsv } from '@/lib/export/csv';
import type { IngresoRead, SalidaListRead } from '../api/reporteriaSchema';

import {
  useReporteriaIngresos,
  useReporteriaSalidas,
  useReporteriaOcupacion,
  useReporteriaOperacional,
  useReporteriaOcupacionHeatmap,
} from '../hooks/useReporteria';
import { IngresosTable } from '../components/IngresosTable';
import { SalidasTable } from '../components/SalidasTable';
import { OcupacionPanel } from '../components/OcupacionPanel';
import { ReporteOperacionalPanel } from '../components/ReporteOperacionalPanel';
import { EstanciaPanel } from '../components/EstanciaPanel';
import {
  DateRangePicker,
  type DateRange,
} from '../components/DateRangePicker';
import { defaultRange } from '../components/dateRange';

interface BranchSummary {
  uuid: string;
  nombre: string | null;
}

const BRANCHES_PATH = '/api/v1/sucursales';

async function fetchJson<T>(input: string): Promise<T> {
  const res = await parkosFetchRaw(input, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`fetch ${input} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

export default function Reporteria() {
  const { t } = useTranslation();
  const { selected } = useSucursal();
  const [tab, setTab] = useState<'ingresos' | 'salidas' | 'ocupacion'>(
    'ingresos',
  );
  const [range, setRange] = useState<DateRange>(() => defaultRange());

  const branches = useSWR<{ items: BranchSummary[] }>(
    BRANCHES_PATH,
    () => fetchJson<{ items: BranchSummary[] }>(BRANCHES_PATH),
    { revalidateOnFocus: false },
  );
  const branchName =
    branches.data?.items.find((b) => b.uuid === selected)?.nombre ?? null;

  const ingresosQuery = selected ? { uuid_sucursal: selected, limit: 50 } : null;
  const salidasQuery = selected ? { uuid_sucursal: selected, limit: 50 } : null;

  const ingresos = useReporteriaIngresos(ingresosQuery);
  const salidas = useReporteriaSalidas(salidasQuery);
  const ocupacion = useReporteriaOcupacion(selected);

  const operacionalQuery = useMemo(() => {
    if (!selected) return null;
    return {
      uuid_sucursal: selected,
      fecha_desde: range.fecha_desde,
      fecha_hasta: range.fecha_hasta,
    };
  }, [selected, range]);
  const operacional = useReporteriaOperacional(operacionalQuery);

  // HU-F17.2 -- cross-branch heatmap, same date range as the KPI panel
  // above (one picker drives both). Cross-branch by design: every
  // branch the admin can see, not just the one currently selected.
  const heatmap = useReporteriaOcupacionHeatmap({
    desde: range.fecha_desde,
    hasta: range.fecha_hasta,
  });

  if (!selected) {
    return (
      <main
        className="min-h-screen bg-background p-6"
        data-testid="page-reporteria"
      >
        <p
          className="rounded-md border bg-muted/40 p-4 text-sm text-muted-foreground"
          data-testid="reporteria-no-branch"
        >
          {t(
            'reporteria.noBranch',
            'Seleccioná una sucursal para ver la reportería.',
          )}
        </p>
      </main>
    );
  }

  const rangeInvalid =
    range.fecha_desde > range.fecha_hasta ||
    !/^\d{4}-\d{2}-\d{2}$/.test(range.fecha_desde) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(range.fecha_hasta);

  return (
    <main
      className="min-h-screen bg-background p-6"
      data-testid="page-reporteria"
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <header className="border-b pb-4">
          <h1 className="text-3xl font-bold tracking-tight">
            {t('reporteria.title', 'Reportería operacional')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t(
              'reporteria.subtitle',
              'Ingresos, salidas y ocupación de la sucursal seleccionada.',
            )}
            {branchName ? (
              <span className="ml-2 font-medium" data-testid="reporteria-branch-name">
                ({branchName})
              </span>
            ) : null}
          </p>
        </header>

        <section
          aria-label={t('reporteria.totales.label', 'Totales del período')}
          className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-4"
          data-testid="reporteria-totales-section"
        >
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold">
              {t('reporteria.totales.title', 'Totales del período')}
            </h2>
          </div>
          <DateRangePicker
            value={range}
            onChange={setRange}
            disabled={operacional.isLoading && !operacional.data}
          />
          {!rangeInvalid ? (
            <>
              <ReporteOperacionalPanel
                data={operacional.data}
                isLoading={operacional.isLoading}
                error={operacional.error}
              />
              <EstanciaPanel
                items={operacional.data?.tiempos_estancia ?? []}
                isLoading={operacional.isLoading}
                error={operacional.error}
              />
            </>
          ) : null}
        </section>

        <Tabs
          value={tab}
          onValueChange={(value) =>
            setTab(value as 'ingresos' | 'salidas' | 'ocupacion')
          }
        >
          <TabsList aria-label={t('reporteria.tabsLabel', 'Sección de reporte')}>
            <TabsTrigger value="ingresos" data-testid="reporteria-tab-ingresos">
              {t('reporteria.tabs.ingresos', 'Ingresos')}
            </TabsTrigger>
            <TabsTrigger value="salidas" data-testid="reporteria-tab-salidas">
              {t('reporteria.tabs.salidas', 'Salidas')}
            </TabsTrigger>
            <TabsTrigger value="ocupacion" data-testid="reporteria-tab-ocupacion">
              {t('reporteria.tabs.ocupacion', 'Ocupación')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="ingresos">
            <div className="flex flex-col gap-2">
              <div className="flex justify-end">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    exportToCsv<IngresoRead>(
                      `ingresos-${selected}.csv`,
                      [
                        { header: 'Placa', accessor: (r) => r.placa ?? '' },
                        { header: 'Fecha de ingreso', accessor: (r) => r.fecha_ingreso?.toISOString() ?? '' },
                        { header: 'Consecutivo', accessor: (r) => r.consecutivo ?? '' },
                        { header: 'Observaciones', accessor: (r) => r.observaciones ?? '' },
                      ],
                      ingresos.data ?? [],
                    )
                  }
                  disabled={(ingresos.data ?? []).length === 0}
                  data-testid="reporteria-ingresos-export-csv"
                >
                  {t('reporteria.exportCsv', 'Exportar CSV')}
                </Button>
              </div>
              <IngresosTable
                items={ingresos.data ?? []}
                isLoading={ingresos.isLoading}
                error={ingresos.error}
                caption={t('reporteria.ingresos.caption', 'Ingresos de la sucursal')}
              />
            </div>
          </TabsContent>

          <TabsContent value="salidas">
            <div className="flex flex-col gap-2">
              <div className="flex justify-end">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    exportToCsv<SalidaListRead>(
                      `salidas-${selected}.csv`,
                      [
                        { header: 'Placa', accessor: (r) => r.placa ?? '' },
                        { header: 'Fecha de salida', accessor: (r) => r.fecha_salida?.toISOString() ?? '' },
                        { header: 'Consecutivo', accessor: (r) => r.consecutivo ?? '' },
                      ],
                      salidas.data ?? [],
                    )
                  }
                  disabled={(salidas.data ?? []).length === 0}
                  data-testid="reporteria-salidas-export-csv"
                >
                  {t('reporteria.exportCsv', 'Exportar CSV')}
                </Button>
              </div>
              <SalidasTable
                items={salidas.data ?? []}
                isLoading={salidas.isLoading}
                error={salidas.error}
                caption={t('reporteria.salidas.caption', 'Salidas de la sucursal')}
              />
            </div>
          </TabsContent>

          <TabsContent value="ocupacion">
            <div className="flex flex-col gap-6">
              <OcupacionPanel
                data={ocupacion.data}
                isLoading={ocupacion.isLoading}
                error={ocupacion.error}
              />
              <div className="rounded-lg border bg-card p-4" data-testid="reporteria-heatmap-section">
                {heatmap.error ? (
                  <p
                    role="alert"
                    aria-live="assertive"
                    data-testid="reporteria-heatmap-error"
                    className="text-sm text-destructive"
                  >
                    {heatmap.error.message}
                  </p>
                ) : (
                  <HeatmapOcupacion
                    data={heatmap.data?.data ?? []}
                    sucursales={heatmap.data?.sucursales ?? []}
                    title={t(
                      'reporteria.ocupacion.heatmapTitle',
                      'Actividad por hora ({{desde}} → {{hasta}})',
                      { desde: range.fecha_desde, hasta: range.fecha_hasta },
                    )}
                  />
                )}
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </main>
  );
}