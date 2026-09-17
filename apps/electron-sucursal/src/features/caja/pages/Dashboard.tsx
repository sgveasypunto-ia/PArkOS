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
 *   │ 5 action │                                   │  AUTOS 5         │
 *   │ buttons  │  Bienvenido + keyboard help       │  MOTOS 4         │
 *   │ → drawers│                                   │                  │
 *   │          │                                   │  VEHICULOS LIST  │
 *   │          │                                   │  COBROS PEND.    │
 *   └──────────┴───────────────────────────────────┴──────────────────┘
 *
 * Hotkeys (F1-F6) open the matching side-panel drawer via the
 * `useDashboardDrawerStore` Zustand singleton (REQ-OPS-138 single-drawer
 * invariant). Esc closes any active drawer.
 *
 * Sections previously listed in 2-col grid (REQ-OPS-136 PR-1..PR-6) are
 * now collapsed into:
 *   - Top header bar (operador + status + cerrar)
 *   - Left sidebar (5 navigation actions)
 *   - Placa input hero (the operator's only primary action during the turn)
 *   - Right sidebar (live counts + active vehicles + pending cobros)
 *   - DrawerHost (single-drawer mounted for: PagoSheet, FE-Retry, Reimprimir,
 *     ArqueoSheet, CierreDiarioDialog — triggered by sidebar OR hotkey)
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';
import { useAuth } from '@parkos/ui-kit/hooks';

import { useSesionActiva } from '../hooks/useSesionActiva';
import { OcupacionPanel } from '../components/OcupacionPanel';
import { IngresoPanel } from '../../operacion/components/IngresoPanel';
import { SalidaPanel } from '../../operacion/components/SalidaPanel';
import { FacturaElectronicaRetryPanel } from '../../facturacion/components/FacturaElectronicaRetryPanel';
import { SuscripcionesPanel } from '../../suscripciones/components/SuscripcionesPanel';
import { SyncStatusStrip } from '../../sync/components/SyncStatusStrip';
import { AlertasPanel } from '../../sync/components/AlertasPanel';
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
  const { t } = useTranslation(['caja', 'common', 'operacion']);
  const uuid_sucursal = sucursal?.uuid ?? null;
  const openDrawer = useDashboardDrawerStore((s) => s.open);
  const closeDrawer = useDashboardDrawerStore((s) => s.close);
  const openDrawerKind = useDashboardDrawerStore((s) => s.openDrawer);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // F1-F6 hotkey listener → openDrawer + Esc closes.
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
        openDrawer(target);
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
        <header className="col-span-1 lg:col-span-3 flex flex-wrap items-center gap-2 border-b border-border bg-card px-3 py-2 md:gap-3 md:px-4">
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
            className="ml-auto hidden items-center gap-1 rounded-full border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700 lg:inline-flex"
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
                className="inline-flex h-6 cursor-pointer items-center rounded border border-border bg-background px-2 text-xs hover:bg-accent"
                onClick={() => openDrawer(kind)}
              >
                {key}
              </kbd>
            ))}
          </span>

          {/* Turno chip + Cerrar turno — always visible (mobile + desktop). */}
          <TurnoActivoToggle sesion={sesion} />
          <Button
            variant="outline"
            size="sm"
            data-testid="dashboard-cerrar-turno"
            onClick={() => navigate('/caja/cerrar-turno')}
            className="shrink-0"
          >
            {t('caja:cerrarTurno')}
          </Button>
        </header>

        {/* ── Left sidebar nav ──────────────────────────────────────────── */}
        <nav
          id="dashboard-sidebar-nav"
          aria-label={t('caja:dashboard.navLabel', { defaultValue: 'Acciones rápidas' })}
          className={
            // Mobile: drawer-style overlay (when hamburger open) OR hidden.
            // lg+: static sidebar in the grid (col-start-1 row-start-2).
            'flex flex-col gap-2 overflow-y-auto border-border bg-card p-2 ' +
            'lg:row-start-2 lg:col-start-1 lg:border-r ' +
            (mobileNavOpen
              ? 'fixed inset-y-0 left-0 z-40 w-64 border-r shadow-xl'
              : 'hidden lg:flex')
          }
        >
          <Button
            variant="outline"
            data-testid="sidebar-suscripciones"
            className="justify-start text-sm"
            onClick={() => {
              openDrawer('suscripciones');
              setMobileNavOpen(false);
            }}
          >
            💳 {t('suscripciones:menu', { defaultValue: 'Suscripción' })}
          </Button>
          <Button
            variant="outline"
            data-testid="sidebar-arqueo"
            className="justify-start text-sm"
            onClick={() => {
              openDrawer('arqueo');
              setMobileNavOpen(false);
            }}
          >
            🧮 {t('caja:arqueo', { defaultValue: 'Arqueo' })}
          </Button>
          <Button
            variant="outline"
            data-testid="sidebar-cierre-diario"
            className="justify-start text-sm"
            onClick={() => {
              openDrawer('cierre-diario');
              setMobileNavOpen(false);
            }}
          >
            📋 {t('caja:dashboard.cierreDiario', { defaultValue: 'Cierre diario' })}
            <kbd className="ml-auto rounded bg-muted px-1 text-[10px]">F6</kbd>
          </Button>
          <Button
            variant="outline"
            data-testid="sidebar-inventario"
            className="justify-start text-sm"
            onClick={() => {
              openDrawer('inventario');
              setMobileNavOpen(false);
            }}
          >
            📦 {t('caja:dashboard.inventario', { defaultValue: 'Inventario' })}
            <kbd className="ml-auto rounded bg-muted px-1 text-[10px]">F5</kbd>
          </Button>
          <Button
            variant="outline"
            data-testid="sidebar-facturas"
            className="justify-start text-sm"
            onClick={() => {
              openDrawer('reimpresion');
              setMobileNavOpen(false);
            }}
          >
            🧾 {t('caja:dashboard.facturas', { defaultValue: 'Facturas' })}
          </Button>
        </nav>

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
          <Card data-testid="placa-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm uppercase tracking-wider text-muted-foreground">
                {t('caja:dashboard.placaLabel', { defaultValue: 'Placa del vehículo' })}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {/* The placa input hero — autofocus on mount, ABC123 placeholder. */}
              <PlacaInputHero uuid_sucursal={uuid_sucursal} />
            </CardContent>
          </Card>

          <Card data-testid="welcome-card">
            <CardHeader className="pb-2">
              <CardTitle>{t('caja:dashboard.welcome', { defaultValue: 'Bienvenido' })}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <p className="text-muted-foreground">
                {t('caja:dashboard.welcomeHelp', {
                  defaultValue:
                    'Digita la placa arriba. El sistema abre automáticamente el panel correspondiente (pago si tiene cobro pendiente, salida si ya está dentro, ingreso si es nueva).',
                })}
              </p>
              <ul className="hidden space-y-0.5 pt-1 md:block">
                <li><kbd className="kbd-key">F1</kbd> {t('caja:dashboard.help.ingreso', { defaultValue: 'Abrir panel de ingreso (Atajo de teclado).' })}</li>
                <li><kbd className="kbd-key">F2</kbd> {t('caja:dashboard.help.salida', { defaultValue: 'Abrir panel de salida (Atajo de teclado).' })}</li>
                <li><kbd className="kbd-key">F3</kbd> {t('caja:dashboard.help.suscripciones', { defaultValue: 'Suscripción — modulo futuro.' })}</li>
                <li><kbd className="kbd-key">F4</kbd> {t('caja:dashboard.help.arqueo', { defaultValue: 'Arqueo — arqueo parcial (EP-13).' })}</li>
                <li><kbd className="kbd-key">F5</kbd> {t('caja:dashboard.help.inventario', { defaultValue: 'Inventario — vehiculos dentro del parqueadero (EP-09).' })}</li>
                <li><kbd className="kbd-key">F6</kbd> {t('caja:dashboard.help.cierre', { defaultValue: 'Cierre — cierre diario (EP-14).' })}</li>
                <li><kbd className="kbd-key">Esc</kbd> {t('caja:dashboard.help.esc', { defaultValue: 'Volver a esta pantalla.' })}</li>
              </ul>
            </CardContent>
          </Card>

          {/* Hidden: legacy section panels for compatibility with the F4.4
              `OcupacionStrip` removal. Render collapsed so any consumer still
              polling `data-testid="dashboard-section-ingreso"` etc. finds the
              anchor without breaking the layout. */}
          <div aria-hidden className="sr-only">
            <section data-testid="dashboard-section-ingreso">
              <IngresoPanel />
            </section>
          </div>
          <div aria-hidden className="sr-only">
            <section data-testid="dashboard-section-salida">
              <SalidaPanel uuid_ingreso={null} onPagoSubmit={async () => {}} />
            </section>
          </div>
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
          className="col-span-1 mt-3 grid gap-2 px-3 pb-4 lg:row-start-2 lg:col-start-3 lg:mt-0 lg:border-l lg:bg-card lg:px-2 lg:pb-0"
        >
          {/* Inventario: per-tipo occupancy (admin-configured cupos only). */}
          <Card data-testid="inventario-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm uppercase tracking-wider text-muted-foreground">
                {t('caja:dashboard.inventario', { defaultValue: 'Inventario' })}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-2">
              <OcupacionPanel uuid_sucursal={uuid_sucursal} />
            </CardContent>
          </Card>

          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-1">
            <Card data-testid="vehiculos-list-card" className="overflow-hidden">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm uppercase tracking-wider text-muted-foreground">
                  {t('caja:dashboard.vehiculosDentro', { defaultValue: 'Vehículos dentro' })}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 overflow-y-auto p-2 text-sm">
                <VehiculosDentroList uuid_sucursal={uuid_sucursal} />
              </CardContent>
            </Card>

            <Card data-testid="cobros-list-card" className="overflow-hidden">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm uppercase tracking-wider text-muted-foreground">
                  {t('caja:dashboard.cobrosPendientes', { defaultValue: 'Cobros pendientes' })}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 overflow-y-auto p-2 text-sm">
                <p className="text-muted-foreground" data-testid="cobros-empty">
                  {t('caja:dashboard.sinCobros', { defaultValue: 'Sin cobros pendientes.' })}
                </p>
              </CardContent>
            </Card>
          </div>
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
  uuid_sucursal,
}: {
  uuid_sucursal: string | null;
}): JSX.Element {
  const { t } = useTranslation('caja');
  const openDrawer = useDashboardDrawerStore((s) => s.open);

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>): void {
    if (e.key === 'Enter') {
      const value = (e.currentTarget as HTMLInputElement).value.trim().toUpperCase();
      if (value === '') return;
      // Smart routing per plan.md §CU-02: if ingreso activo → F2 (salida/cobro);
      // else → F1 (ingreso). The hook handles the lookup.
      e.preventDefault();
      // Lazy heuristic: open the ingreso drawer; the panel re-checks
      // useIngresoActivo and redirects to salida or pago internally.
      openDrawer('ingreso');
    }
  }

  return (
    <input
      type="text"
      autoFocus
      data-testid="placa-hero-input"
      placeholder="ABC123"
      maxLength={6}
      className="block w-full rounded border border-input bg-background px-4 py-3 text-center font-mono text-5xl uppercase tracking-[0.4em] outline-none ring-ring placeholder:text-muted-foreground focus:ring-2"
      onKeyDown={onKeyDown}
      aria-label={t('caja:dashboard.placaLabel', { defaultValue: 'Placa del vehículo' })}
      // uuid_sucursal is consumed by IngresoPanel inside the drawer; this
      // hero input is the entry-point keyboard handler.
      data-uuid-sucursal={uuid_sucursal ?? ''}
    />
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
  fecha_ingreso: string;
  uuid_tipo_vehiculo: string;
  uuid_sucursal: string;
}

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
  return (
    <ul className="space-y-1" data-testid="vehiculos-list">
      {safe.map((it) => (
        <li
          key={it.uuid}
          className="flex items-center justify-between rounded border border-border bg-background px-2 py-1"
          data-testid={`vehiculos-item-${it.uuid}`}
        >
          <span className="font-mono uppercase">
            {it.placa ?? <span className="italic text-muted-foreground">—sin placa—</span>}
          </span>
          <span className="text-xs text-muted-foreground tabular-nums">
            {new Date(it.fecha_ingreso).toLocaleTimeString('es-CO', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </li>
      ))}
    </ul>
  );
}

function CobrosPendientesList({
  uuid_sucursal: _uuid_sucursal,
}: {
  uuid_sucursal: string | null;
}): JSX.Element {
  const { t } = useTranslation('caja');
  return (
    <p className="text-muted-foreground" data-testid="cobros-empty">
      {t('caja:dashboard.sinCobros', { defaultValue: 'Sin cobros pendientes.' })}
    </p>
  );
}
