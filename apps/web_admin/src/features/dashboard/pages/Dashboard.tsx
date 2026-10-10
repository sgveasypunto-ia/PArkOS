import { lazy, Suspense, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';
import { BranchSelector, type BranchOption } from '@/components/branch-selector/BranchSelector';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { Skeleton } from '@/components/ui/skeleton';
import { parkosFetchRaw } from '@/lib/fetch';
import { useSucursal } from '@/lib/sucursal-context';
import { useCantidadList } from '@/features/cupos/hooks/useCantidadList';
import { useTarifasList } from '@/features/tarifas/hooks/useTarifasList';
import { useAdminUsuarios } from '@/features/admin/hooks/useAdminUsuarios';
import { listAdminUsuarioSucursales } from '@/features/admin/api/adminUsuariosApi';
import { offsetISO, todayISO } from '@/features/reporteria/components/dateRange';
import { useReporteriaOperacional } from '@/features/reporteria/hooks/useReporteria';

import { useSucursalKpi } from '../hooks/useSucursalKpi';

// Dynamic import (T5): the branch-scoped chart and its SVG code never
// ship in the initial bundle -- only when /dashboard actually mounts.
// The cross-branch charts (`CrossBranchCharts.tsx`) live in a separate
// `lazy()` boundary on `/` (the global HQ), so the dashboard bundle
// stays free of `HeatmapOcupacion`, `ChartBar`, `ChartPie` and the
// cross-branch resumen fetcher.
const BranchCharts = lazy(() => import('../components/BranchCharts'));

/**
 * Dashboard — branch-scoped executive landing page (HU-F17.1, post-split).
 *
 * Lives inside `<RequireSucursal>`, so a `selected` UUID is guaranteed
 * non-null by the time this component renders. The header is a real
 * "you are looking at one branch" surface: a `<BranchSelector>` pinned
 * to the top and a subtitle that names the branch scope explicitly.
 *
 * Two things were REMOVED in the post-split refactor:
 *   - The 6 cross-branch KPI cards (ocupación agregada, suscripciones,
 *     medios de pago, top sucursales, sync agregado, alertas) moved
 *     to the global HQ at `/` (`useResumenKpi`). They were misleading
 *     on a "sucursal seleccionada" page: a Top Sucursal ranking that
 *     ignores your selector is not a Top Sucursal, and a "Sync 0/19"
 *     whose denominator is 19 branches does not reflect the branch
 *     you picked.
 *   - The cross-branch charts (top-5, FE 24h, occupancy heatmap) also
 *     moved to `/`. The dashboard now keeps only the branch-scoped
 *     ingresos 30-day line.
 *
 * What stays: the 3 per-branch cards (ingresos / facturas / monto
 * total) and the 4 quick-link cards filtered by `selected`.
 */

interface AdminMe {
  actor_uuid: string;
  email: string | null;
  rol: string | null;
  sucursales_permitidas: string[];
  permissions: string[];
}

interface SucursalItem {
  uuid: string;
  nombre: string | null;
}

interface SucursalListResponse {
  items: SucursalItem[];
  next_cursor: string | null;
}

const ME_KEY = '/api/v1/admin/me';
const SUCURSALES_KEY = '/api/v1/sucursales';

const jsonFetcher = async <T,>(url: string): Promise<T> => {
  const res = await parkosFetchRaw(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`fetch ${url} failed: ${res.status}`);
  }
  return (await res.json()) as T;
};

export default function Dashboard(): JSX.Element {
  const { t } = useTranslation();
  const { selected, setSelected } = useSucursal();

  const me = useSWR<AdminMe>(ME_KEY, jsonFetcher<AdminMe>, {
    revalidateOnFocus: false,
  });

  const sucursales = useSWR<SucursalListResponse>(
    SUCURSALES_KEY,
    jsonFetcher<SucursalListResponse>,
    { revalidateOnFocus: false },
  );

  // Pick a default the first time we have the list — first permitted
  // branch, unless the user already selected one (persisted via
  // SucursalContext). The gate upstream (`RequireSucursal`) blocks
  // this render until `selected` is in `sucursalUuids`, so by the
  // time we mount the `selected ??` is just a defensive fallback.
  useEffect(() => {
    if (selected) return;
    const items = sucursales.data?.items ?? [];
    const mePermitidas = me.data?.sucursales_permitidas ?? [];
    const candidates = items.filter((i) => mePermitidas.includes(i.uuid));
    const first = candidates[0] ?? items[0];
    if (first) {
      setSelected(first.uuid);
    }
  }, [selected, sucursales.data, me.data, setSelected]);

  const branchOptions: BranchOption[] = useMemo(() => {
    const items = sucursales.data?.items ?? [];
    const permitidas = new Set(me.data?.sucursales_permitidas ?? []);
    return items
      .filter((i) => permitidas.has(i.uuid))
      .map((i) => ({ uuid: i.uuid, nombre: i.nombre }));
  }, [sucursales.data, me.data]);

  const kpi = useSucursalKpi(selected);

  const operacional = useReporteriaOperacional(
    selected
      ? { uuid_sucursal: selected, fecha_desde: offsetISO(-29), fecha_hasta: todayISO() }
      : null,
  );

  const { cupos } = useCantidadList();
  const { tarifas } = useTarifasList(null);
  const { usuarios } = useAdminUsuarios();

  const cuposCount = useMemo(
    () => cupos.filter((c) => c.uuid_sucursal === selected).length,
    [cupos, selected],
  );
  const tarifasCount = useMemo(
    () => tarifas.filter((t) => t.uuid_sucursal === selected).length,
    [tarifas, selected],
  );

  const usuariosCountSWR = useSWR<number>(
    selected && usuarios ? `dashboard-usuarios-count-${selected}` : null,
    async () => {
      let count = 0;
      await Promise.all(
        (usuarios ?? []).map(async (u) => {
          try {
            const items = await listAdminUsuarioSucursales(u.uuid);
            if (items.some((a) => a.uuid_sucursal === selected)) count++;
          } catch {
            // skip user on per-row failure — count stays best-effort
          }
        }),
      );
      return count;
    },
    { revalidateOnFocus: false },
  );
  const usuariosCount = usuariosCountSWR.data ?? 0;

  return (
    <main
      className="min-h-screen bg-background p-6"
      data-testid="page-dashboard"
    >
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <header className="flex flex-col gap-4 border-b pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">
              {t('dashboard.title', 'Panel ejecutivo')}
            </h1>
            <p className="text-sm text-muted-foreground">
              {t(
                'dashboard.subtitle',
                'Métricas operativas de la sucursal seleccionada.',
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-muted-foreground">
              {t('branchSelector.label', 'Sucursal')}
            </span>
            <BranchSelector options={branchOptions} value={selected} onChange={setSelected} />
          </div>
        </header>

        {/* Row 1: 3 cards strictly scoped to the selected branch. The
            cross-branch resumen no longer rides on this surface -- see
            the global HQ at `/` (post-split refactor). */}
        <section
          className="grid grid-cols-1 gap-4 sm:grid-cols-3"
          aria-label="métricas de la sucursal"
          data-testid="dashboard-kpi-grid"
        >
          <KpiCard
            label={t('dashboard.ingresos', 'Ingresos')}
            value={kpi.ingresos.value}
            loading={kpi.ingresos.loading}
            error={kpi.ingresos.error}
          />
          <KpiCard
            label={t('dashboard.facturas', 'Facturas')}
            value={kpi.facturas.value}
            loading={kpi.facturas.loading}
            error={kpi.facturas.error}
          />
          <KpiCard
            label={t('dashboard.montoTotal', 'Monto total (COP)')}
            value={kpi.montoTotal.value?.toLocaleString('es-CO')}
            loading={kpi.montoTotal.loading}
            error={kpi.montoTotal.error}
          />
        </section>

        {/* Row 2: per-branch shortcuts that lived in the original
            7-card grid, kept as quick links rather than dropped. */}
        <section
          className="grid grid-cols-2 gap-3 sm:grid-cols-4"
          aria-label="accesos rápidos"
          data-testid="dashboard-quick-links"
        >
          <KpiCard
            label={t('dashboard.usuariosAsignados', 'Usuarios asignados')}
            value={usuariosCount}
            loading={usuariosCountSWR.isLoading}
            error={Boolean(usuariosCountSWR.error)}
            to="/gestion-usuarios"
            linkHint={t('dashboard.verUsuarios', 'Ver gestión de usuarios →')}
          />
          <KpiCard
            label={t('dashboard.cuposVigentes', 'Cupos vigentes')}
            value={cuposCount}
            loading={false}
            error={false}
            to="/cupos"
            linkHint={t('dashboard.verCupos', 'Ver cupos →')}
          />
          <KpiCard
            label={t('dashboard.tarifasVigentes', 'Tarifas vigentes')}
            value={tarifasCount}
            loading={false}
            error={false}
            to="/tarifas"
            linkHint={t('dashboard.verTarifas', 'Ver tarifas →')}
          />
          <KpiCard
            label={t('dashboard.montoTotalReporteria', 'Detalle de ingresos')}
            value="→"
            loading={false}
            error={false}
            to="/reporteria"
            linkHint={t('dashboard.verReporteria', 'Ver reportería →')}
          />
        </section>

        {(kpi.ingresos.error || kpi.facturas.error || kpi.montoTotal.error) && (
          <p className="text-sm text-destructive" data-testid="dashboard-error">
            {t('dashboard.loadError', 'No se pudo cargar el panel de la sucursal.')}
          </p>
        )}

        <Suspense
          fallback={
            <div className="grid grid-cols-1 gap-6" data-testid="dashboard-charts-loading">
              <Skeleton className="h-48" />
            </div>
          }
        >
          <BranchCharts operacional={operacional.data} />
        </Suspense>
      </div>
    </main>
  );
}
