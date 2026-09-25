/**
 * `<Dashboard />` — kiosk workspace (F3.3 + REQ-OPS-136/137/138/139).
 *
 * **Layout 2026-09-22 (operador, reorganización visual):**
 *
 *   ┌────────────────────────────────────────────────────────────────────┐
 *   │ Header: operador + F1-F6 chips + TurnoActivoToggle + Cerrar turno  │
 *   ├──────────┬─────────────────────────────────────────────────────────┤
 *   │ Sidebar  │ Center:                                                 │
 *   │ 240px    │  PLACA DEL VEHÍCULO                                     │
 *   │ (+33% vs │  [giant ABC123 input]                                    │
 *   │  versión │    placa hint (contextual)                               │
 *   │  previa) │                                                         │
 *   │ 6 action │  Vehículos dentro                                       │
 *   │ buttons  │   (con cobros pendientes                                │
 *   │ → drawers│    inline si > 0)                                        │
 *   │ + tooltips                                                         │
 *   │ (help +   │                                                         │
 *   │  hotkey)  │                                                         │
 *   ├──────────┴─────────────────────────────────────────────────────────┤
 *   │ Footer full-width: chips compactos por tipo + KPI total libres     │
 *   │ (sticky bottom-0, max-h-[80px] — 2026-09-25: corrección de escala  │
 *   │  tras rechazo del rediseño grande, ver CuposLibresStrip.tsx)       │
 *   └───────────────────────────────────────────────────────────────────┘
 *
 * **Operador 2026-09-22 (segunda iteración):** el right-sidebar de
 * "suscripciones por vencer" se removió del kiosko — el operador lo
 * va a montar en otra parte (drawer propio, otra ruta, o ruta admin).
 * El grid pasa de 3 columnas a 2: `lg:grid-cols-[240px_1fr]`. El
 * main gana el ancho del right-sidebar (≈ 280px → +35% ancho del
 * panel central para la lista de vehículos).
 *
 * El popover del `<TurnoActivoToggle />` (navbar) muestra el resumen
 * del turno abierto: "Ingresos en mi turno" / "Salidas en mi turno"
 * / "Cupos libres en la sucursal". Esos datos vienen de `useMiTurno`
 * + `useOcupacion` (cache compartida con `<CuposLibresStrip />`).
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
 *   - Left sidebar (7 navigation actions)
 *   - Placa input hero (the operator's only primary action during the turn)
 *   - Footer full-width sticky (chips compactos de cupos por tipo + KPI
 *     total, 2026-09-25: escala compacta — ver CuposLibresStrip.tsx)
 *   - DrawerHost (single-drawer mounted for: IngresoSheet, SalidaSheet,
 *     PagoSheet, ReimprimirTiqueteSheet, ArqueoSheet, CierreDiarioDialog —
 *     triggered by sidebar, hotkey, OR the PlacaInputHero)
 *
 * **Cobros pendientes:** se renderizan inline en cada fila de
 * `<VehiculosDentroList />` como una tercera columna a la derecha del
 * identificador del vehículo. La columna sólo aparece si el wire trae
 * `cobros_pendientes > 0` para esa fila. Hoy el endpoint
 * `GET /api/v1/operacion/ingresos` NO devuelve ese campo — la columna
 * queda invisible por default, que matchea exactamente la directiva
 * del operador ("si no hay no deben aparecer"). Cuando se wire-ee el
 * endpoint, queda en follow-up (1 línea: agregar al response shape).
 */
import { useEffect, useId, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Car,
  Flag,
  CreditCard,
  Wallet,
  ClipboardList,
  Receipt,
  LogOut,
} from 'lucide-react';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useAuth } from '@parkos/ui-kit/hooks';

import logoLight from '../../../assets/brand/logos/logo-horizontal-light.svg';
import logoDark from '../../../assets/brand/logos/logo-horizontal-dark--REQUIERE-VECTOR.png';
import { useSesionActiva } from '../hooks/useSesionActiva';
import { CuposLibresStrip } from '../../operacion/components/CuposLibresStrip';
import { FacturaElectronicaRetryPanel } from '../../facturacion/components/FacturaElectronicaRetryPanel';
import { SyncStatusBadge } from '../../sync/components/SyncStatusBadge';
import { AlertasPanel } from '../../../components/AlertasPanel';
import { useIngresoActivo } from '../../operacion/hooks/useIngresoActivo';
import { useIngresosActivos } from '../../operacion/hooks/useIngresosActivos';
import { getIngresosByPlaca } from '../../operacion/api/ingresoActivoApi';
import {
  matchVehiculos,
  vehiculoSuggestionOptionId,
  getNextSuggestionIndex,
  type VehiculoMatch,
} from '../../operacion/lib/vehiculoMatch';
import { VehiculoSuggestions } from '../../operacion/components/VehiculoSuggestions';
import { formatCOP, formatHoraCorta } from '../lib/format';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { TurnoActivoToggle } from '../components/TurnoActivoToggle';
import { ThemeToggle } from '@/components/ThemeToggle';

import { DrawerHost } from './DrawerHost';
import { useDashboardDrawerStore, type NonNullDrawerKind } from '@/store/dashboardDrawerStore';

// `DrawerKind` (the store's state type) includes `null` — "no drawer
// open" — but every literal below is a real drawer, and `open(kind, ...)`
// requires `NonNullDrawerKind`. Typing this map as `Record<string,
// DrawerKind>` let a `null` slip into the inferred value type even
// though no entry is ever `null`, which broke narrowing at both call
// sites below (`target`/`kind` stayed `DrawerKind`, not
// `NonNullDrawerKind`, after the `!== undefined` guard).
const DRAWER_BY_HOTKEY: Record<string, NonNullDrawerKind> = {
  F1: 'ingreso',
  F2: 'salida',
  F3: 'suscripciones',
  F4: 'arqueo',
  F6: 'cierre-diario',
};

export function Dashboard(): JSX.Element | null {
  const { sesion, isLoading, error, refresh } = useSesionActiva();
  const { isAuthenticated, isLoading: isAuthLoading, sucursal, user } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation(['caja', 'common', 'operacion', 'suscripciones', 'sync']);
  const uuid_sucursal = sucursal?.uuid ?? null;
  const openDrawer = useDashboardDrawerStore((s) => s.open);
  const closeDrawer = useDashboardDrawerStore((s) => s.close);
  const openDrawerKind = useDashboardDrawerStore((s) => s.openDrawer);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

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
    // 2026-09-25 (pedido operador): antes se derivaba un nombre falso del
    // prefijo del email — `apps/ui-kit useAuth.ts` ya expone `nombre`/
    // `apellido` reales (el backend siempre los mandó, la interfaz TS no
    // los declaraba). El email-prefix queda como último fallback si el
    // operador no tiene nombre cargado en `prod.usuarios`.
    const nombreCompleto = [user?.nombre, user?.apellido].filter(Boolean).join(' ').trim();
    const operadorLabel =
      nombreCompleto !== ''
        ? nombreCompleto
        : (user?.email.split('@')[0] ?? t('common:operador', { defaultValue: 'Operador' }));
    // Idem: `prefijo_nombre` (código corto, ej. "BOG-CEN") ya lo manda el
    // backend (`schemas/auth.py` SucursalItem) — se prefiere sobre el
    // nombre completo de sucursal por ser más corto para el header.
    const sucursalLabel =
      sucursal?.prefijo_nombre ?? sucursal?.nombre ?? t('common:sucursal', { defaultValue: 'Sucursal' });

    // Alto: `h-full` (no un `min-h-[calc(100dvh-...)]` propio) — el padre
    // (`<main>` en App.tsx) ya es `flex-1 min-h-0`, un alto real y acotado
    // al viewport menos StatusBar; heredarlo con `h-full` hace que
    // `grid-rows-[auto_1fr_auto]` funcione de verdad (la fila `1fr` se
    // acota al espacio real, no crece sin límite) y que el
    // `overflow-y-auto` del `<main>` de abajo contenga el scroll ahí,
    // nunca en la página. Ver comentario largo en App.tsx (2026-09-25).
    return (
      <div
        className="grid h-full w-full grid-rows-[auto_1fr_auto] grid-cols-1 md:grid-cols-[240px_1fr]"
        data-testid="dashboard-hub"
      >
        {/* ── Top header bar (mobile-first: minimum on mobile, full on md+).
            REDISEÑO F31.3: el punto de quiebre del sidebar/hamburguesa baja
            de lg (1024) a md (768) — a partir de "Tablet vertical" (ver
            tabla de breakpoints del brief) ya sobra ancho para un sidebar
            fijo de 240px sin apretujar el contenido (240px deja ≥528px
            libres desde 768px en adelante). Antes el header usaba
            `lg:col-span-3` sobre un grid que solo tiene 2 columnas reales
            (`[240px_1fr]`) — bug preexistente inocuo (el navegador crea una
            3ra columna implícita de 0px) que se corrige acá a
            `md:col-span-2`. */}
        <header className="col-span-1 min-w-0 flex flex-wrap items-center gap-2 border-b border-border/40 bg-card/80 px-4 py-2.5 backdrop-blur-md shadow-apple-sm md:col-span-2 md:gap-3 md:px-5 xl:px-6">
          {/* Logo de marca EasyPunto — swap por tema vía `dark:` (clase
              `.dark` en `<html>`, sin necesidad de estado React). El SVG
              real (`logo-horizontal-light.svg`, wordmark blanco) es para
              fondo oscuro; el PNG (`--REQUIERE-VECTOR`, wordmark oscuro)
              es la única variante disponible para fondo claro — ver
              `src/assets/brand/inventory.json` y la decisión del operador
              de usarlo tal cual sin vectorizar. Alto: h-20 (80px) → h-14
              (56px) → h-9 (36px, 2026-09-25, pedido operador: "más
              estético", mismo orden de magnitud que el logo del login).
              Sin achicar en mobile — sigue siendo un piso, no un techo
              responsive. */}
          <img
            src={logoDark}
            alt="EasyPunto"
            className="h-9 w-auto shrink-0 dark:hidden"
          />
          <img
            src={logoLight}
            alt="EasyPunto"
            className="hidden h-9 w-auto shrink-0 dark:block"
          />

          {/* Divisor vertical entre el logo y el bloque operador/sucursal
              — 2026-09-25 (pedido operador): 20px de aire a cada lado
              (`mx-5` = 1.25rem = 20px). Solo visible junto con el bloque
              que separa (`hidden md:block`, igual que `operador-sucursal`
              de abajo — no tiene sentido en mobile donde ese bloque no
              se muestra). */}
          <div className="hidden h-8 w-px shrink-0 bg-border mx-5 md:block" />

          {/* Hamburger — only below md. 44×44 (antes 32×32) para cumplir
              tamaño mínimo de tap target en kiosko táctil. */}
          <button
            type="button"
            data-testid="dashboard-hamburger"
            aria-expanded={mobileNavOpen}
            aria-controls="dashboard-sidebar-nav"
            aria-label={t('common:menu', { defaultValue: 'Menu' })}
            onClick={() => setMobileNavOpen((v) => !v)}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded border border-border bg-background text-base hover:bg-accent md:hidden"
          >
            {mobileNavOpen ? '✕' : '☰'}
          </button>

          {/* Operador + sucursal — only on md+ (avoid header bloat on
              mobile/phablet). 2026-09-25 (pedido operador): simplificado a
              nombre + sucursal apilados (antes "sucursal — Administrador"
              en una sola línea, el rol no aportaba acá) y con más espacio
              real: `flex-1` (no compite con nada más del clúster
              izquierdo — hotkeys removidos, pill Online movido al clúster
              derecho, ver abajo) + texto un escalón más grande para hacer
              juego con el logo. */}
          <div className="hidden min-w-0 flex-1 flex-col leading-tight md:flex">
            <strong className="truncate text-base" data-testid="operador-name">{operadorLabel}</strong>
            <span className="truncate text-sm text-muted-foreground" data-testid="operador-sucursal">
              {sucursalLabel}
            </span>
          </div>

          {/* F1-F6 hotkey chips: removidos del header (2026-09-25, pedido
              explícito del operador) — son redundantes con el badge
              `<kbd>F1</kbd>`..`<kbd>F6</kbd>` que cada botón del sidebar ya
              muestra individualmente (ver más abajo). El listener global de
              teclado (`DRAWER_BY_HOTKEY`, arriba en el archivo) sigue
              funcionando igual — esto solo quita el chip clickeable
              duplicado del header, no la funcionalidad de hotkey en sí. */}

          {/* Turno chip + Cerrar turno — always visible (mobile + desktop),
              ahora ancladas al borde derecho del header (`ml-auto`) en vez
              de flotar pegadas al clúster izquierdo: en pantallas anchas
              (1920/2560/3840/ultrawide) evita que todo el header quede
              apelmazado a la izquierda con un vacío enorme a la derecha.
              `flex-wrap` interno + `justify-end` son la red de seguridad en
              320px, donde el chip de turno (contenido dinámico, fuera de
              alcance) puede no caber junto al botón de cerrar turno. */}
          <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
            {/* Online status — 2026-09-25 (pedido operador): movido del
                clúster central al borde derecho, junto con tema/turno/
                cerrar. `<SyncStatusBadge />` trae su propio
                `ml-auto lg:inline-flex` embebido — envuelto en un `<div>`
                plano para neutralizar ese margen automático dentro de
                este flex (si no, se comería el espacio de lo que sigue).
                Su breakpoint interno (lg=1024) sigue sin ser editable
                desde acá. F11.1 realineado (REQ-OPS-171, AD-3/AD-4/AD-5,
                2026-09-24; re-alineado 2026-09-25). */}
            <div>
              <SyncStatusBadge uuid_sucursal={uuid_sucursal} />
            </div>
            <ThemeToggle />
            <TurnoActivoToggle sesion={sesion} />
            <Button
              variant="default"
              size="sm"
              data-testid="dashboard-cerrar-turno"
              onClick={() => openDrawer('cerrar-turno', 'dashboard-cerrar-turno')}
              aria-label={t('caja:cerrarTurnoLabel')}
              className="h-11 shrink-0 gap-1.5 px-3 sm:px-4"
            >
              <LogOut className="h-4 w-4 sm:hidden" aria-hidden />
              <span className="hidden sm:inline">{t('caja:cerrarTurnoLabel')}</span>
            </Button>
          </div>
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
              // Mobile/tablet chico: drawer-style overlay (when hamburger
              // open) OR hidden. md+: static sidebar in the grid
              // (col-start-1 row-start-2) — ver nota del breakpoint en el
              // <header /> de más arriba (mismo criterio: 768px alcanza
              // para un sidebar de 240px fijo sin apretujar).
              'flex flex-col gap-1 overflow-y-auto border-r border-border/40 bg-card/40 p-2 ' +
              'md:row-start-2 md:col-start-1 ' +
              (mobileNavOpen
                ? 'fixed inset-y-0 left-0 z-40 w-64 border-r shadow-apple-lg'
                : 'hidden md:flex')
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
                  <kbd className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">F3</kbd>
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
            className="fixed inset-0 z-30 bg-black/40 md:hidden"
          />
        )}

        {/* ── Center: placa hero + welcome ─────────────────────────────── */}
        <main
          lang="es-CO"
          className="row-start-2 col-start-1 min-w-0 flex flex-col gap-3 overflow-y-auto p-[clamp(0.75rem,1.5vw,1.5rem)] md:col-start-2"
        >
          {/* `placa-card` — ancho acotado (48rem) hasta 2xl (1536px) para
              que en laptop/desktop no se vea desproporcionado; en pantallas
              grandes (2xl+) el operador pidió que ocupe el ancho completo
              del área central, igual que `vehiculos-list-card` (abajo). El
              input interno escala su tipografía en pasos adicionales para
              esos anchos — ver `PlacaInputHero`, no queda un box gigante
              con texto chico. */}
          <Card data-testid="placa-card" className="mx-auto w-full max-w-3xl 2xl:max-w-none">
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
              no longer need an `sr-only` anchor here. The `sync` section
              anchor was removed in F11.1's navbar realineation — the
              indicator now lives in the header as `<SyncStatusBadge />`
              (real UI, not an sr-only test anchor). The remaining panel
              stays because it is referenced by tests via
              `data-testid="dashboard-section-..."`. */}
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

        {/* ── Footer full-width (operador 2026-09-22): inventario per-tipo + cupos libres agregados ── */}
        <CuposLibresStrip uuid_sucursal={uuid_sucursal} />

        {/* ── DrawerHost mounts the SINGLE active drawer (REQ-OPS-138) ─── */}
        <DrawerHost />
      </div>
    );
  }

  return null;
}

// ── Sub-components ───────────────────────────────────────────────────────

/**
 * Native input chars a typed plate can still contain WITHOUT losing the
 * "pure placa" auto-uppercase/strip-whitespace formatting (HU-F7.1, T5).
 * A consecutivo (`<TIPO>-NNNNNN-<uuid8>`, ej. `PATINETA-000003-34a24bae`)
 * introduces a `-` and lowercase hex — once that shape shows up we STOP
 * forcing the placa transform so the trailing uuid8 fragment survives
 * as typed. Matching itself stays case-insensitive regardless
 * (`matchVehiculos` normalizes both sides).
 */
const PLACA_SHAPE_REGEX = /^[A-Za-z0-9\s]*$/;
/** Generous cap — long enough for a full consecutivo, short of unbounded. */
const PLACA_HERO_MAX_LEN = 30;

function PlacaInputHero({
  uuid_sucursal,
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

  // HU-F7.1 (búsqueda sin placa, T5) — live suggestions sourced from the
  // SAME "vehículos dentro" snapshot `<VehiculosDentroList />` polls
  // (extracted hook, no new endpoint). Placa suggestions always resolve
  // to `salida` (every candidate here is, by construction, active);
  // no-placa (consecutivo) suggestions hand off via `initialUuidIngreso`
  // instead of `initialPlaca` (point 5 of the store contract).
  const items = useIngresosActivos(uuid_sucursal);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [suggestionsClosed, setSuggestionsClosed] = useState(false);
  const listboxId = useId();
  const candidates = useMemo(() => matchVehiculos(items ?? [], value), [items, value]);
  const isSuggestionsOpen = !suggestionsClosed && candidates.length > 0;
  const activeOptionId =
    activeIndex >= 0 ? vehiculoSuggestionOptionId(listboxId, activeIndex) : undefined;

  function handleChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const raw = e.target.value;
    const looksLikePlaca = PLACA_SHAPE_REGEX.test(raw);
    const next = looksLikePlaca
      ? raw.toUpperCase().replace(/\s+/g, '').slice(0, PLACA_HERO_MAX_LEN)
      : raw.slice(0, PLACA_HERO_MAX_LEN);
    setValue(next);
    setActiveIndex(-1);
    setSuggestionsClosed(false);
  }

  /** Selecting a suggestion (click or Enter-on-highlighted) — shared by both paths. */
  function selectCandidate(candidate: VehiculoMatch): void {
    const { ingreso } = candidate;
    setValue('');
    setActiveIndex(-1);
    setSuggestionsClosed(true);
    if (ingreso.placa) {
      // Every candidate here comes from the active-ingresos snapshot, so
      // it is ALWAYS currently inside — same exact routing as the
      // legacy placa-found fallback below.
      openDrawer('salida', 'placa-hero-input', ingreso.placa);
    } else {
      // No placa (consecutivo-only, ej. bici/patineta) — hand off the
      // resolved uuid_ingreso directly; there is no placa text to
      // re-search. `<SalidaPanel>` re-runs the estado-guard before
      // trusting it (point 5/7 of the DoD).
      openDrawer('salida', 'placa-hero-input', null, null, ingreso.uuid);
    }
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
  //
  // HU-F7.1 (T5): arrow keys navigate the suggestion listbox and Enter
  // on a highlighted suggestion takes priority over this fallback —
  // see `selectCandidate` above. Enter with NOTHING highlighted keeps
  // this exact fallback path unchanged.
  async function onKeyDown(
    e: React.KeyboardEvent<HTMLInputElement>,
  ): Promise<void> {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (candidates.length === 0) return;
      e.preventDefault();
      setSuggestionsClosed(false);
      setActiveIndex((idx) =>
        getNextSuggestionIndex(idx, e.key === 'ArrowDown' ? 'down' : 'up', candidates.length),
      );
      return;
    }
    if (e.key === 'Escape') {
      if (isSuggestionsOpen) {
        e.preventDefault();
        setSuggestionsClosed(true);
        setActiveIndex(-1);
      }
      return;
    }
    if (e.key !== 'Enter') return;

    if (isSuggestionsOpen && activeIndex >= 0) {
      const candidate = candidates[activeIndex];
      if (candidate) {
        e.preventDefault();
        selectCandidate(candidate);
        return;
      }
    }

    // ── Fallback: legacy smart-routing path (verbatim, unchanged) ──
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
    <div className="space-y-2">
      {/* REGRESSION fix (2026-09-22) + pedido operador (2026-09-25): el
          aviso de "esta placa ya está dentro" ahora vive ARRIBA del input
          (antes abajo) y con estilo resaltado (chip de color, no texto
          plano) para que se note antes de presionar Enter — sigue siendo
          best-effort (SWR, puede ir un paso atrás del tecleo); la decisión
          real en Enter usa el fetch directo de abajo, este chip es solo
          UX. Reutiliza el token semántico `warning` (naranja/ámbar): no es
          un error, pero sí algo que el operador debe notar antes de
          continuar. */}
      {latestIngreso && (
        <p
          data-testid="placa-hero-active-hint"
          className="rounded-lg bg-warning px-3 py-1.5 text-center text-sm font-semibold text-warning-foreground"
          role="status"
        >
          {t('caja:dashboard.placaActiveHint', {
            defaultValue: 'Esta placa ya está dentro — presioná Enter para cobrar la salida.',
          })}
        </p>
      )}
      <div className="relative">
        <input
          type="text"
          autoFocus
          data-testid="placa-hero-input"
          id="placa-hero-input"
          placeholder="ABC123"
          value={value}
          onChange={handleChange}
          maxLength={PLACA_HERO_MAX_LEN}
          disabled={submitting}
          // Tamaño por pasos (no clamp() puro): el ancho disponible NO
          // escala linealmente con el viewport — a partir de md el layout
          // pasa a sidebar+main (240px fijos de por medio), así que un
          // clamp() basado en vw calcularía mal justo en ese quiebre. Los
          // pasos están calculados para que "ABC123" (6 chars, tracking
          // incluido) siempre quepa dentro del `placa-card` (max-w-3xl)
          // sin recortarse, incluso en 320px.
          className="mx-auto block w-full max-w-2xl rounded-2xl border-0 bg-muted/50 px-4 py-3 text-center font-mono text-[1.875rem] uppercase tracking-[0.12em] outline-none placeholder:text-muted-foreground/40 focus-ring-apple focus-visible:bg-background focus-visible:shadow-apple transition-all disabled:opacity-60 min-[375px]:text-[2.25rem] min-[480px]:py-4 min-[480px]:text-[2.75rem] min-[480px]:tracking-[0.2em] md:py-5 md:text-6xl md:tracking-[0.4em]"
          onKeyDown={onKeyDown}
          onBlur={() => setSuggestionsClosed(true)}
          aria-label={t('caja:dashboard.placaLabel', { defaultValue: 'Placa del vehículo' })}
          role="combobox"
          aria-expanded={isSuggestionsOpen}
          aria-controls={listboxId}
          aria-activedescendant={activeOptionId}
          aria-autocomplete="list"
          // uuid_sucursal is consumed by IngresoPanel inside the drawer; this
          // hero input is the entry-point keyboard handler.
          data-uuid-sucursal={uuid_sucursal ?? ''}
        />
        {/* HU-F7.1 (T5) — normal-size suggestion list; NEVER inherits the
            hero's text-6xl sizing (VehiculoSuggestions owns its own,
            legible body-text sizing). */}
        <VehiculoSuggestions
          listboxId={listboxId}
          candidates={isSuggestionsOpen ? candidates : []}
          activeIndex={activeIndex}
          onSelect={selectCandidate}
        />
      </div>
    </div>
  );
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
      {/* Reserve 20rem (antes 14rem): el footer de cupos (2026-09-24)
          dejó de estar topeado en 80px — crece a propósito para tener
          más presencia visual, así que esta lista reserva más espacio
          para que el footer más alto no la tape. */}
      <ul
        className="max-h-[calc(100dvh-14rem)] flex-1 divide-y divide-border/40 overflow-y-auto"
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
          // Cobros pendientes: la columna inline a la derecha SOLO si
          // el wire trae un valor > 0. Operador 2026-09-22: "los cobros
          // pendientes solo apareceran en el lado derecho de la tabla de
          // vehiculos dentro cuando sean > 0 si no hay no deben aparecer".
          // `?? null` cubre tanto `undefined` (campo ausente) como `null`
          // explícito del backend.
          const cobrosPendientes =
            typeof it.cobros_pendientes === 'number' && it.cobros_pendientes > 0
              ? it.cobros_pendientes
              : null;
          return (
            <li
              key={it.uuid}
              className="group flex items-center justify-between rounded-xl px-3 py-2 hover:bg-accent/40 transition-colors"
              data-testid={`vehiculos-item-${it.uuid}`}
            >
              <span className="font-mono text-sm font-medium uppercase tracking-wide" title={it.uuid}>
                {idVisible}
              </span>
              <div className="flex items-baseline gap-3">
                {cobrosPendientes !== null && (
                  <span
                    data-testid={`vehiculos-item-cobros-${it.uuid}`}
                    className="text-xs font-medium text-amber-700 dark:text-amber-300 tabular-nums"
                    title={t('caja:dashboard.cobrosPendientesTitle', {
                      defaultValue: 'Cobros pendientes',
                    })}
                  >
                    {formatCOP(cobrosPendientes)}
                  </span>
                )}
                <span className="text-xs text-muted-foreground tabular-nums">
                  {formatHoraCorta(horaIso)}
                </span>
              </div>
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
