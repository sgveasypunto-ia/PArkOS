import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

import { StatusBar } from './components/StatusBar';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Login } from '../features/auth/pages/Login';
import { Dashboard } from '../features/caja/pages/Dashboard';
import { AbrirTurno } from '../features/caja/pages/AbrirTurno';
import { CerrarTurno } from '../features/caja/pages/CerrarTurno';

/**
 * App — F2.1 placeholder router + F2.3 StatusBar mount + F3.1 Login route +
 * F3.3 caja routes (Dashboard wire `/`, `/caja/abrir-turno`, `/caja/cerrar-turno`).
 *
 * The root renders a semantic `<main>` with one `<h1>` so axe-core's
 * WCAG 2.1 AA audit (RNF-022) is satisfied from day one. Subsequent
 * HU (F2.2+, F3.x) attach their routes here. F2.3 mounts the
 * `<StatusBar />` above `<main>` so backend health is always visible
 * (DEC-UPD-12). F3.1 añade `<Route path="/login">` — entry point del
 * flujo de autenticación (post-`POST /auth/login` con credentials:'include',
 * `useAuth()` hidrata y redirige a `/` con `user` resuelto, sin flash).
 *
 * F3.3 MODIFY — registra 3 rutas del feature caja (DEC-F3.3-05):
 *   - `/` → `<Dashboard />` (redirige según sesión activa o renderiza TurnoActivoPanel).
 *   - `/caja/abrir-turno` → `<AbrirTurno />` (form apertura).
 *   - `/caja/cerrar-turno` → `<CerrarTurno />` (form cierre placeholder F10.x completa).
 *   Reemplaza la ruta F3.1+F3.2 placeholder `<Route path="/" element={null} />`.
 */
export default function App() {
  const { t } = useTranslation('common');

  return (
    <>
      <StatusBar />
      <main
        lang="es-CO"
        className="flex min-h-[calc(100vh-2rem)] items-center justify-center bg-muted/40 p-4"
      >
        <div className="w-full max-w-md">
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
        </div>
      </main>
    </>
  );
}
