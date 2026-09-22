import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

import { StatusBar } from './components/StatusBar';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Login } from '../features/auth/pages/Login';
import { Dashboard } from '../features/caja/pages/Dashboard';
import { AbrirTurno } from '../features/caja/pages/AbrirTurno';
import { ArqueoParcial } from '../features/caja/pages/ArqueoParcial';
import { CierreDiario } from '../features/caja/pages/CierreDiario';
import { FacturaDetalle } from '../features/facturacion/pages/FacturaDetalle';
import { ReimprimirTiquete } from '../features/facturacion/pages/ReimprimirTiquete';
import { Venta } from '../features/suscripciones/pages/Venta';
import { Listado } from '../features/suscripciones/pages/Listado';
import { SyncBanner } from '../components/SyncBanner';
import { LocalApiDownBanner } from '../components/LocalApiDownBanner';
import { useAuth } from '@parkos/ui-kit/hooks';

/**
 * App — F2.1 router + F2.3 StatusBar mount + F3.1 Login + F3.3 caja
 * routes + REQ-OPS-140 (PR-6 of operador-dashboard-hub): the global
 * `<OcupacionStrip />` mount at the old L48 has been removed; the
 * occupancy panel now lives ONLY inside `<Dashboard />` so it does
 * not poll the API on `/caja/abrir-turno` and `/caja/cerrar-turno`
 * (F4.3 "TEMPORAL" comment honoured).
 *
 * F11.1 mount order (AD-5 + REQ-OPS-174):
 *   1. `<StatusBar />` — F2.3 API health chip (kept).
 *   2. `<LocalApiDownBanner />` — sticky hard-fault banner, mounts
 *      only when selectApiStatusDown(state) === true.
 *   3. `<SyncBanner />` — top-of-page sync-to-cloud health banner,
 *      gated on `useAuth().sucursal?.uuid != null` so the
 *      /sync/estado SWR poll fires only when the operator has a
 *      branch context (REQ-OPS-139 lazy-mount precedent).
 *
 * F11.2 note: `<AlertasPanel />` (REQ-OPS-178) was previously mounted
 * here at the App root but is now SCOPED to `<Dashboard />` only --
 * focused routes (caja/facturacion/suscripciones) don't need the
 * alerts surface while the operator is performing one task. Dashboard
 * keeps the panel in `sr-only` for back-compat with `dashboard-section-
 * alertas` test ids. The pre-auth gate (`!uuid_sucursal`) is also no
 * longer needed at the App level since the panel is unreachable from
 * /login anyway (Dashboard is not mounted on /login).
 *

 * Layout: full-bleed (no centered max-width) so the 6-section dashboard
 * uses the whole viewport without scroll at 1080p.
 *
 * The persistent turno indicator (chip + expandable details) lives inside
 * `<Dashboard />` as `<TurnoActivoToggle />` — see F3.3 + REQ-OPS-027.
 *
 * The root renders a semantic `<main>` with one `<h1>` so axe-core's
 * WCAG 2.1 AA audit (RNF-022) is satisfied from day one.
 */
export default function App(): JSX.Element {
  const { t } = useTranslation('common');
  const { sucursal } = useAuth();
  const branchUuid = sucursal?.uuid ?? null;

  return (
    <>
      <StatusBar />
      <LocalApiDownBanner />
      <SyncBanner uuid_sucursal={branchUuid} />
      <main
        lang="es-CO"
        className="block min-h-[calc(100vh-2rem)] w-full bg-muted/40 px-4 py-3"
      >
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/caja/abrir-turno"
            element={
              <ProtectedRoute>
                <AbrirTurno />
              </ProtectedRoute>
            }
          />
          <Route
            path="/caja/cierre-diario"
            element={
              <ProtectedRoute>
                <CierreDiario />
              </ProtectedRoute>
            }
          />
          <Route
            path="/factura-electronica/:uuid"
            element={
              <ProtectedRoute>
                <FacturaDetalle />
              </ProtectedRoute>
            }
          />
          <Route
            path="/facturacion/reimprimir"
            element={
              <ProtectedRoute>
                <ReimprimirTiquete />
              </ProtectedRoute>
            }
          />
          <Route
            path="/suscripciones/venta"
            element={
              <ProtectedRoute>
                <Venta />
              </ProtectedRoute>
            }
          />
          <Route
            path="/suscripciones"
            element={
              <ProtectedRoute>
                <Listado />
              </ProtectedRoute>
            }
          />
          <Route
            path="*"
            element={
              <p role="status">{t('error', { defaultValue: '404' })}</p>
            }
          />
        </Routes>
      </main>
    </>
  );
}
