/**
 * `<Dashboard />` — container (F3.3 — T4, DEC-F3.3-05 + REQ-OPS-136/137).
 *
 * Página `/` que consume `useSesionActiva()` y decide redirect atómicamente:
 *
 *   (a) `sesion === null && !isLoading && !error`
 *       → `navigate('/caja/abrir-turno', { replace: true })` (replace previene
 *         back-button infinite loop en kiosko).
 *
 *   (b) `sesion !== null` → renderiza el hub persistente que orquesta:
 *       - `<TurnoActivoPanel />` (F3.3) en la parte superior.
 *       - `<OcupacionPanel />` (F4.3, F4.4 relocate).
 *       - 4 slots de sección para features futuros (ingreso / salida /
 *         facturacion / reimpresion / suscripciones / sync / alertas) —
 *         cada uno lazy-mount según REQ-OPS-139.
 *       - 1 `<DrawerHost />` que consume `useDashboardDrawerStore` y
 *         monta el único drawer activo (REQ-OPS-138).
 *
 *   (c) `isLoading === true` → `<Skeleton>` neutral.
 *
 *   (d) `error && status !== 404/422` → error + retry button.
 *
 * Note: el `<OcupacionStrip />` global en `App.tsx:48` se mantiene hasta
 * PR-6 (REQ-OPS-140). Durante PR-1..PR-5 coexisten el strip global y el
 * panel in-dashboard — el panel es el nuevo mount canónico, el strip
 * global se borra al final.
 *
 * DEC-F3.3-05 single source of truth: Dashboard consume `useSesionActiva`
 * y NO verifica autenticación directamente — `<ProtectedRoute>` (App.tsx)
 * intercepta `parkos:auth:cleared` y navega a `/login?next=...`.
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useAuth } from '@parkos/ui-kit/hooks';

import { useSesionActiva } from '../hooks/useSesionActiva';
import { TurnoActivoPanel } from '../components/TurnoActivoPanel';
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

import { DrawerHost } from './DrawerHost';

export function Dashboard(): JSX.Element | null {
  const { sesion, isLoading, error, refresh } = useSesionActiva();
  const { isAuthenticated, isLoading: isAuthLoading, sucursal } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation(['caja', 'common', 'operacion']);
  const uuid_sucursal = sucursal?.uuid ?? null;

  // DEC-F3.3-05 + auth guard: redirect atómico cuando no hay sesión activa Y
  // el operador está autenticado. Sin auth previa → /login (no salta el login).
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

  // (c) Loading state → Skeleton neutral.
  if (isLoading) {
    return <Skeleton className="h-32 w-full" data-testid="dashboard-skeleton" />;
  }

  // (d) Error state distinto a 404 → error + retry.
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

  // (b) Sesión activa → hub persistente.
  if (sesion) {
    return (
      <div
        className="flex w-full max-w-5xl flex-col gap-4"
        data-testid="dashboard-hub"
      >
        <TurnoActivoPanel
          sesion={sesion}
          onCerrarClick={() => navigate('/caja/cerrar-turno')}
        />

        {/* Slot 1 — OcupacionPanel (F4.3 relocated). */}
        <section data-testid="dashboard-section-ocupacion" aria-label={t('caja:dashboard.ocupacion', { defaultValue: 'Ocupación' })}>
          <OcupacionPanel uuid_sucursal={uuid_sucursal} />
        </section>

        {/* Slot 2 — IngresoPanel (F6.1, PR-2). */}
        <section data-testid="dashboard-section-ingreso" aria-label={t('caja:dashboard.operar', { defaultValue: 'Ingreso' })}>
          <IngresoPanel />
        </section>

        {/* Slot 3 — SalidaPanel (F7.1+F7.2, PR-3). */}
        <section data-testid="dashboard-section-salida" aria-label={t('operacion:salida', { defaultValue: 'Salida' })}>
          <Card>
            <CardHeader>
              <CardTitle>{t('operacion:salida', { defaultValue: 'Salida' })}</CardTitle>
              <CardDescription>{t('caja:dashboard.placeholderDesc', { defaultValue: 'Sección pendiente (PR-3).' })}</CardDescription>
            </CardHeader>
            <CardContent>
              <SalidaPanel uuid_ingreso={null} onPagoSubmit={async () => {}} />
            </CardContent>
          </Card>
        </section>

        <section data-testid="dashboard-section-suscripciones" aria-label={t('caja:dashboard.suscripciones', { defaultValue: 'Suscripciones' })}>
          <SuscripcionesPanel uuid_sucursal={uuid_sucursal} />
        </section>

        <section data-testid="dashboard-section-sync" aria-label={t('caja:dashboard.sync', { defaultValue: 'Sincronización' })}>
          <SyncStatusStrip uuid_sucursal={uuid_sucursal} />
        </section>

        <section data-testid="dashboard-section-alertas" aria-label={t('caja:dashboard.alertas', { defaultValue: 'Alertas' })}>
          <AlertasPanel uuid_sucursal={uuid_sucursal} />
        </section>

        {/* Slot 7 — FacturaElectronicaRetryPanel (F8.2, PR-4 mount).
            Lazy-mount: passes uuid_fe={null} because no ingreso currently
            exposes a pending FE trigger; the panel issues ZERO fetches
            while uuid_fe is null (REQ-OPS-139 cold-Dashboard invariant).
            Once a uuid_fe source is wired (PR-X), pass it through here. */}
        <section data-testid="dashboard-section-fe-retry" aria-label={t('facturacion:fe.titulo', { defaultValue: 'Factura electrónica' })}>
          <FacturaElectronicaRetryPanel uuid_fe={null} />
        </section>

        {/* DrawerHost — single-drawer invariant (REQ-OPS-138). */}
        <DrawerHost />
      </div>
    );
  }

  // (a) sin sesión + no loading + no error → el redirect se dispara en el effect.
  // Render defensivo: no flash de "sesión no iniciada" antes del redirect.
  return null;
}