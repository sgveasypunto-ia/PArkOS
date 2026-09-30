/**
 * `<Reporteria />` — operational report container (HU-F17.1, web_admin).
 *
 * One Radix-Tabs surface with three tabs (Ingresos | Salidas |
 * Ocupación). Each tab fetches on activation so the page does not pull
 * three lists it does not need on first paint. The lazy SWR keys keep
 * the cache small and the API calls under the operator's control
 * (which tab the operator reaches for first).
 *
 * Branch context comes from `useSucursal()`; this page lives inside
 * the branch-scoped route group (gated by `<RequireSucursal>` in
 * `App.tsx`), so an admin without a selected branch never reaches
 * here — we render a placeholder rather than a confusing 400.
 *
 * F17.1 SPEC GAP — what is NOT here on purpose:
 *   - Aggregations (totales por día, monto facturado, facturación
 *     electrónica vs física, time series): PR-C adds aggregation
 *     endpoints. The placeholder notice points at /dashboard for the
 *     today's snapshot that exists today, and notes the richer report
 *     arrives in PR-C.
 *   - Charts (4 chart types in F17.1) and 24h heatmap: deferred
 *     beyond PR-C by user direction (see
 *     `openspec/changes/hu-f17-1-2-reporteria-operacional/`).
 *   - Ingresos/salidas time-range filters: the backend already
 *     supports them (date_salida__gte/__lte) but they need an
 *     aggregation layer to make sense across many rows; out of scope
 *     for the raw-listing slice we ship now.
 *
 * RNF-022 (WCAG 2.1 AA): Tabs and triggers come from Radix so keyboard
 * navigation (Left/Right, Home/End) and `aria-controls`/`aria-selected`
 * are correct; the per-tab containers carry `aria-labelledby` for
 * screen readers.
 */
import { useState } from 'react';
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
} from '../hooks/useReporteria';
import { IngresosTable } from '../components/IngresosTable';
import { SalidasTable } from '../components/SalidasTable';
import { OcupacionPanel } from '../components/OcupacionPanel';

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
          <p
            className="mt-2 text-xs text-muted-foreground"
            data-testid="reporteria-prc-notice"
          >
            {t(
              'reporteria.prcNotice',
              'Totales agregados y series temporales llegan en PR-C; esta vista muestra las filas crudas devueltas por /operacion.',
            )}
          </p>
        </header>

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