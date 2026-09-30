import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import useSWR from 'swr';
import { BranchSelector, type BranchOption } from '@/components/branch-selector/BranchSelector';
import { parkosFetchRaw } from '@/lib/fetch';
import { useSucursal } from '@/lib/sucursal-context';
import { useCantidadList } from '@/features/cupos/hooks/useCantidadList';
import { useTarifasList } from '@/features/tarifas/hooks/useTarifasList';
import { useAdminUsuarios } from '@/features/admin/hooks/useAdminUsuarios';
import { listAdminUsuarioSucursales } from '@/features/admin/api/adminUsuariosApi';

/**
 * Dashboard — multi-tenant admin landing page (T-PR10-10..13).
 *
 * Loads the permitted branches from `/api/v1/admin/me` on mount, renders
 * the `<BranchSelector>` so the operator can pick which branch they want
 * to inspect, then fetches that branch's aggregates from
 * `/api/v1/admin/sucursales/{uuid}/dashboard`.
 *
 * Persistence: the selected UUID lives in `localStorage` under
 * `parkos.lastSelectedSucursal` (set by `SucursalProvider`); on reload,
 * `useSucursal()` rehydrates it and the dashboard skips the
 * `sucursales_permitidas` bootstrap step.
 *
 * SWR key strategy: the dashboard key embeds the branch UUID, so the
 * SWR invalidator (`useInvalidateOnBranchSwitch`) drops the cache for
 * the previously-selected branch on every switch — no stale data leaks.
 *
 * HU-F17.2 (monto real): the backend currently hardcodes
 * ``ingresos_monto_total = 0.0`` because the amount is derived at exit
 * via ``Ingreso -> Facturas -> FacturaPagos.total`` and no aggregation
 * endpoint exists yet. The card surfaces this honestly with a
 * "pendiente PR-C" hint pointing the admin to `/reporteria`, where the
 * raw row data is already visible. The endpoint that closes the gap
 * (factura chain aggregation per branch) ships in PR-C.
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

interface SucursalDashboard {
  uuid_sucursal: string;
  fecha: string;
  ingresos_count: number;
  ingresos_monto_total: number;
  facturas_emitidas_count: number;
  facturas_electronicas_count: number;
  open_alertas_count: number;
  sync_health: {
    last_sync_at: string | null;
    lag_seconds: number | null;
    queue_depth: number;
  };
}

const ME_KEY = '/api/v1/admin/me';
const SUCURSALES_KEY = '/api/v1/sucursales';
const DASHBOARD_KEY = (uuid: string): string =>
  `/api/v1/admin/sucursales/${uuid}/dashboard`;

const jsonFetcher = async <T,>(url: string): Promise<T> => {
  const res = await parkosFetchRaw(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`fetch ${url} failed: ${res.status}`);
  }
  return (await res.json()) as T;
};

export default function Dashboard() {
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

  const dashboard = useSWR<SucursalDashboard>(
    selected ? DASHBOARD_KEY(selected) : null,
    jsonFetcher<SucursalDashboard>,
    { revalidateOnFocus: false },
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
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <header className="flex flex-col gap-4 border-b pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">
              {t('dashboard.title', 'Panel de sucursal')}
            </h1>
            <p className="text-sm text-muted-foreground">
              {t('dashboard.subtitle', 'Métricas en vivo de la sucursal seleccionada.')}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-muted-foreground">
              {t('branchSelector.label', 'Sucursal')}
            </span>
            <BranchSelector
              options={branchOptions}
              value={selected}
              onChange={setSelected}
            />
          </div>
        </header>

        <section
          className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-7"
          aria-label="métricas"
        >
          <MetricCard
            label={t('dashboard.ingresos', 'Ingresos')}
            value={dashboard.data?.ingresos_count}
            loading={dashboard.isLoading}
            error={Boolean(dashboard.error)}
          />
          <MetricCard
            label={t('dashboard.facturas', 'Facturas')}
            value={dashboard.data?.facturas_emitidas_count}
            loading={dashboard.isLoading}
            error={Boolean(dashboard.error)}
          />
          <MetricCard
            label={t('dashboard.alertas', 'Alertas abiertas')}
            value={dashboard.data?.open_alertas_count}
            loading={dashboard.isLoading}
            error={Boolean(dashboard.error)}
          />
          <MetricCard
            label={t('dashboard.montoTotal', 'Monto total (COP)')}
            value={dashboard.data?.ingresos_monto_total}
            loading={dashboard.isLoading}
            error={Boolean(dashboard.error)}
            to="/reporteria"
            linkHint={t('dashboard.prcNotice', 'Pendiente PR-C — ver reportería →')}
          />
          <MetricCard
            label={t('dashboard.usuariosAsignados', 'Usuarios asignados')}
            value={usuariosCount}
            loading={usuariosCountSWR.isLoading}
            error={Boolean(usuariosCountSWR.error)}
            to="/gestion-usuarios"
            linkHint={t('dashboard.verUsuarios', 'Ver gestión de usuarios →')}
          />
          <MetricCard
            label={t('dashboard.cuposVigentes', 'Cupos vigentes')}
            value={cuposCount}
            loading={false}
            error={false}
            to="/cupos"
            linkHint={t('dashboard.verCupos', 'Ver cupos →')}
          />
          <MetricCard
            label={t('dashboard.tarifasVigentes', 'Tarifas vigentes')}
            value={tarifasCount}
            loading={false}
            error={false}
            to="/tarifas"
            linkHint={t('dashboard.verTarifas', 'Ver tarifas →')}
          />
        </section>

        {!selected && (
          <p className="text-sm text-muted-foreground" data-testid="dashboard-no-branch">
            {t('dashboard.noBranch', 'Seleccioná una sucursal para ver el panel.')}
          </p>
        )}
        {dashboard.error && (
          <p className="text-sm text-destructive" data-testid="dashboard-error">
            {t('dashboard.loadError', 'No se pudo cargar el panel de la sucursal.')}
          </p>
        )}
      </div>
    </main>
  );
}

/* ------------------------------------------------------------------ */
/*  Local UI                                                          */
/* ------------------------------------------------------------------ */

function MetricCard({
  label,
  value,
  loading,
  error,
  to,
  linkHint,
}: {
  label: string;
  value: number | undefined;
  loading: boolean;
  error: boolean;
  to?: string;
  linkHint?: string;
}) {
  const display = error ? '—' : loading ? '…' : (value ?? 0);
  const testId = `metric-card-${label.toLowerCase().replace(/\s+/g, '-')}`;
  const body = (
    <>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-3xl font-semibold tabular-nums">{display}</p>
      {linkHint ? (
        <p className="mt-2 text-xs font-medium text-primary">{linkHint}</p>
      ) : null}
    </>
  );
  if (to) {
    return (
      <Link
        to={to}
        className="rounded-lg border bg-card p-4 text-card-foreground shadow-sm transition-shadow hover:shadow-md focus:outline-none focus:ring-2 focus:ring-ring"
        data-testid={testId}
      >
        {body}
      </Link>
    );
  }
  return (
    <article
      className="rounded-lg border bg-card p-4 text-card-foreground shadow-sm"
      data-testid={testId}
    >
      {body}
    </article>
  );
}
