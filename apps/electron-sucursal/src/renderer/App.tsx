import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

import { StatusBar } from './components/StatusBar';
import { TurnoActivoBadge } from './components/TurnoActivoBadge';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Login } from '../features/auth/pages/Login';
import { Dashboard } from '../features/caja/pages/Dashboard';
import { AbrirTurno } from '../features/caja/pages/AbrirTurno';
import { CerrarTurno } from '../features/caja/pages/CerrarTurno';

/**
 * App — F2.1 router + F2.3 StatusBar mount + F3.1 Login + F3.3 caja
 * routes + REQ-OPS-140 (PR-6 of operador-dashboard-hub): the global
 * `<OcupacionStrip />` mount at the old L48 has been removed; the
 * occupancy panel now lives ONLY inside `<Dashboard />` so it does
 * not poll the API on `/caja/abrir-turno` and `/caja/cerrar-turno`
 * (F4.3 "TEMPORAL" comment honoured).
 *
 * Layout: full-bleed (no centered max-width) so the 6-section dashboard
 * uses the whole viewport without scroll at 1080p. The persistent
 * `<TurnoActivoBadge />` floats top-right and remains visible across
 * ALL routes (login excluded) so the operator always has a corner-anchored
 * read on whether they have a turno open — even when a drawer covers
 * most of the viewport.
 *
 * The root renders a semantic `<main>` with one `<h1>` so axe-core's
 * WCAG 2.1 AA audit (RNF-022) is satisfied from day one.
 */
export default function App(): JSX.Element {
  const { t } = useTranslation('common');

  return (
    <>
      <StatusBar />
      <TurnoActivoBadge />
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
