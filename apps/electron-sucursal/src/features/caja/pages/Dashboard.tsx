/**
 * `<Dashboard />` — kiosk workspace (F3.3 + REQ-OPS-136/137/138/139).
 *
 * Layout (single screen, no scroll at 1080p height):
 *
 *   ┌────────────────────────────────────────────────────────────────────┐
 *   │ Header: operador + "Dentro: N" + F1-F6 chips + Cerrar sesión   │
 *   ├──────────┬───────────────────────────────────┬──────────────────┤
 *   │ Sidebar  │ Center:                           │ Sidebar:         │
 *   │ 200px    │  PLACA DEL VEHICULO               │  300px           │
 *   │          │  [giant ABC123 input]              │                  │
 *   │ 7 action │    placa hint (contextual)         │  AUTOS 5         │
 *   │ buttons  │                                   │  MOTOS 4         │
 *   │ → drawers│  Vehículos dentro                 │                  │
 *   │ + tooltips                                   │  VEHICULOS LIST  │
 *   │ (help +   │                                   │  COBROS PEND.    │
 *   │  hotkey)  │                                   │                  │
 *   └──────────┴───────────────────────────────────┴──────────────────┘
 *
 * Hotkeys (F1-F6) open the matching side-panel drawer via the
 * `useDashboardDrawerStore` Zustand singleton (REQ-OPS-138 single-drawer
 * invariant). Esc closes any active drawer.
 *
 * The PlacaInputHero (center column) is the primary action surface.
 * Pressing Enter on a typed plate opens the matching drawer with the
 * plate pre-filled (REQ-OPS-136 smart routing):
 *   - plate already has an active ingreso in this branch → `salida`
 *   - otherwise → `ingreso`
 *
 * Sections previously listed in 2-col grid (REQ-OPS-136 PR-1..PR-6) are
 * now collapsed into:
 *   - Top header bar (operador + status + cerrar)
 *   - Left sidebar (5 navigation actions)
 *   - Placa input hero (the operator's only primary action during the turn)
 *   - Right sidebar (live counts + active vehicles + pending cobros)
 *   - DrawerHost (single-drawer mounted for: IngresoSheet, SalidaSheet,
 *     PagoSheet, ReimprimirTiqueteSheet, ArqueoSheet, CierreDiarioDialog —
 *     triggered by sidebar, hotkey, OR the PlacaInputHero)
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Car,
  Flag,
  CreditCard,
  Wallet,
  ClipboardList,
  Package,
  Receipt,
} from 'lucide-react';

import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';
import { useAuth } from '@parkos/ui-kit/hooks';

import { useSesionActiva } from '../hooks/useSesionActiva';
import { MiTurnoPanel } from '../../operacion/components/MiTurnoPanel';
import { OcupacionPanel } from '../components/OcupacionPanel';
import { FacturaElectronicaRetryPanel } from '../../facturacion/components/FacturaElectronicaRetryPanel';
import { SuscripcionesPanel } from '../../suscripciones/components/SuscripcionesPanel';
import { SyncStatusStrip } from '../../sync/components/SyncStatusStrip';
import { AlertasPanel } from '../../../components/AlertasPanel';
import { useIngresoActivo } from '../../operacion/hooks/useIngresoActivo';
import { getIngresosByPlaca } from '../../operacion/api/ingresoActivoApi';
import { useSuscripcionesProximasVencer } from '../../suscripciones/hooks/useSuscripcionesProximasVencer';
import { formatHoraCorta } from '../lib/format';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { TurnoActivoToggle } from '../components/TurnoActivoToggle';

import { DrawerHost } from './DrawerHost';
import { useDashboardDrawerStore, type DrawerKind } from '@/store/dashboardDrawerStore';

const DRAWER_BY_HOTKEY: Record<string, DrawerKind> = {
  F1: 'ingreso',
  F2: 'salida',
  F3: 'suscripciones',
  F4: 'arqueo',
  F5: 'inventario',
  F6: 'cierre-diario',
};

export function Dashboard(): JSX.Element | null {
  const { sesion, isLoading, error, refresh } = useSesionActiva();
  const { isAuthenticated, isLoading: isAuthLoading, sucursal, user } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation(['caja', 'common', 'operacion', 'suscripciones']);
  const uuid_sucursal = sucursal?.uuid ?? null;
  const openDrawer = useDashboardDrawerStore((s) => s.open);
  const closeDrawer = useDashboardDrawerStore((s) => s.close);
  const openDrawerKind = useDashboardDrawerStore((s) => s.openDrawer);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // HU-F9.2 (REQ-OPS-183) — banner + top-5 panel de suscripciones
  // próximas a vencer en la sede. El hook aplica el filtro
  // `dias >= 0` (excluye vencidas) y ordena por `fecha_vencimiento`
  // ASC, así que `data[0]` es la suscripción MÁS próxima a vencer
  // y `data.slice(0, 5)` es el top 5 de la pantalla. El
  // ABIRTO-05/REQ-OPS-184 (override per-suscripción) NO está
  // implementado en este PR — default global `7 días` via
  // `DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO` en `lib/constants.ts`.
  const { data: suscripcionesPorVencer } =
    useSuscripcionesProximasVencer(uuid_sucursal);
  const topVencer = suscripcionesPorVencer?.slice(0, 5) ?? [];
  const totalVencer = suscripcionesPorVencer?.length ?? 0;
  const firstVencer = suscripcionesPorVencer?.[0];

  const bannerText = firstVencer
    ? t('suscripciones:dashboard.bannerVencimiento', {
        dias: firstVencer.dias_para_vencer,
        fecha: firstVencer.fecha_vencimiento,
        defaultValue:
          'Suscripción de esta placa vence en X días (fecha). Considere renovación.',
      })
    : null;

  // F1-F6 hotkey listener → openDrawer + Esc closes.
  // Every drawer mounts via <DrawerHost /> on the dashboard — none of
  // the F-keys navigate to a route. F4 (arqueo) shares the pattern:
  // global hotkey opens the right-side arqueo drawer, the dashboard
  // route stays at `/`. F11.3 (the old REQ-OPS-152 routed-page path
  // for arqueo was removed: the F10.1 experience is drawer-only per
  // the user's UX direction so F4 hotkey + sidebar anchor + hotkey
  // chip all share the same code path).
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        if (openDrawerKind !== null) {
          closeDrawer();
        }
        return;
      }
      const target = DRAWER_BY_HOTKEY[e.key];
      if (target !== undefined) {
        e.preventDefault();
        // Anchor id is empty for hotkey-driven opens — focus restore
        // is a no-op when the trigger is the global F-key listener.
        openDrawer(target, '');
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [openDrawerKind, openDrawer, closeDrawer]);

  useEffect(() => {
    if (isAuthLoading) return;
    if (!isAuthenticated) {
      navigate('/login', { replace: true });
      return;
    }
    if (!sesion && !isLoading && !error) {
      navigate('/caja/abrir-turno', { replace: true });
    }
  }, [isAuthenticated, isAuthLoading, sesion, isLoading, error, navigate]);

  if (isLoading) {
    return <Skeleton className="h-screen w-full" data-testid="dashboard-skeleton" />;
  }

  if (error && (error instanceof ParkosHttpError ? error.status !== 404 : true)) {
    return (
      <div data-testid="dashboard-error">
        <p role="alert">{t('common:error')}</p>
        <Button onClick={() => void refresh()} data-testid="dashboard-retry">
          {t('common:retry')}
        </Button>
      </div>
    );
  }

  if (sesion) {
    const operadorLabel =
      user?.email.split('@')[0] ?? t('common:operador', { defaultValue: 'Operador' });
    const sucursalLabel = sucursal?.prefijo_nombre ?? 'BOG-CEN';

    return (
      <div
        className="grid min-h-[calc(100vh-2.5rem)] w-full grid-rows-[auto_1fr] grid-cols-1 lg:grid-cols-[180px_1fr_280px]"
        data-testid="dashboard-hub"
      >
        {/* ── Top header bar (mobile-first: minimum on mobile, full on lg+) ── */}
        <header className="col-span-1 lg:col-span-3 flex flex-wrap items-center gap-2 border-b border-border/40 bg-card/80 px-4 py-2.5 backdrop-blur-md shadow-apple-sm md:gap-3 md:px-5">
          {/* Hamburger — only on small screens (below lg). */}
          <button
            type="button"
            data-testid="dashboard-hamburger"
            aria-expanded={mobileNavOpen}
            aria-controls="dashboard-sidebar-nav"
            aria-label={t('common:menu', { defaultValue: 'Menu' })}
            onClick={() => setMobileNavOpen((v) => !v)}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-border bg-background text-sm hover:bg-accent lg:hidden"
          >
            {mobileNavOpen ? '✕' : '☰'}
          </button>

          {/* Operador + sucursal — only on md+ (avoid header bloat on mobile). */}
          <div className="hidden items-baseline gap-2 md:flex">
            <strong data-testid="operador-name">{operadorLabel}</strong>
            <span className="text-xs text-muted-foreground" data-testid="operador-sucursal">
              {sucursalLabel} — {t('common:administrador', { defaultValue: 'Administrador' })}
            </span>
          </div>

          {/* Online status — only on lg+ (avoid clutter on mobile). */}
          <span
            data-testid="dashboard-online"
            className="ml-auto hidden items-center gap-1.5 rounded-full border border-emerald-200/60 bg-emerald-50/80 px-3 py-1 text-xs font-medium text-emerald-700 shadow-apple-sm lg:inline-flex"
          >
            <span aria-hidden className="h-2 w-2 rounded-full bg-emerald-500" />
            {t('common:online', { defaultValue: 'Online' })}
          </span>

          {/* F1-F6 hotkey chips — only on md+ (mobile users use on-screen buttons). */}
          <span className="hidden gap-1 md:inline-flex">
            {Object.entries(DRAWER_BY_HOTKEY).map(([key, kind]) => (
              <kbd
                key={key}
                data-testid={`hotkey-${kind}`}
                id={`hotkey-chip-${kind}`}
                className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md border border-border/60 bg-background/80 px-2 font-mono text-[11px] font-semibold text-muted-foreground backdrop-blur-sm hover:bg-accent/60 hover:text-foreground"
                onClick={() => {
                  // Every F-key chip opens the matching drawer; the
                  // dashboard route stays at `/`. F4 (arqueo) shares
                  // the same pattern as F1/F2/F3 (the F10.1 routed
                  // page was retired in F11.3 per UX direction).
                  openDrawer(kind, `hotkey-chip-${kind}`);
                }}
              >
                {key}
              </kbd>
            ))}
          </span>

          {/* Turno chip + Cerrar turno — always visible (mobile + desktop). */}
          <TurnoActivoToggle sesion={sesion} />
          <Button
            variant="default"
            size="sm"
            data-testid="dashboard-cerrar-turno"
            onClick={() => openDrawer('cerrar-turno', 'dashboard-cerrar-turno')}
            className="shrink-0"
          >
            {t('caja:cerrarTurnoLabel')}
          </Button>
        </header>

        {/* ── Left sidebar nav ──────────────────────────────────────────── */}
        {/* TooltipProvider lives at the sidebar root so each action button
            shows its own contextual help (purpose + hotkey) at the moment
            the operator is about to click it. Replaces the legacy
            `welcome-card` list which was read-once-then-forgotten.
            Radix Tooltip shows on hover AND focus, so touch + keyboard +
            kiosko (mouse-less) are all covered. `side="right"` keeps the
            popover inside the viewport regardless of sidebar position. */}
        <TooltipProvider delayDuration={150}>
          <nav
            id="dashboard-sidebar-nav"
            aria-label={t('caja:dashboard.navLabel', { defaultValue: 'Acciones rápidas' })}
            className={
              // Mobile: drawer-style overlay (when hamburger open) OR hidden.
              // lg+: static sidebar in the grid (col-start-1 row-start-2).
              'flex flex-col gap-1 overflow-y-auto border-r border-border/40 bg-card/40 p-2 ' +
              'lg:row-start-2 lg:col-start-1 ' +
              (mobileNavOpen
                ? 'fixed inset-y-0 left-0 z-40 w-64 border-r shadow-apple-lg'
                : 'hidden lg:flex')
            }
          >
            {/* Ingreso + Salida — acciones CORE del kiosko. Los drawers
                `ingreso`/`salida` ya están cableados en DrawerHost
                (F6.1/F7.1) y los hotkeys F1/F2 los abren desde header;
                este anchor del sidebar los expone como botón trigger
                para kioskos sin teclado o cuando el header está
                colapsado en mobile. */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  data-testid="sidebar-ingreso"
                  className="h-11 justify-start gap-3 rounded-xl px-3 text-sm font-medium text-foreground/80 hover:bg-accent/70 hover:text-foreground transition-colors"
                  onClick={() => {
                    openDrawer('ingreso', 'sidebar-ingreso');
                    setMobileNavOpen(false);
                  }}
                >
                  <Car className="h-4 w-4 shrink-0" />
                  <span>{t('operacion:ingreso', { defaultValue: 'Ingreso' })}</span>
                  <kbd className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">F1</kbd>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                {t('caja:dashboard.help.ingreso')}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  data-testid="sidebar-salida"
                  className="h-11 justify-start gap-3 rounded-xl px-3 text-sm font-medium text-foreground/80 hover:bg-accent/70 hover:text-foreground transition-colors"
                  onClick={() => {
                    openDrawer('salida', 'sidebar-salida');
                    setMobileNavOpen(false);
                  }}
                >
                  <Flag className="h-4 w-4 shrink-0" />
                  <span>{t('operacion:salida', { defaultValue: 'Salida' })}</span>
                  <kbd className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">F2</kbd>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                {t('caja:dashboard.help.salida')}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  data-testid="sidebar-suscripciones"
                  className="h-11 justify-start gap-3 rounded-xl px-3 text-sm font-medium text-foreground/80 hover:bg-accent/70 hover:text-foreground transition-colors"
                  onClick={() => {
                    openDrawer('suscripciones', 'sidebar-suscripciones');
                    setMobileNavOpen(false);
                  }}
                >
                  <CreditCard className="h-4 w-4 shrink-0" />
                  <span>{t('suscripciones:menu', { defaultValue: 'Suscripción' })}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                {t('caja:dashboard.help.suscripciones')}
              </TooltipContent>
            </Tooltip>
            {/* HU-F10.1 — Arqueo (EP-13) en el sidebar izquierdo.
                F11.3 había movido esto al right-sidebar MiTurnoPanel
                como "single source of truth" del per-turn action
                surface. Revierto esa decisión por directiva del
                operador: el botón de hacer arqueo debe estar en el
                menú izquierdo, accesible con el atajo F4 (igual que
                el resto del sidebar). El anchor del right-sidebar
                (ArqueoButton dentro de MiTurnoPanel) sigue
                existiendo como atajo contextual del turno abierto. */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  data-testid="sidebar-arqueo"
                  className="h-11 justify-start gap-3 rounded-xl px-3 text-sm font-medium text-foreground/80 hover:bg-accent/70 hover:text-foreground transition-colors"
                  onClick={() => {
                    openDrawer('arqueo', 'sidebar-arqueo');
                    setMobileNavOpen(false);
                  }}
                >
                  <Wallet className="h-4 w-4 shrink-0" />
                  <span>{t('caja:arqueoLabel', { defaultValue: 'Arqueo' })}</span>
                  <kbd className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">F4</kbd>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                {t('caja:dashboard.help.arqueo')}
              </TooltipContent>
            </Tooltip>
            {/* "Cerrar turno" is intentionally NOT in the left sidebar.
                The header button (data-testid="dashboard-cerrar-turno")
                is the canonical single-source-of-truth for the
                turn-closing entry-point — duplicating it in the sidebar
                made the kiosk surface ambiguous. */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  data-testid="sidebar-cierre-diario"
                  className="h-11 justify-start gap-3 rounded-xl px-3 text-sm font-medium text-foreground/80 hover:bg-accent/70 hover:text-foreground transition-colors"
                  onClick={() => {
                    // HU-F10.3 (REQ-OPS-164 + AD-2) — sidebar anchor
                    // navigates to the routed page (mirrors the F10.1/F10.2
                    // sidebar anchors). The F8.x `CierreDiarioDialog` drawer
                    // (per-session quick close) remains accessible via the
                    // DrawerHost but the canonical entry-point for the
                    // multi-session daily reconciliation is this routed
                    // page.
                    navigate('/caja/cierre-diario');
                    setMobileNavOpen(false);
                  }}
                >
                  <ClipboardList className="h-4 w-4 shrink-0" />
                  <span>{t('caja:cierreDiario.titulo', { defaultValue: 'Cierre diario' })}</span>
                  <kbd className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">F6</kbd>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                {t('caja:dashboard.help.cierre')}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  data-testid="sidebar-inventario"
                  className="h-11 justify-start gap-3 rounded-xl px-3 text-sm font-medium text-foreground/80 hover:bg-accent/70 hover:text-foreground transition-colors"
                  onClick={() => {
                    openDrawer('inventario', 'sidebar-inventario');
                    setMobileNavOpen(false);
                  }}
                >
                  <Package className="h-4 w-4 shrink-0" />
                  <span>{t('caja:dashboard.inventario', { defaultValue: 'Inventario' })}</span>
                  <kbd className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">F5</kbd>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                {t('caja:dashboard.help.inventario')}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  data-testid="sidebar-facturas"
                  className="h-11 justify-start gap-3 rounded-xl px-3 text-sm font-medium text-foreground/80 hover:bg-accent/70 hover:text-foreground transition-colors"
                  onClick={() => {
                    openDrawer('reimpresion', 'sidebar-facturas');
                    setMobileNavOpen(false);
                  }}
                >
                  <Receipt className="h-4 w-4 shrink-0" />
                  <span>{t('caja:dashboard.facturas', { defaultValue: 'Facturas' })}</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                {t('caja:dashboard.help.facturas')}
              </TooltipContent>
            </Tooltip>
          </nav>
        </TooltipProvider>

        {/* Backdrop overlay for mobile sidebar. Click to close. */}
        {mobileNavOpen && (
          <button
            type="button"
            aria-label={t('common:cerrar', { defaultValue: 'Cerrar menú' })}
            onClick={() => setMobileNavOpen(false)}
            className="fixed inset-0 z-30 bg-black/40 lg:hidden"
          />
        )}

        {/* ── Center: placa hero + welcome ─────────────────────────────── */}
        <main
          lang="es-CO"
          className="row-start-2 col-start-1 flex flex-col gap-3 overflow-y-auto p-3 lg:col-start-2 lg:p-3"
        >
          {/*
            HU-F9.2 banner literal (REQ-OPS-183) — inline amarillo
            renderiza SOLO cuando hay al menos una suscripción por
            vencer. El texto es literal canónico de plan.md:2100;
            `dias` y `fecha` se interpolan del PRIMER item del array
            (que el hook ya ordena por `fecha_vencimiento` ASC).
          */}
          {bannerText !== null && (
            <div
              data-testid="dashboard-vencimiento-banner"
              role="alert"
              className="rounded-2xl border border-amber-200/60 bg-amber-50/80 px-4 py-2.5 text-sm text-amber-900 shadow-apple-sm"
            >
              <span aria-hidden className="mr-2 font-semibold">
                ⚠
              </span>
              {bannerText}
            </div>
          )}

          <Card data-testid="placa-card">
            <CardHeader className="px-5 pt-5 pb-3">
              <CardTitle className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
                {t('caja:dashboard.placaLabel', { defaultValue: 'Placa del vehículo' })}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {/* The placa input hero — autofocus on mount, ABC123 placeholder. */}
              <PlacaInputHero uuid_sucursal={uuid_sucursal} />
              {/*
                Hint contextual debajo del input — antes vivía en la
                `welcome-card` (read-once-then-forgotten). Acá vive al
                lado del objeto que describe: el operador ve la ayuda
                mientras tipea, no en otra zona de la pantalla.
              */}
              <p
                className="mt-3 text-center text-sm text-muted-foreground/80 leading-relaxed"
                data-testid="placa-card-hint"
              >
                {t('caja:dashboard.placaHint', {
                  defaultValue:
                    'Digita la placa y presioná Enter. El sistema abre automáticamente el panel correspondiente.',
                })}
              </p>
            </CardContent>
          </Card>

          {/*
            Vehículos dentro — directiva del operador: debe vivir debajo
            del panel central de placa del vehículo (no en el right-sidebar).
            Mismo data-testid y mismo render para no romper tests / SWR /
            anchor de axe-core que ya apuntan a `vehiculos-list-card` y
            `vehiculos-list`. (F11.x direct layout — sin cambio de data
            ni de polling cadence; sigue siendo 10s vía useIngresosActivos.)
          */}
          <Card data-testid="vehiculos-list-card" className="overflow-hidden">
            <CardHeader className="px-5 pt-5 pb-3">
              <CardTitle className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
                {t('caja:dashboard.vehiculosDentro', { defaultValue: 'Vehículos dentro' })}
              </CardTitle>
            </CardHeader>
            <CardContent className="px-3 pb-3 text-sm">
              <VehiculosDentroList uuid_sucursal={uuid_sucursal} />
            </CardContent>
          </Card>

          {/* Hidden: legacy section panels for compatibility with the F4.4
              `OcupacionStrip` removal. The ingreso/salida panels now live
              inside DrawerHost (via IngresoSheet / SalidaSheet) so they
              no longer need an `sr-only` anchor here. The remaining
              panels stay because they are referenced by tests via
              `data-testid="dashboard-section-..."`. */}
          <div aria-hidden className="sr-only">
            <section data-testid="dashboard-section-suscripciones">
              <SuscripcionesPanel uuid_sucursal={uuid_sucursal} />
            </section>
          </div>
          <div aria-hidden className="sr-only">
            <section data-testid="dashboard-section-sync">
              <SyncStatusStrip uuid_sucursal={uuid_sucursal} />
            </section>
          </div>
          <div aria-hidden className="sr-only">
            <section data-testid="dashboard-section-alertas">
              <AlertasPanel uuid_sucursal={uuid_sucursal} />
            </section>
          </div>
          <div aria-hidden className="sr-only">
            <section data-testid="dashboard-section-fe-retry">
              <FacturaElectronicaRetryPanel uuid_fe={null} />
            </section>
          </div>
        </main>

        {/* ── Right sidebar: counts + lists (responsive) ──────────────────── */}
        {/*
          - lg+ (>= 1024px): fixed right sidebar in the grid (col 3).
          - < lg: stacked at the bottom of the page (below the main column).
          - < md: each card spans full width; md+: 2-col grid for the lists.
        */}
        <aside
          aria-label={t('caja:dashboard.rightLabel', { defaultValue: 'Estado en vivo' })}
          className="col-span-1 mt-3 grid gap-3 px-3 pb-4 lg:row-start-2 lg:col-start-3 lg:mt-0 lg:border-l lg:border-border/40 lg:bg-card/30 lg:px-4 lg:pb-4"
        >
          {/*
            HU-F12.1 (REQ-OPS-187) — per-turn widget mounted ABOVE
            <OcupacionPanel /> (the Inventario card below). The panel
            polls `/operacion/mi-turno?uuid_sesion=X` every 15s via SWR
            and renders a vertical LIST with 3 rows (ingresos en mi
            turno / salidas en mi turno / cupos libres en la sucursal)
            — directiva 2026-09-22: NO dinero (totalCobrado/efectivo/
            datafono), diseño tipo lista, no KPI cards en grid.
            `uuid_sucursal` se pasa para que el panel agregue los
            cupos libres via `useOcupacion` (sum de `disponible`).
            Zero-state (no sesion / loading) renderiza 0s sin skeleton.
          */}
          <MiTurnoPanel
            uuid_sesion={sesion?.uuid ?? null}
            uuid_sucursal={uuid_sucursal}
          />

          {/* Inventario: per-tipo occupancy (admin-configured cupos only). */}
          <Card data-testid="inventario-card">
            <CardHeader className="px-5 pt-4 pb-3">
              <CardTitle className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
                {t('caja:dashboard.inventario', { defaultValue: 'Inventario' })}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 px-3 pb-4">
              <OcupacionPanel uuid_sucursal={uuid_sucursal} />
            </CardContent>
          </Card>

          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-1">
            <Card data-testid="cobros-list-card" className="overflow-hidden">
              <CardHeader className="px-5 pt-4 pb-3">
                <CardTitle className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
                  {t('caja:dashboard.cobrosPendientes', { defaultValue: 'Cobros pendientes' })}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 overflow-y-auto px-3 pb-4 text-sm">
                <p className="text-muted-foreground/70 text-sm" data-testid="cobros-empty">
                  {t('caja:dashboard.sinCobros', { defaultValue: 'Sin cobros pendientes.' })}
                </p>
              </CardContent>
            </Card>
          </div>

          {/*
            HU-F9.2 panel "Suscripciones por vencer" (REQ-OPS-183).
            Muestra el TOTAL (`totalVencer`) y los primeros 5 items
            del array ordenado por `fecha_vencimiento` ASC que devuelve
            el hook `useSuscripcionesProximasVencer`.
          */}
          <Card data-testid="dashboard-vencimiento-panel" className="overflow-hidden">
            <CardHeader className="px-5 pt-4 pb-3">
              <CardTitle className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
                {t('suscripciones:dashboard.panelVencimiento.titulo', {
                  defaultValue: 'Suscripciones por vencer',
                })}{' '}
                <span data-testid="dashboard-vencimiento-panel-count">
                  ({totalVencer})
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 overflow-y-auto px-3 pb-4 text-sm">
              {topVencer.length === 0 && (
                <p className="text-muted-foreground/70 text-sm" data-testid="dashboard-vencimiento-panel-empty">
                  {t('caja:dashboard.sinCobros', { defaultValue: 'Sin suscripciones por vencer.' })}
                </p>
              )}
              <ul className="space-y-1" data-testid="dashboard-vencimiento-panel-list">
                {topVencer.map((it) => (
                  <li
                    key={it.uuid}
                    className="flex items-center justify-between rounded-xl px-3 py-2 hover:bg-accent/40 transition-colors"
                    data-testid={`dashboard-vencimiento-item-${it.placa}`}
                  >
                    <span className="font-mono text-sm font-medium uppercase tracking-wide">{it.placa}</span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {t('suscripciones:dashboard.panelVencimiento.diasRestantesMuchos', {
                        dias: it.dias_para_vencer,
                        defaultValue: `vence en ${it.dias_para_vencer} días`,
                      })}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </aside>

        {/* ── DrawerHost mounts the SINGLE active drawer (REQ-OPS-138) ─── */}
        <DrawerHost />
      </div>
    );
  }

  return null;
}

// ── Sub-components ───────────────────────────────────────────────────────

function PlacaInputHero({
  uuid_sucursal: _uuid_sucursal,
}: {
  uuid_sucursal: string | null;
}): JSX.Element {
  const { t } = useTranslation('caja');
  const openDrawer = useDashboardDrawerStore((s) => s.open);

  // Controlled input so the typed plate can drive `useIngresoActivo`
  // and be passed to the drawer (REQ-OPS-136 smart routing).
  const [value, setValue] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const normalized = value.trim().toUpperCase().replace(/\s+/g, '');
  // Only probe for an active ingreso once the typed plate is at least
  // 5 chars and shaped like a vehicle plate — avoids spamming SWR for
  // every keystroke and false-positives on prefixes that can't match
  // either regex yet.
  const probePlaca = normalized.length >= 5 ? normalized : null;
  const { latestIngreso } = useIngresoActivo(probePlaca);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>): void {
    setValue(e.target.value.toUpperCase().replace(/\s+/g, '').slice(0, 6));
  }

  // REGRESSION fix (2026-09-22, directiva del operador): el smart
  // routing dependía SOLO del SWR cache (`useIngresoActivo` →
  // `latestIngreso`). El fetch SWR tarda ~50-200ms; cuando el operador
  // tipea una placa existente y presiona Enter rápidamente, el fetch
  // todavía no terminó → `latestIngreso` es `null` → abre
  // incorrectamente el IngresoSheet para una placa que YA está dentro
  // (debería abrir SalidaSheet). El bug bloquea el flujo de salida con
  // cálculo de tiempo/valor que el operador pidió garantizar.
  //
  // Fix: en el handler de Enter, hacer un await directo contra
  // ``getIngresosByPlaca(placa)`` — esa función es el mismo endpoint
  // (``GET /api/v1/operacion/ingresos?placa=X``) que el SWR consume,
  // pero awaited en línea. La decisión es ahora síncrona respecto al
  // resultado del fetch, no respecto al estado del cache SWR. El
  // SWR cache (``useIngresoActivo``) sigue alimentando el hint visual
  // inline mientras el operador tipea (live, best-effort), pero NO
  // es la fuente de verdad para la decisión.
  async function onKeyDown(
    e: React.KeyboardEvent<HTMLInputElement>,
  ): Promise<void> {
    if (e.key !== 'Enter') return;
    const placa = value.trim();
    if (placa === '') return;
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      // Fetch directo bloqueante para que la decisión sea autoritativa
      // (no race contra el SWR cache). Reutiliza el mismo endpoint que
      // ``useIngresoActivo`` — solo cambia el modo (await inline vs
      // SWR background poll).
      const rows = await getIngresosByPlaca(placa);
      if (rows.length > 0) {
        // Smart routing per plan.md §CU-02: plate already has an active
        // ingreso → open the salida drawer. ``SalidaSheet`` will mount
        // inside the DrawerHost and ``SalidaPanel`` will fetch the
        // cotizacion (tiempo + valor) via ``useCotizacion`` —
        // guaranteed to work thanks to the migration 0046 COALESCE fix
        // on the backend.
        openDrawer('salida', 'placa-hero-input', placa);
      } else {
        // Smart routing per plan.md §CU-02: plate has NO active ingreso
        // → open the ingreso drawer. ``IngresoSheet`` pre-fills the
        // placa so the operator only has to click "Registrar".
        openDrawer('ingreso', 'placa-hero-input', placa);
      }
      setValue('');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-1">
      <input
        type="text"
        autoFocus
        data-testid="placa-hero-input"
        id="placa-hero-input"
        placeholder="ABC123"
        value={value}
        onChange={handleChange}
        maxLength={6}
        disabled={submitting}
        className="block w-full rounded-2xl border-0 bg-muted/50 px-4 py-6 text-center font-mono text-6xl uppercase tracking-[0.4em] outline-none placeholder:text-muted-foreground/40 focus-ring-apple focus-visible:bg-background focus-visible:shadow-apple transition-all disabled:opacity-60"
        onKeyDown={onKeyDown}
        aria-label={t('caja:dashboard.placaLabel', { defaultValue: 'Placa del vehículo' })}
        // uuid_sucursal is consumed by IngresoPanel inside the drawer; this
        // hero input is the entry-point keyboard handler.
        data-uuid-sucursal={_uuid_sucursal ?? ''}
      />
      {/* REGRESSION fix (2026-09-22): inline visual hint when the typed
          plate already has an active ingreso. The SWR-fed
          ``latestIngreso`` is best-effort (it can lag the operator's
          keystrokes) — the actual decision on Enter uses a direct
          fetch — but the hint helps the operator confirm "yes, this
          plate is already inside" before pressing Enter. Without this
          hint the operator might press Enter expecting "ingreso" and
          be surprised when SalidaSheet opens instead. The hint is
          intentionally subtle (text-muted-foreground) — primary
          feedback comes from the drawer mount itself. */}
      {latestIngreso && (
        <p
          data-testid="placa-hero-active-hint"
          className="text-center text-xs text-muted-foreground"
          role="status"
        >
          {t('caja:dashboard.placaActiveHint', {
            defaultValue: 'Esta placa ya está dentro — presioná Enter para cobrar la salida.',
          })}
        </p>
      )}
    </div>
  );
}

// ── Inline SWR-style hook for active ingresos list (per placa) ───────
//
// `GET /api/v1/operacion/ingresos?uuid_sucursal=X` returns currently-active
// ingresos (timestamp_salida IS NULL). The oficial hook `useIngresoActivo`
// is for ONE placa; this one lists ALL currently-occupied plates.
//
// Refresh cadence: 10s (same as <OcupacionPanel />) so the two stay in sync.
//
// Robust to React StrictMode (effects run twice in dev): the return value
// is always either `null` (loading/error) or an array (possibly empty).
// Never returns `undefined` so the consumer's `items.length` is always safe.
const INGRESOS_REFRESH_MS = 10_000;

function useIngresosActivos(
  uuid_sucursal: string | null,
): IngresoActivo[] | null {
  const [items, setItems] = useState<IngresoActivo[] | null>(null);

  useEffect(() => {
    if (uuid_sucursal === null) {
      setItems([]);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function pull(): Promise<void> {
      try {
        // Endpoint returns IngresoActivo[] DIRECTLY (not wrapped in
        // { items: ... } as many list endpoints do). Coerce defensively
        // in case the backend shape changes.
        const json = (await parkosFetch<unknown>(
          `/api/v1/operacion/ingresos?uuid_sucursal=${uuid_sucursal}`,
        )) as IngresoActivo[] | { items?: IngresoActivo[] };
        if (cancelled) return;
        const list = Array.isArray(json)
          ? json
          : Array.isArray(json?.items)
            ? json.items
            : [];
        setItems(list);
      } catch {
        if (!cancelled) setItems([]);
      }
    }

    void pull();
    timer = setInterval(() => void pull(), INGRESOS_REFRESH_MS);

    return () => {
      cancelled = true;
      if (timer !== null) clearInterval(timer);
    };
  }, [uuid_sucursal]);

  return items;
}

interface IngresoActivo {
  uuid: string;
  placa: string | null;
  /**
   * Hora del ingreso. El backend puede devolver `null` para filas creadas
   * antes de que el handler populase la columna (seeds / ingresos de
   * pruebas viejos). En ese caso caemos a `created_at`, que SÍ trae
   * timestamp real del INSERT.
   */
  fecha_ingreso: string | null;
  /**
   * Identificador legible para ingresos sin placa (REQ-OPS-197).
   * Formato `<TIPO>-NNNNNN-<uuid8>` (ej. `PATINETA-000003-34a24bae`).
   * `null` para ingresos con placa — esos muestran la placa.
   */
  consecutivo: string | null;
  /** Timestamp del INSERT — fallback cuando `fecha_ingreso` viene null. */
  created_at: string;
  uuid_tipo_vehiculo: string;
  uuid_sucursal: string;
}

/**
 * Opciones de tamaño de página para el listado de vehículos dentro.
 * El operador pidió cap de 5 o 10 registros por vista para que el card
 * no exceda el viewport del kiosko (REQ-UX-F11.PAGINACION).
 */
const PAGE_SIZE_OPTIONS = [5, 10] as const;
type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];

function VehiculosDentroList({
  uuid_sucursal,
}: {
  uuid_sucursal: string | null;
}): JSX.Element {
  const { t } = useTranslation('caja');
  const items = useIngresosActivos(uuid_sucursal);
  // items is IngresoActivo[] | null. null = loading; [] = empty; >0 = lista.
  // Defensive: if the hook ever returned undefined, treat as loading.
  const safe = items ?? null;

  const [pageSize, setPageSize] = useState<PageSize>(10);
  const [currentPage, setCurrentPage] = useState(0);

  // Si cambia el pageSize o los items y la página actual queda fuera de
  // rango, reset a la primera página. Evita que el operador quede en una
  // página vacía después de un cambio de filtro o un corte de ingresos.
  useEffect(() => {
    const total = safe?.length ?? 0;
    const maxPage = Math.max(0, Math.ceil(total / pageSize) - 1);
    if (currentPage > maxPage) {
      setCurrentPage(0);
    }
  }, [safe, pageSize, currentPage]);

  if (safe === null) {
    return (
      <p className="text-muted-foreground" data-testid="vehiculos-loading">
        {t('common:loading')}
      </p>
    );
  }
  if (safe.length === 0) {
    return (
      <p className="text-muted-foreground" data-testid="vehiculos-empty">
        {t('caja:dashboard.sinVehiculos', { defaultValue: 'Sin vehículos dentro.' })}
      </p>
    );
  }

  const totalPages = Math.max(1, Math.ceil(safe.length / pageSize));
  const start = currentPage * pageSize;
  const visible = safe.slice(start, start + pageSize);
  const firstShown = start + 1;
  const lastShown = Math.min(start + pageSize, safe.length);

  return (
    <div className="flex flex-col" data-testid="vehiculos-list-paginated">
      {/*
        Contenedor con altura limitada: el card NUNCA excede el viewport
        del kiosko. `-14rem` reserva el header + panel de placa + chrome
        del card. En viewports chicos el overflow-y-auto absorbe el caso
        límite donde pageSize=10 entra justo pero el alto disponible
        es menor; en viewports normales (>=768px) no aparece scroll.
      */}
      <ul
        className="max-h-[calc(100vh-14rem)] flex-1 divide-y divide-border/40 overflow-y-auto"
        data-testid="vehiculos-list"
      >
        {visible.map((it) => {
          // Identificador visible: placa si existe, sino el consecutivo
          // (REQ-OPS-197, mismo string que se imprime en el tiquete), y
          // como último recurso los primeros 8 chars del uuid.
          const idVisible =
            it.placa ?? it.consecutivo ?? it.uuid.slice(0, 8);
          // Hora del ingreso: canon backend `fecha_ingreso`, con fallback a
          // `created_at` para filas viejas donde la columna quedó null.
          const horaIso = it.fecha_ingreso ?? it.created_at;
          return (
            <li
              key={it.uuid}
              className="group flex items-center justify-between rounded-xl px-3 py-2 hover:bg-accent/40 transition-colors"
              data-testid={`vehiculos-item-${it.uuid}`}
            >
              <span className="font-mono text-sm font-medium uppercase tracking-wide" title={it.uuid}>
                {idVisible}
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">
                {formatHoraCorta(horaIso)}
              </span>
            </li>
          );
        })}
      </ul>

      {/*
        Footer de paginación. Siempre visible cuando hay items — el
        operador puede necesitar cambiar pageSize aunque haya una sola
        página. Mantiene el control cerca de la lista (no en el header)
        para no inflar el CardHeader.
      */}
      <div
        className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border/40 pt-3 text-xs text-muted-foreground"
        data-testid="vehiculos-pagination"
      >
        <span className="tabular-nums" data-testid="vehiculos-pagination-range">
          {firstShown}-{lastShown} de {safe.length}
        </span>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={currentPage === 0}
            onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
            aria-label={t('caja:dashboard.paginaAnterior', {
              defaultValue: 'Página anterior',
            })}
            data-testid="vehiculos-pagination-prev"
            className="h-7 w-7 p-0 rounded-lg"
          >
            ‹
          </Button>
          <span
            className="tabular-nums"
            data-testid="vehiculos-pagination-page"
            aria-label={t('caja:dashboard.paginaActual', {
              defaultValue: `Página ${currentPage + 1} de ${totalPages}`,
              current: currentPage + 1,
              total: totalPages,
            })}
          >
            {currentPage + 1} / {totalPages}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={currentPage >= totalPages - 1}
            onClick={() =>
              setCurrentPage((p) => Math.min(totalPages - 1, p + 1))
            }
            aria-label={t('caja:dashboard.paginaSiguiente', {
              defaultValue: 'Página siguiente',
            })}
            data-testid="vehiculos-pagination-next"
            className="h-7 w-7 p-0 rounded-lg"
          >
            ›
          </Button>
          <span className="ml-2 hidden sm:inline">
            {t('caja:dashboard.porPagina', { defaultValue: 'Por página' })}:
          </span>
          <div
            role="group"
            aria-label={t('caja:dashboard.porPagina', {
              defaultValue: 'Por página',
            })}
            className="inline-flex overflow-hidden rounded-lg border border-border/60"
          >
            {PAGE_SIZE_OPTIONS.map((opt) => {
              const active = pageSize === opt;
              return (
                <button
                  key={opt}
                  type="button"
                  onClick={() => setPageSize(opt)}
                  aria-pressed={active}
                  className={
                    'px-2.5 py-1 text-xs font-semibold ' +
                    (active
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-background hover:bg-accent/60')
                  }
                  data-testid={`vehiculos-pagination-size-${opt}`}
                >
                  {opt}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function CobrosPendientesList({
  uuid_sucursal: _uuid_sucursal,
}: {
  uuid_sucursal: string | null;
}): JSX.Element {
  const { t } = useTranslation('caja');
  return (
    <p className="text-muted-foreground/70 text-sm" data-testid="cobros-empty">
      {t('caja:dashboard.sinCobros', { defaultValue: 'Sin cobros pendientes.' })}
    </p>
  );
}
