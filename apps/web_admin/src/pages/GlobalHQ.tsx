/**
 * `GlobalHQ.tsx` — landing post-login del administrador. Antes `HomeHub`
 * (refactor de scope: ahora el `/` es un panel ejecutivo multi-sucursal,
 * no un grid vacío de links).
 *
 * INVARIANTE ARQUITECTÓNICO (no romper): esta página se monta FUERA de
 * `<RequireSucursal>`. Por eso no tiene `<AdminChrome />`, no tiene
 * `SucursalSelectorBadge`, no tiene `BranchSelector`. El selector de
 * sucursal aparece SOLO en las rutas gateadas por `<RequireSucursal>`
 * (dashboard, audit, etc.). Pineado por `GlobalHQ.test.tsx` H1/H2 y
 * por `App.test.tsx` "does NOT mount the chrome on /".
 *
 * DEC-LOGIN-07 (revisado): el post-login ya no fuerza
 * `/seleccionar-sucursal`. El admin aterriza acá y la selección de
 * sucursal pasa a ser opt-in vía la rail item "Sucursales" o el topbar
 * en rutas branch-scoped.
 *
 * POST-SPLIT: las 6 cards que estaban mezcladas en `/dashboard` (que
 * pretendían ser "de la sucursal seleccionada" pero agregaban TODAS las
 * permitidas) viven ahora acá, en su contexto correcto. La
 * responsabilidad de `/` es multi-sucursal; la de `/dashboard` es
 * branch-scoped. Cada superficie importa solo el hook que le
 * corresponde (`useResumenKpi` vs `useSucursalKpi`) — ver
 * `features/dashboard/hooks/`.
 *
 * LAYOUT: 2 columnas (≥1024px) con un rail derecho sticky que aloja
 * los 8 accesos rápidos. Antes era un grid 2×4 de cards al final de
 * la página (725px de alto en viewport 1080p, 82% de la pantalla) que
 * "se perdían" debajo del fold. El rail mantiene los 8 accesos
 * permanentemente visibles sin sacrificar la lectura vertical de los
 * KPIs y los charts. Estilo Linear/Vercel admin.
 */
import { lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Banknote,
  Bell,
  BookOpen,
  Building2,
  ChevronRight,
  FolderTree,
  Landmark,
  Send,
  Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { Skeleton } from '@/components/ui/skeleton';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { useResumenKpi } from '@/features/dashboard/hooks/useResumenKpi';

// Charts that depend on the cross-branch resumen are lazy-loaded so
// they only land in the bundle when the user actually lands on `/`.
// Sister boundary on `/dashboard` (`BranchCharts.tsx`) keeps the
// branch-scoped chart out of this surface's chunk and vice-versa.
const CrossBranchCharts = lazy(
  () => import('@/features/dashboard/components/CrossBranchCharts'),
);

interface HubCard {
  key:
    | 'sucursales'
    | 'catalogos'
    | 'empresa'
    | 'usuarios'
    | 'arqueos'
    | 'alertas'
    | 'dian'
    | 'auditoria';
  path: string;
  icon: LucideIcon;
  titleKey: string;
  descriptionKey: string;
  /** Test id for the rail row. The 8 rail items keep the
   *  `home-hub-card-*` testids for backward compat with the old
   *  2×4 grid layout (and with `App.test.tsx`'s assertions). */
  testId: string;
}

export const HUB_CARDS: readonly HubCard[] = [
  {
    key: 'sucursales',
    path: '/seleccionar-sucursal',
    icon: Building2,
    titleKey: 'homeHub.sucursales.label',
    descriptionKey: 'homeHub.sucursales.description',
    testId: 'home-hub-card-sucursales',
  },
  {
    key: 'catalogos',
    path: '/catalogos',
    icon: FolderTree,
    titleKey: 'homeHub.catalogos.label',
    descriptionKey: 'homeHub.catalogos.description',
    testId: 'home-hub-card-catalogos',
  },
  {
    key: 'empresa',
    path: '/empresa',
    icon: Landmark,
    titleKey: 'homeHub.empresa.label',
    descriptionKey: 'homeHub.empresa.description',
    testId: 'home-hub-card-empresa',
  },
  {
    key: 'usuarios',
    path: '/usuarios',
    icon: Users,
    titleKey: 'homeHub.usuarios.label',
    descriptionKey: 'homeHub.usuarios.description',
    testId: 'home-hub-card-usuarios',
  },
  {
    key: 'arqueos',
    path: '/arqueos',
    icon: Banknote,
    titleKey: 'homeHub.arqueos.label',
    descriptionKey: 'homeHub.arqueos.description',
    testId: 'home-hub-card-arqueos',
  },
  {
    key: 'alertas',
    path: '/alertas',
    icon: Bell,
    titleKey: 'homeHub.alertas.label',
    descriptionKey: 'homeHub.alertas.description',
    testId: 'home-hub-card-alertas',
  },
  {
    key: 'dian',
    path: '/dian',
    icon: Send,
    titleKey: 'homeHub.dian.label',
    descriptionKey: 'homeHub.dian.description',
    testId: 'home-hub-card-dian',
  },
  {
    key: 'auditoria',
    path: '/auditoria/log',
    icon: BookOpen,
    titleKey: 'homeHub.auditoria.label',
    descriptionKey: 'homeHub.auditoria.description',
    testId: 'home-hub-card-auditoria',
  },
] as const;

function formatLag(seconds: number | null): string {
  if (seconds === null) return '—';
  if (seconds < 60) return `${seconds} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h`;
  return `${Math.round(seconds / 86400)} d`;
}

export default function GlobalHQ(): JSX.Element {
  const { t } = useTranslation();
  const { sucursalUuids: permitidas } = useAdminAuth();
  const resumen = useResumenKpi(permitidas);

  const topSucursal = resumen.topSucursales.value?.[0];
  const mediosPagoTotal = (resumen.mediosPago.value ?? []).reduce(
    (acc, m) => acc + m.monto_total,
    0,
  );
  const totalAlertas = (resumen.alertas.value ?? []).reduce(
    (acc, a) => acc + a.count,
    0,
  );
  const alertasCriticas =
    (resumen.alertas.value ?? []).find((a) => a.severity === 'critical')?.count ?? 0;
  const lastLag = resumen.sync.value?.max_lag_seconds ?? null;

  return (
    <div
      className="mx-auto max-w-7xl px-4 py-8"
      data-testid="global-hq"
    >
      <header className="mb-6" data-testid="global-hq-header">
        <h1 className="text-2xl font-bold tracking-tight">
          {t('globalHq.title', 'Panel global del parqueo')}
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">
          {t(
            'globalHq.subtitle',
            '{{branches}} sucursal(es) autorizada(s) · {{alertas}} alertas · lag máximo {{lag}}.',
            {
              branches: permitidas.length,
              alertas: totalAlertas,
              lag: formatLag(lastLag),
            },
          )}
        </p>
      </header>

      {/* 2-column layout (≥lg): main column on the left (KPIs + charts),
          right rail on the right (8 access rows). Below `lg` the rail
          stacks on top so the page is still readable on smaller
          viewports (the 1080p desktop case is the design target). */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
        <main className="flex min-w-0 flex-col gap-6">
          {/* 6 cross-branch KPIs. The BranchSelector is intentionally
              absent on this surface — `/` lives outside
              `RequireSucursal`, and the whole point of these cards is
              the aggregate across every permitted branch. */}
          <section
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
            aria-label="métricas ejecutivas multi-sucursal"
            data-testid="global-hq-kpi-grid"
          >
            <KpiCard
              label={t('dashboard.ocupacionAgregada', 'Ocupación agregada')}
              loading={resumen.ocupacion.loading}
              error={resumen.ocupacion.error}
              render={() => (
                <p className="text-2xl font-semibold tabular-nums">
                  {resumen.ocupacion.value?.porcentaje === null ||
                  resumen.ocupacion.value?.porcentaje === undefined
                    ? '—'
                    : `${resumen.ocupacion.value.porcentaje.toFixed(0)}%`}
                  <span className="ml-2 text-sm font-normal text-muted-foreground">
                    {resumen.ocupacion.value?.ocupados ?? 0}/{resumen.ocupacion.value?.capacidad ?? 0}
                  </span>
                </p>
              )}
            />
            <KpiCard
              label={t('dashboard.suscripcionesActivas', 'Suscripciones activas')}
              value={resumen.suscripciones.value}
              loading={resumen.suscripciones.loading}
              error={resumen.suscripciones.error}
            />
            <KpiCard
              label={t('dashboard.mediosPagoDia', 'Medios de pago (hoy)')}
              loading={resumen.mediosPago.loading}
              error={resumen.mediosPago.error}
              render={() => (
                <p className="text-2xl font-semibold tabular-nums">
                  ${mediosPagoTotal.toLocaleString('es-CO')}
                  <span className="ml-2 text-sm font-normal text-muted-foreground">
                    {(resumen.mediosPago.value ?? []).length} medios
                  </span>
                </p>
              )}
            />

            <KpiCard
              label={t('dashboard.topSucursal', 'Top sucursal (30 días)')}
              loading={resumen.topSucursales.loading}
              error={resumen.topSucursales.error}
              render={() => (
                <p className="text-lg font-semibold">
                  {topSucursal
                    ? `${topSucursal.nombre ?? topSucursal.uuid_sucursal.slice(0, 8)} — $${topSucursal.monto_total.toLocaleString('es-CO')}`
                    : 'Sin datos'}
                </p>
              )}
            />
            <KpiCard
              label={t('dashboard.syncAgregado', 'Estado de sincronización')}
              loading={resumen.sync.loading}
              error={resumen.sync.error}
              render={() => (
                <p className="text-2xl font-semibold tabular-nums">
                  {resumen.sync.value?.sucursales_ok ?? 0}
                  <span className="text-muted-foreground">/{permitidas.length}</span>
                  <span className="ml-2 text-sm font-normal text-muted-foreground">al día</span>
                </p>
              )}
            />
            <KpiCard
              label={t('dashboard.alertasSeveridad', 'Alertas abiertas')}
              loading={resumen.alertas.loading}
              error={resumen.alertas.error}
              render={() => (
                <p className="text-2xl font-semibold tabular-nums">
                  {totalAlertas}
                  {alertasCriticas > 0 && (
                    <span className="ml-2 text-sm font-normal text-destructive">
                      {alertasCriticas} críticas
                    </span>
                  )}
                </p>
              )}
            />
          </section>

          <section
            aria-label="gráficas ejecutivas"
            data-testid="global-hq-charts"
          >
            <Suspense
              fallback={
                <div
                  className="grid grid-cols-1 gap-4 lg:grid-cols-3"
                  data-testid="global-hq-charts-loading"
                >
                  <Skeleton className="h-48" />
                  <Skeleton className="h-48" />
                  <Skeleton className="h-48" />
                </div>
              }
            >
              <CrossBranchCharts resumen={resumen.resumen} />
            </Suspense>
          </section>
        </main>

        {/* Right rail. The 8 access links stay permanently visible
            (sticky on desktop) regardless of scroll. Each row is a
            single `<a>`: icon + label + chevron, hover/focus state via
            `hover:bg-accent`. The KPI "Alertas" already surfaces the
            count prominently, so no badge decoration in the rail
            (keeps the pattern minimal and avoids nested-anchor issues
            the old grid had to dance around with `pointer-events`). */}
        <aside
          className="lg:sticky lg:top-4 lg:self-start"
          aria-label="accesos rápidos"
          data-testid="global-hq-quick-links"
        >
          <h2 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t('globalHq.accessTitle', 'Accesos rápidos')}
          </h2>
          <nav>
            <ul className="flex flex-col gap-0.5">
              {HUB_CARDS.map((card) => {
                const Icon = card.icon;
                return (
                  <li key={card.key}>
                    <Link
                      to={card.path}
                      data-testid={card.testId}
                      aria-label={t(card.titleKey)}
                      className="group focus-ring flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium text-foreground transition-colors duration-base ease-macos hover:bg-accent hover:text-accent-foreground"
                    >
                      <Icon
                        aria-hidden="true"
                        className="text-muted-foreground group-hover:text-foreground size-4 shrink-0"
                      />
                      <span className="min-w-0 flex-1 truncate">
                        {t(card.titleKey)}
                      </span>
                      <ChevronRight
                        aria-hidden="true"
                        className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-transform duration-base ease-macos group-hover:translate-x-0.5"
                      />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </aside>
      </div>
    </div>
  );
}
