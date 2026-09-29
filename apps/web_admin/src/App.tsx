import { Route, Routes, Navigate, Outlet } from 'react-router-dom';
import { Login } from '@/features/auth/pages/Login';
import { RequireAdmin } from '@/components/auth/RequireAdmin';
import { RequireSucursal } from '@/components/auth/RequireSucursal';
import { WaitForAuth } from '@/components/WaitForAuth';
import { AdminChrome } from '@/components/chrome/AdminChrome';
import HomeHub from '@/pages/HomeHub';
import Dashboard from '@/pages/Dashboard';
import SeleccionarSucursal from '@/pages/SeleccionarSucursal';
import CatalogPage from '@/features/catalogos/CatalogPage';
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
 * Global routes (`/`) sit in their own
 * `<RequireAdmin><Outlet/></RequireAdmin>` group OUTSIDE the branch
 * guard. They render without the `<AdminChrome />`, so no
 * `SucursalSelectorBadge` and no `BranchSelector` are mounted — the
 * admin reaches them on first login, before confirming a branch.
 * The HomeHub links to `/seleccionar-sucursal` to opt into the
 * branch-scoped surface.
 *
 * DEC-LOGIN-07 revisado: el post-login ya no fuerza
 * `/seleccionar-sucursal`. El admin aterriza en `/` (HomeHub). La
 * decisión previa (siempre re-confirmar sucursal) está revertida; el
 * comentario histórico vive en `Login.tsx::getNextPath`.
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

        {/* Global routes — auth required, NO branch required.
            `Catalogos` is a tenant-global surface (DEC-CATALOG-01),
            so it sits OUTSIDE `<RequireSucursal>` — pineado by
            `App.test.tsx` "does NOT mount the chrome on /catalogos". */}
        <Route
          element={
            <RequireAdmin>
              <Outlet />
            </RequireAdmin>
          }
        >
          <Route path="/" element={<HomeHub />} />
          <Route path="/catalogos" element={<CatalogPage />} />
        </Route>

        {/* Branch-scoped routes — auth + branch required, render inside AdminChrome. */}
        <Route
          element={
            <RequireAdmin>
              <RequireSucursal>
                <AdminChrome />
              </RequireSucursal>
            </RequireAdmin>
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />
          <Route
            path="/sucursales"
            element={<Navigate to="/seleccionar-sucursal?tab=admin" replace />}
          />
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
