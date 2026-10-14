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
 *     PagoSheet, ReimprimirTiqueteSheet, ArqueoSheet, CierreDiarioSheet —
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
import { useEffect, useId, useMemo, useRef, useState } from 'react';
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
import { useResumenCierrePendiente } from '../hooks/useResumenCierrePendiente';
import { useSesionActiva } from '../hooks/useSesionActiva';
import { CuposLibresStrip } from '../../operacion/components/CuposLibresStrip';
import { openSalidaDeIngreso } from '../../operacion/lib/openSalidaDeIngreso';
import {
  openReimpresionDeIngreso,
  terminoReimpresion,
} from '../../operacion/lib/openReimpresionDeIngreso';
import { FacturaElectronicaRetryPanel } from '../../facturacion/components/FacturaElectronicaRetryPanel';
import { ProximasVencerBanner } from '../../suscripciones/components/ProximasVencerBanner';
import { BaseCajaAviso } from '../components/BaseCajaAviso';
import { SyncStatusBadge } from '../../sync/components/SyncStatusBadge';
import { AlertasTrigger } from '../../alertas/components/AlertasTrigger';
import { useIngresoActivo } from '../../operacion/hooks/useIngresoActivo';
import { useIngresosActivos, type IngresoActivo } from '../../operacion/hooks/useIngresosActivos';
import {
  getIngresosByConsecutivo,
  getIngresosByPlaca,
} from '../../operacion/api/ingresoActivoApi';
import { REGEX_AUTO, REGEX_MOTO } from '../../../lib/validation/placa';
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
  // F6 — HU-F10.3 (ajuste 2026-09-25, directiva del operador): unificado
  // con el sheet multi-sesión — el viejo `'cierre-diario'` (per-session,
  // `<CierreDiarioDialog />`) era código muerto confirmado (se montaba
  // con uuid_sucursal/uuid_sesion=null siempre, su submit nunca hacía
  // nada) y fue retirado. F6 y el botón del sidebar abren el mismo flujo.
  F6: 'cierre-diario-multi',
  // F8 — HU-F8.3 (directiva del operador 2026-09-25): reimpresión de
  // tiquete con costo. Vive en el sheet (no en una ruta aparte del
  // dashboard) — mismo code path que el resto de los F-keys.
  F8: 'reimpresion',
};

export function Dashboard(): JSX.Element | null {
  const { sesion: sesionLive, isLoading, error, refresh } = useSesionActiva();
  // PT-5: keep rendering the dashboard (and the drawer that hosts the
  // post-close summary) with the last known sesion while the summary is
  // pending, even after /sesion/me starts answering 404 for the closed turn.
  const resumenCierrePendiente = useResumenCierrePendiente((s) => s.pendiente);
  const ultimaSesionRef = useRef<typeof sesionLive>(null);
  if (sesionLive) ultimaSesionRef.current = sesionLive;
  const sesion = sesionLive ?? (resumenCierrePendiente ? ultimaSesionRef.current : null);
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
    // PT-5: while the post-close summary is on screen the sesion is already
    // closed server-side (404 on /sesion/me) but the operator is still
    // reading/downloading the summary — do not tear the dashboard down.
    if (!sesion && !isLoading && !error && !resumenCierrePendiente) {
      navigate('/caja/abrir-turno', { replace: true });
    }
  }, [isAuthenticated, isAuthLoading, sesion, isLoading, error, navigate, resumenCierrePendiente]);

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
    // 2026-09-25 (pedido operador, tras confirmar con data real de la
    // sucursal de prueba que ninguno de los dos campos solo alcanza):
    // combina `prefijo_nombre` (código corto, ej. "BOG-CEN") + `nombre`
    // completo cuando ambos existen — "BOG-CEN - Sucursal Bogotá Centro".
    // Con datos de seed placeholder hoy se ve "D2049f2 - Suc 2049f2cd";
    // en producción, con datos reales cargados, se ve como se espera.
    const sucursalLabel =
      [sucursal?.prefijo_nombre, sucursal?.nombre].filter(Boolean).join(' - ') ||
      t('common:sucursal', { defaultValue: 'Sucursal' });

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
                    // Ajuste 2026-09-25 (directiva del operador: "cierre
                    // diario no debe estar en una ruta aparte, debe estar
                    // en un sheet dentro de / como todas las demás
                    // funcionalidades"). Reemplaza la navegación a la ruta
                    // `/caja/cierre-diario` (retirada de App.tsx) por el
                    // Sheet `'cierre-diario-multi'` (HU-F10.3, mismo
                    // patrón que Arqueo/CerrarTurno/Reimprimir). Unificado
                    // con el hotkey F6 (ver comentario en DRAWER_BY_HOTKEY
                    // arriba) — el viejo `'cierre-diario'` per-session
                    // (`<CierreDiarioDialog />`, código muerto confirmado)
                    // fue retirado, así que el badge F6 ya es coherente.
                    openDrawer('cierre-diario-multi', 'sidebar-cierre-diario');
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
                  <kbd className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">F8</kbd>
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
          className="row-start-2 col-start-1 min-h-0 min-w-0 flex flex-col gap-3 overflow-y-auto p-[clamp(0.75rem,1.5vw,1.5rem)] md:col-start-2"
        >
          {/* Aviso de la base de caja recién recibida (parametrizada por
              administración); no renderiza nada si ya se descartó. */}
          <BaseCajaAviso sesion={sesion} />

          {/* PT-3: aviso de suscripciones próximas a vencer (feed del backend);
              no renderiza nada si no hay avisos. */}
          <ProximasVencerBanner uuid_sucursal={uuid_sucursal} />

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
          <VehiculosDentroList uuid_sucursal={uuid_sucursal} />

          {/* Hidden: legacy section panel kept for tests via
              `data-testid="dashboard-section-fe-retry"`. */}
          <div aria-hidden className="sr-only">
            <section data-testid="dashboard-section-fe-retry">
              <FacturaElectronicaRetryPanel uuid_fe={null} />
            </section>
          </div>
        </main>

        {/* ── Footer full-width (operador 2026-09-22): inventario per-tipo + cupos libres agregados ── */}
        <CuposLibresStrip uuid_sucursal={uuid_sucursal}>
          {/* Alertas: módulo colapsado — trigger en el footer, panel en bottom sheet. */}
          <AlertasTrigger uuid_sucursal={uuid_sucursal} />
        </CuposLibresStrip>

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

/** Forma de un consecutivo impreso en el tiquete: `<TIPO>-NNNNNN-<uuid8>`. */
const CONSECUTIVO_SHAPE_REGEX = /^[A-Z]+-\d{6}-[0-9a-f]{8}$/i;

function PlacaInputHero({
  uuid_sucursal,
}: {
  uuid_sucursal: string | null;
}): JSX.Element {
  const { t } = useTranslation(['caja', 'common', 'errors']);
  const openDrawer = useDashboardDrawerStore((s) => s.open);

  // Controlled input so the typed plate can drive `useIngresoActivo`
  // and be passed to the drawer (REQ-OPS-136 smart routing).
  const [value, setValue] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    setError(null);
    setActiveIndex(-1);
    setSuggestionsClosed(false);
  }

  /** Selecting a suggestion (click or Enter-on-highlighted) — shared by both paths. */
  function selectCandidate(candidate: VehiculoMatch): void {
    setValue('');
    setActiveIndex(-1);
    setSuggestionsClosed(true);
    // Every candidate comes from the active-ingresos snapshot, so it is
    // ALWAYS currently inside. `<SalidaPanel>` re-runs the estado-guard
    // before trusting a uuid handoff (point 5/7 of the DoD).
    openSalidaDeIngreso(openDrawer, 'placa-hero-input', candidate.ingreso);
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

    const placa = value.trim();
    if (placa === '') return;
    e.preventDefault();
    if (submitting) return;

    // ── Salida por consecutivo (vehículo sin placa) ──────────────────
    // `getIngresosByPlaca` consulta `?placa=` y NUNCA resuelve un
    // consecutivo (devuelve `[]` → abría Ingreso por error). Antes de
    // caer a la ruta por placa se resuelve el texto como consecutivo.
    const lower = placa.toLowerCase();
    const exacto = (items ?? []).find((it) => it.consecutivo?.toLowerCase() === lower);
    if (exacto) {
      selectCandidate({ ingreso: exacto, matchedOn: 'consecutivo' });
      return;
    }
    const esPlacaValida = REGEX_AUTO.test(normalized) || REGEX_MOTO.test(normalized);
    const esConsecutivo = CONSECUTIVO_SHAPE_REGEX.test(placa);
    const unicoCandidato = candidates.length === 1 ? candidates[0] : undefined;
    if (!esPlacaValida && !esConsecutivo && unicoCandidato?.matchedOn === 'consecutivo') {
      selectCandidate(unicoCandidato);
      return;
    }
    if (esConsecutivo) {
      // La lista puede no haber cargado (o estar a un poll de distancia):
      // el backend resuelve `?consecutivo=<x>&activo=true`.
      setSubmitting(true);
      try {
        const rows = await getIngresosByConsecutivo(placa, { soloActivos: true });
        const row = rows[0];
        if (row) {
          setError(null);
          setValue('');
          openSalidaDeIngreso(openDrawer, 'placa-hero-input', row);
        } else {
          setError(
            t('caja:dashboard.consecutivoNoEncontrado', {
              defaultValue: 'Consecutivo no encontrado entre los vehículos dentro.',
            }),
          );
        }
      } catch {
        setError(t('common:error'));
      } finally {
        setSubmitting(false);
      }
      return;
    }

    // Ni placa válida ni consecutivo: no abrir ningún drawer (IngresoPanel
    // descartaba en silencio el valor inválido) — avisar al operador.
    if (!esPlacaValida) {
      setError(
        t('errors:validation.placa_formato_invalido', {
          defaultValue:
            'Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)',
        }),
      );
      return;
    }

    // ── Fallback: smart-routing por placa ──
    setSubmitting(true);
    try {
      // Fetch directo bloqueante para que la decisión sea autoritativa
      // (no race contra el SWR cache). Reutiliza el mismo endpoint que
      // ``useIngresoActivo`` — solo cambia el modo (await inline vs
      // SWR background poll).
      const rows = await getIngresosByPlaca(placa, { soloActivos: true });
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
          aria-describedby={error !== null ? 'placa-hero-error' : undefined}
          aria-invalid={error !== null}
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
      {error !== null && (
        <p
          id="placa-hero-error"
          data-testid="placa-hero-error"
          role="alert"
          className="text-center text-sm font-medium text-destructive"
        >
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * "Vehículos dentro": TODOS los ingresos activos en una región con scroll
 * interno que ocupa el alto disponible del card (el header + conteo quedan
 * fijos; la página no crece). Sin paginación: `overflow-y-auto` simple rinde
 * bien para unos cientos de filas. Cada fila es el trigger de un menú de
 * acciones del vehículo; las acciones sólo ENRUTAN a los drawers existentes
 * (mismos helpers que `<VehiculosTipoSheet />`).
 */
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

  return (
    <Card
      data-testid="vehiculos-list-card"
      className="flex min-h-56 flex-1 flex-col overflow-hidden"
    >
      <CardHeader className="flex-row items-center gap-2 space-y-0 px-5 pt-5 pb-3">
        <CardTitle className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
          {t('caja:dashboard.vehiculosDentro', { defaultValue: 'Vehículos dentro' })}
        </CardTitle>
        {safe !== null && (
          <span
            data-testid="vehiculos-count"
            aria-live="polite"
            className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums text-muted-foreground"
          >
            {safe.length}
          </span>
        )}
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col px-3 pb-3 text-sm">
        {safe === null ? (
          <p className="text-muted-foreground" data-testid="vehiculos-loading">
            {t('common:loading')}
          </p>
        ) : safe.length === 0 ? (
          <p className="text-muted-foreground" data-testid="vehiculos-empty">
            {t('caja:dashboard.sinVehiculos', { defaultValue: 'Sin vehículos dentro.' })}
          </p>
        ) : (
          <ul
            className="min-h-0 flex-1 divide-y divide-border/40 overflow-y-auto"
            data-testid="vehiculos-list"
          >
            {safe.map((it) => (
              <VehiculoDentroRow key={it.uuid} ingreso={it} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function VehiculoDentroRow({ ingreso: it }: { ingreso: IngresoActivo }): JSX.Element {
  const { t } = useTranslation('caja');
  const openDrawer = useDashboardDrawerStore((s) => s.open);
  // Cuando una acción abre un drawer, el foco lo maneja el drawer (y al
  // cerrarse vuelve a este trigger vía `lastAnchorId`); sólo al cerrar el
  // menú SIN elegir acción (Esc / click afuera) Radix devuelve el foco a la fila.
  const actionChosenRef = useRef(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const rowRef = useRef<HTMLLIElement>(null);
  const plateRef = useRef<HTMLButtonElement>(null);

  // Identificador visible: placa si existe, sino el consecutivo
  // (REQ-OPS-197, mismo string que se imprime en el tiquete), y
  // como último recurso los primeros 8 chars del uuid.
  const idVisible = it.placa ?? it.consecutivo ?? it.uuid.slice(0, 8);
  const anchorId = `vehiculos-item-anchor-${it.uuid}`;
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
    // The menu is anchored to the right-hand block (cobros + time) and opens to its
    // LEFT, in a single row: it sits on the right side of the table, never covers
    // the time and is not taller than the row, so neighbouring plates stay visible.
    // The plate button (and the rest of the row) toggles it.
    <li
      ref={rowRef}
      data-testid={`vehiculos-item-${it.uuid}`}
      data-state={menuOpen ? 'open' : 'closed'}
      className="flex cursor-pointer items-center justify-between rounded-xl transition-colors hover:bg-accent/40 data-[state=open]:bg-accent/40"
      onClick={(e) => {
        // Portaled menu events bubble through React; only handle clicks on the row itself.
        if (!e.currentTarget.contains(e.target as Node)) return;
        // The anchor block is the Radix trigger and toggles by itself.
        if ((e.target as HTMLElement).closest('[data-menu-anchor]')) return;
        setMenuOpen((open) => !open);
      }}
    >
      <button
        type="button"
        ref={plateRef}
        id={anchorId}
        data-testid={`vehiculos-item-action-${it.uuid}`}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        aria-label={t('caja:dashboard.accionesDe', {
          defaultValue: `Acciones para ${idVisible}`,
          id: idVisible,
        })}
        className="rounded-xl px-3 py-2 text-left focus-ring-apple"
      >
        <span className="font-mono text-sm font-medium uppercase tracking-wide" title={it.uuid}>
          {idVisible}
        </span>
      </button>
      <DropdownMenu modal={false} open={menuOpen} onOpenChange={setMenuOpen}>
        <DropdownMenuTrigger asChild>
          <div data-menu-anchor className="flex items-baseline gap-3 px-3 py-2">
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
        </DropdownMenuTrigger>
        <DropdownMenuContent
          side="left"
          align="center"
          sideOffset={4}
          className="flex flex-row justify-end gap-2 p-1.5"
          data-testid={`vehiculos-item-menu-${it.uuid}`}
          onInteractOutside={(e) => {
            // Clicks on this row's own plate/row are handled by the row toggle.
            if (rowRef.current?.contains(e.target as Node)) e.preventDefault();
          }}
          onCloseAutoFocus={(e) => {
            // The anchor is not focusable: hand focus back to the plate button, unless
            // an action opened a drawer (the drawer owns focus then).
            e.preventDefault();
            if (actionChosenRef.current) {
              actionChosenRef.current = false;
              return;
            }
            plateRef.current?.focus();
          }}
        >
          <DropdownMenuItem
            data-testid={`vehiculos-item-salida-${it.uuid}`}
            className="h-8 cursor-pointer whitespace-nowrap rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/70 hover:text-primary-foreground hover:ring-2 hover:ring-primary/40 focus:bg-primary/70 focus:text-primary-foreground data-[highlighted]:bg-primary/70 data-[highlighted]:text-primary-foreground data-[highlighted]:ring-2 data-[highlighted]:ring-primary/40"
            onSelect={() => {
              actionChosenRef.current = true;
              openSalidaDeIngreso(openDrawer, anchorId, it);
            }}
          >
            {t('caja:dashboard.registrarSalida', { defaultValue: 'Registrar salida' })}
          </DropdownMenuItem>
          {terminoReimpresion(it) !== null && (
            <DropdownMenuItem
              data-testid={`vehiculos-item-reimprimir-${it.uuid}`}
              className="h-8 cursor-pointer whitespace-nowrap rounded-lg border border-border bg-background px-3 text-xs font-medium transition-colors hover:border-primary hover:bg-primary/30 hover:text-foreground focus:border-primary focus:bg-primary/30 focus:text-foreground data-[highlighted]:border-primary data-[highlighted]:bg-primary/30"
              onSelect={() => {
                actionChosenRef.current = true;
                openReimpresionDeIngreso(openDrawer, anchorId, it);
              }}
            >
              {t('caja:dashboard.reimprimirTicketEntrada', {
                defaultValue: 'Reimprimir ticket de entrada',
              })}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </li>
  );
}
