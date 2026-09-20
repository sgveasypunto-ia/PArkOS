import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

import { StatusBar } from './components/StatusBar';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Login } from '../features/auth/pages/Login';
import { Dashboard } from '../features/caja/pages/Dashboard';
import { AbrirTurno } from '../features/caja/pages/AbrirTurno';
import { CerrarTurno } from '../features/caja/pages/CerrarTurno';
import { FacturaDetalle } from '../features/facturacion/pages/FacturaDetalle';
import { ReimprimirTiquete } from '../features/facturacion/pages/ReimprimirTiquete';
import { Venta } from '../features/suscripciones/pages/Venta';
import { Listado } from '../features/suscripciones/pages/Listado';

/**
 * App — F2.1 router + F2.3 StatusBar mount + F3.1 Login + F3.3 caja
 * routes + REQ-OPS-140 (PR-6 of operador-dashboard-hub): the global
 * `<OcupacionStrip />` mount at the old L48 has been removed; the
 * occupancy panel now lives ONLY inside `<Dashboard />` so it does
 * not poll the API on `/caja/abrir-turno` and `/caja/cerrar-turno`
 * (F4.3 "TEMPORAL" comment honoured).
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

  return (
    <>
      <StatusBar />
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
            path="/caja/cerrar-turno"
            element={
              <ProtectedRoute>
                <CerrarTurno />
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
