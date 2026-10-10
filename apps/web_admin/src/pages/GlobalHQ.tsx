/**
 * `GlobalHQ.tsx` — landing post-login del administrador. Antes `HomeHub`
 * (refactor de scope: ahora el `/` es un panel ejecutivo multi-sucursal,
 * no un grid vacío de links).
 *
 * INVARIANTE ARQUITECTÓNICO (no romper): esta página se monta FUERA de
 * `<RequireSucursal>`. El branch selector (`chrome-sucursal-selector`)
 * vive en `<TopNav>` y SOLO se renderiza cuando `selected !== null`,
 * por eso en `/` con `selected = null` la invariante "no chrome
 * branch-scoped" sigue cumpliéndose — pineado por `App.test.tsx`
 * "mounts TopNav but NOT AdminChrome on /".
 *
 * DEC-LOGIN-07 (revisado): el post-login ya no fuerza
 * `/seleccionar-sucursal`. El admin aterriza acá y la selección de
 * sucursal pasa a ser opt-in vía el sidebar persistente (item
 * "Sucursales") o el topbar en rutas branch-scoped.
 *
 * POST-SPLIT: las 6 cards que estaban mezcladas en `/dashboard` (que
 * pretendían ser "de la sucursal seleccionada" pero agregaban TODAS las
 * permitidas) viven ahora acá, en su contexto correcto. La
 * responsabilidad de `/` es multi-sucursal; la de `/dashboard` es
 * branch-scoped. Cada superficie importa solo el hook que le
 * corresponde (`useResumenKpi` vs `useSucursalKpi`) — ver
 * `features/dashboard/hooks/`.
 *
 * POST-SIDEBAR: el bloque "Accesos rápidos" que vivía en `<aside>` al
 * fondo de esta página se movió a `<AppSidebar>` (componente chrome
 * persistente, montado por `App.tsx` en TODAS las rutas authed). El
 * `HUB_CARDS` exportado acá sigue siendo la fuente de verdad de los
 * 8 items del sidebar — `App.tsx` lo consume y le pasa a
 * `<AppSidebar items={HUB_CARDS} permisos={...} />`.
 */
import { lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Banknote,
  Bell,
  BookOpen,
  Building2,
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

export interface HubCard {
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
  labelKey: string;
  descriptionKey: string;
  /** Permission gate mirroring the convention in `lib/admin-sections.ts`:
   *  `null` = any admin; string = required permission in `permisos[]`.
   *  `AppSidebar` filters by this when rendering.
   *
   *  Notas de auditoría (las 4 que NO están en admin-sections.ts son
   *  inferidas del comportamiento actual del backend; cualquier
   *  cambio server-side que agregue `require_permission(...)` a
   *  estas rutas debe reflejarse acá):
   *  - `empresa`:    no permission dep en `api/v1/empresa*` -> null.
   *  - `arqueos`:    no permission dep en `api/v1/arqueo*` -> null.
   *  - `alertas`:    no permission dep en `api/v1/workflows/alerta*` -> null.
   *  - `dian`:       no permission dep en `api/v1/envio-dian*` -> null.
   */
  permission: string | null;
  testId: string;
}

export const HUB_CARDS: readonly HubCard[] = [
  {
    key: 'sucursales',
    path: '/seleccionar-sucursal',
    icon: Building2,
    labelKey: 'homeHub.sucursales.label',
    descriptionKey: 'homeHub.sucursales.description',
    permission: null,
    testId: 'home-hub-card-sucursales',
  },
  {
    key: 'catalogos',
    path: '/catalogos',
    icon: FolderTree,
    labelKey: 'homeHub.catalogos.label',
    descriptionKey: 'homeHub.catalogos.description',
    permission: 'config_catalogo',
    testId: 'home-hub-card-catalogos',
  },
  {
    key: 'empresa',
    path: '/empresa',
    icon: Landmark,
    labelKey: 'homeHub.empresa.label',
    descriptionKey: 'homeHub.empresa.description',
    permission: null,
    testId: 'home-hub-card-empresa',
  },
  {
    key: 'usuarios',
    path: '/usuarios',
    icon: Users,
    labelKey: 'homeHub.usuarios.label',
    descriptionKey: 'homeHub.usuarios.description',
    permission: null,
    testId: 'home-hub-card-usuarios',
  },
  {
    key: 'arqueos',
    path: '/arqueos',
    icon: Banknote,
    labelKey: 'homeHub.arqueos.label',
    descriptionKey: 'homeHub.arqueos.description',
    permission: null,
    testId: 'home-hub-card-arqueos',
  },
  {
    key: 'alertas',
    path: '/alertas',
    icon: Bell,
    labelKey: 'homeHub.alertas.label',
    descriptionKey: 'homeHub.alertas.description',
    permission: null,
    testId: 'home-hub-card-alertas',
  },
  {
    key: 'dian',
    path: '/dian',
    icon: Send,
    labelKey: 'homeHub.dian.label',
    descriptionKey: 'homeHub.dian.description',
    permission: null,
    testId: 'home-hub-card-dian',
  },
  {
    key: 'auditoria',
    path: '/auditoria/log',
    icon: BookOpen,
    labelKey: 'homeHub.auditoria.label',
    descriptionKey: 'homeHub.auditoria.description',
    permission: 'audit_read',
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

      {/* Single-column main content. The persistent left nav lives in
          `<AppSidebar>` (mounted by `App.tsx`); the cross-branch KPIs
          and charts fill the main column to the right of it. */}
      <main className="flex min-w-0 flex-col gap-6">
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
    </div>
  );
}
