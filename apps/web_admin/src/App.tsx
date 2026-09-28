import { Route, Routes, Navigate } from 'react-router-dom';
import { Login } from '@/features/auth/pages/Login';
import { RequireAdmin } from '@/components/auth/RequireAdmin';
import { RequireSucursal } from '@/components/auth/RequireSucursal';
import { WaitForAuth } from '@/components/WaitForAuth';
import { AdminChrome } from '@/components/chrome/AdminChrome';
import Home from '@/pages/Home';
import Dashboard from '@/pages/Dashboard';
import SeleccionarSucursal from '@/pages/SeleccionarSucursal';
import SucursalesList from '@/features/sucursales/pages/SucursalesList';
import AuditDashboard from '@/features/audit/pages/AuditDashboard';
import UsuariosList from '@/features/admin/pages/UsuariosList';
import Tarifas from '@/features/tarifas/pages/Tarifas';
import Cupos from '@/features/cupos/pages/Cupos';
import TiposVehiculo from '@/features/tipos-vehiculo/pages/TiposVehiculo';
import TipoTarifa from '@/features/tipo-tarifa/pages/TipoTarifa';
import ConfiguracionTolerancias from '@/features/configuracion-tolerancias/pages/ConfiguracionTolerancias';
import ConfiguracionSeguridad from '@/features/configuracion-seguridad/pages/ConfiguracionSeguridad';

/**
 * Route tree.
 *
 * Two layered guards:
 *   - `RequireAdmin` (auth) wraps everything except `/login`.
 *   - `RequireSucursal` (branch selection) wraps the authed+protected
 *     surface so any deep-link that bypasses the picker lands on
 *     `/seleccionar-sucursal` first.
 *
 * `/seleccionar-sucursal` sits OUTSIDE the branch guard (otherwise the
 * guard would redirect the picker back to itself in a loop). It is
 * still gated by `RequireAdmin` so an unauthenticated visitor never
 * sees it.
 *
 * `/admin/usuarios` is kept as a permanent redirect to
 * `/gestion-usuarios` (PR1 of the admin redesign) so old links still
 * resolve while the rest of the app points at the new canonical name.
 */
export default function App() {
  return (
    <WaitForAuth>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route
          path="/seleccionar-sucursal"
          element={
            <RequireAdmin>
              <SeleccionarSucursal />
            </RequireAdmin>
          }
        />

        <Route
          element={
            <RequireAdmin>
              <RequireSucursal>
                <AdminChrome />
              </RequireSucursal>
            </RequireAdmin>
          }
        >
          <Route path="/" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/sucursales" element={<SucursalesList />} />
          <Route path="/gestion-usuarios" element={<UsuariosList />} />
          <Route
            path="/admin/usuarios"
            element={<Navigate to="/gestion-usuarios" replace />}
          />
          <Route path="/tarifas" element={<Tarifas />} />
          <Route path="/cupos" element={<Cupos />} />
          <Route path="/tipos-vehiculo" element={<TiposVehiculo />} />
          <Route path="/tipo-tarifa" element={<TipoTarifa />} />
          <Route
            path="/configuracion-tolerancias"
            element={<ConfiguracionTolerancias />}
          />
          <Route
            path="/configuracion-seguridad"
            element={<ConfiguracionSeguridad />}
          />
          <Route path="/audit" element={<AuditDashboard />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </WaitForAuth>
  );
}
