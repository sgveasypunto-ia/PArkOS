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

import { useKpiData } from '../hooks/useKpiData';

// Dynamic import (T5): the 4-chart section and its SVG/table-toggle code
// never ship in the initial bundle -- only when the dashboard actually
// mounts, and only once.
const ChartsSection = lazy(() => import('../components/ChartsSection'));

/**
 * Dashboard — multi-tenant admin executive landing page (HU-F17.1).
 *
 * Loads the permitted branches from `/api/v1/admin/me` on mount, renders
 * the `<BranchSelector>` so the operator can pick which branch they want
 * to inspect, then fetches that branch's aggregates from
 * `/api/v1/admin/sucursales/{uuid}/dashboard` for the 3 per-branch cards
 * (ingresos, facturas, monto total). `ingresos_monto_total` is the real
 * `facturas -> ingreso` chain sum (BR1, closed by a prior HU on this
 * same endpoint) -- NOT the historical `0.0` placeholder this file used
 * to warn about; that warning is now stale and removed.
 *
 * A second, cross-branch row sources 6 more KPI cards from the new
 * `/api/v1/admin/dashboard/resumen` endpoint (BR2), scoped to every
 * branch the actor is permitted on: ocupación agregada, suscripciones
 * activas, medios de pago del día, top sucursales, estado de sync, y
 * alertas por severidad. See `hooks/useKpiData.ts` for why 9 cards only
 * cost 2 real HTTP requests.
 *
 * Persistence: the selected UUID lives in `localStorage` under
 * `parkos.lastSelectedSucursal` (set by `SucursalProvider`); on reload,
 * `useSucursal()` rehydrates it and the dashboard skips the
 * `sucursales_permitidas` bootstrap step.
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
  // SucursalContext).
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

  const permitidas = me.data?.sucursales_permitidas ?? [];
  const kpi = useKpiData(selected, permitidas);

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

  const topSucursal = kpi.topSucursales.value?.[0];
  const mediosPagoTotal = (kpi.mediosPago.value ?? []).reduce(
    (acc, m) => acc + m.monto_total,
    0,
  );

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
                'Métricas de la sucursal seleccionada + resumen ejecutivo multi-sucursal.',
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

        {/* Executive 3x3 grid (T4): row 1 is the selected branch's own
            metrics; rows 2-3 are the cross-branch resumen (BR2). */}
        <section
          className="grid grid-cols-1 gap-4 sm:grid-cols-3"
          aria-label="métricas ejecutivas"
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

          <KpiCard
            label={t('dashboard.ocupacionAgregada', 'Ocupación agregada')}
            loading={kpi.ocupacion.loading}
            error={kpi.ocupacion.error}
            render={() => (
              <p className="text-3xl font-semibold tabular-nums">
                {kpi.ocupacion.value?.porcentaje === null ||
                kpi.ocupacion.value?.porcentaje === undefined
                  ? '—'
                  : `${kpi.ocupacion.value.porcentaje.toFixed(0)}%`}
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  {kpi.ocupacion.value?.ocupados ?? 0}/{kpi.ocupacion.value?.capacidad ?? 0}
                </span>
              </p>
            )}
          />
          <KpiCard
            label={t('dashboard.suscripcionesActivas', 'Suscripciones activas')}
            value={kpi.suscripciones.value}
            loading={kpi.suscripciones.loading}
            error={kpi.suscripciones.error}
          />
          <KpiCard
            label={t('dashboard.mediosPagoDia', 'Medios de pago (hoy)')}
            loading={kpi.mediosPago.loading}
            error={kpi.mediosPago.error}
            render={() => (
              <p className="text-3xl font-semibold tabular-nums">
                ${mediosPagoTotal.toLocaleString('es-CO')}
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  {(kpi.mediosPago.value ?? []).length} medios
                </span>
              </p>
            )}
          />

          <KpiCard
            label={t('dashboard.topSucursal', 'Top sucursal (30 días)')}
            loading={kpi.topSucursales.loading}
            error={kpi.topSucursales.error}
            render={() => (
              <p className="text-xl font-semibold">
                {topSucursal
                  ? `${topSucursal.nombre ?? topSucursal.uuid_sucursal.slice(0, 8)} — $${topSucursal.monto_total.toLocaleString('es-CO')}`
                  : 'Sin datos'}
              </p>
            )}
          />
          <KpiCard
            label={t('dashboard.syncAgregado', 'Estado de sincronización')}
            loading={kpi.sync.loading}
            error={kpi.sync.error}
            render={() => (
              <p className="text-3xl font-semibold tabular-nums">
                {kpi.sync.value?.sucursales_ok ?? 0}
                <span className="text-muted-foreground">/{permitidas.length}</span>
                <span className="ml-2 text-sm font-normal text-muted-foreground">al día</span>
              </p>
            )}
          />
          <KpiCard
            label={t('dashboard.alertasSeveridad', 'Alertas abiertas')}
            loading={kpi.alertas.loading}
            error={kpi.alertas.error}
            render={() => {
              const total = (kpi.alertas.value ?? []).reduce((acc, a) => acc + a.count, 0);
              const criticas =
                (kpi.alertas.value ?? []).find((a) => a.severity === 'critical')?.count ?? 0;
              return (
                <p className="text-3xl font-semibold tabular-nums">
                  {total}
                  {criticas > 0 && (
                    <span className="ml-2 text-sm font-normal text-destructive">
                      {criticas} críticas
                    </span>
                  )}
                </p>
              );
            }}
          />
        </section>

        {/* Secondary row: per-branch shortcuts that lived in the original
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

        {!selected && (
          <p className="text-sm text-muted-foreground" data-testid="dashboard-no-branch">
            {t('dashboard.noBranch', 'Seleccioná una sucursal para ver el panel.')}
          </p>
        )}
        {(kpi.ingresos.error || kpi.facturas.error || kpi.montoTotal.error) && (
          <p className="text-sm text-destructive" data-testid="dashboard-error">
            {t('dashboard.loadError', 'No se pudo cargar el panel de la sucursal.')}
          </p>
        )}

        <Suspense
          fallback={
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2" data-testid="dashboard-charts-loading">
              <Skeleton className="h-48" />
              <Skeleton className="h-48" />
              <Skeleton className="h-48" />
              <Skeleton className="h-48" />
            </div>
          }
        >
          <ChartsSection operacional={operacional.data} resumen={kpi.resumen} />
        </Suspense>
      </div>
    </main>
  );
}
