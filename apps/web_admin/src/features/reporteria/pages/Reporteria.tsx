/**
 * `<Reporteria />` — operational report container (HU-F17.1, web_admin).
 *
 * Top section: the "Totales del período" panel (KPIs from
 * ``GET /admin/reporteria/operacional``) with a date-range picker
 * (default = current month) and four preset shortcuts (hoy, ayer,
 * últimos 7 días, este mes). The picker drives the operacional
 * endpoint's SWR key — branch switch and range switch both invalidate
 * the cache.
 *
 * Bottom section: a Radix-Tabs drill-down with three tabs (Ingresos
 * | Salidas | Ocupación) showing the raw rows for the active branch.
 * The drill-down does NOT honour the date range: those endpoints
 * return the latest N entries, and the totals panel above already
 * covers the same range at aggregate level. Wiring the drill-down
 * to the range would require backend support for ``fecha_ingreso__gte``
 * and ``fecha_salida__gte`` on the existing endpoints, which is out of
 * scope for this PR.
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

import {
  useReporteriaIngresos,
  useReporteriaSalidas,
  useReporteriaOcupacion,
  useReporteriaOperacional,
} from '../hooks/useReporteria';
import { IngresosTable } from '../components/IngresosTable';
import { SalidasTable } from '../components/SalidasTable';
import { OcupacionPanel } from '../components/OcupacionPanel';
import { ReporteOperacionalPanel } from '../components/ReporteOperacionalPanel';
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
            <ReporteOperacionalPanel
              data={operacional.data}
              isLoading={operacional.isLoading}
              error={operacional.error}
            />
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
            <IngresosTable
              items={ingresos.data ?? []}
              isLoading={ingresos.isLoading}
              error={ingresos.error}
              caption={t('reporteria.ingresos.caption', 'Ingresos de la sucursal')}
            />
          </TabsContent>

          <TabsContent value="salidas">
            <SalidasTable
              items={salidas.data ?? []}
              isLoading={salidas.isLoading}
              error={salidas.error}
              caption={t('reporteria.salidas.caption', 'Salidas de la sucursal')}
            />
          </TabsContent>

          <TabsContent value="ocupacion">
            <OcupacionPanel
              data={ocupacion.data}
              isLoading={ocupacion.isLoading}
              error={ocupacion.error}
            />
          </TabsContent>
        </Tabs>
      </div>
    </main>
  );
}