import { Route, Routes, Navigate, Outlet } from 'react-router-dom';
import { Login } from '@/features/auth/pages/Login';
import { RequireAdmin } from '@/components/auth/RequireAdmin';
import { RequireSucursal } from '@/components/auth/RequireSucursal';
import { WaitForAuth } from '@/components/WaitForAuth';
import { AdminChrome } from '@/components/chrome/AdminChrome';
import { TopNav } from '@/components/chrome/TopNav';
import HomeHub from '@/pages/HomeHub';
import Dashboard from '@/features/dashboard/pages/Dashboard';
import SeleccionarSucursal from '@/pages/SeleccionarSucursal';
import Perfil from '@/pages/Perfil';
import CatalogPage from '@/features/catalogos/CatalogPage';
import EmpresaPage from '@/features/empresa/pages/EmpresaPage';
import AuditDashboard from '@/features/audit/pages/AuditDashboard';
import UsuariosList from '@/features/admin/pages/UsuariosList';
import { UsuarioDetalle } from '@/features/usuarios/pages/UsuarioDetalle';
import SucursalDetalle from '@/features/parametrizacion/pages/SucursalDetalle';
import Tarifas from '@/features/tarifas/pages/Tarifas';
import Cupos from '@/features/cupos/pages/Cupos';
import TiposVehiculo from '@/features/tipos-vehiculo/pages/TiposVehiculo';
import TipoTarifa from '@/features/tipo-tarifa/pages/TipoTarifa';
import ConfiguracionTolerancias from '@/features/configuracion-tolerancias/pages/ConfiguracionTolerancias';
import ConfiguracionSeguridad from '@/features/configuracion-seguridad/pages/ConfiguracionSeguridad';
import Reporteria from '@/features/reporteria/pages/Reporteria';
import { ArqueosPage } from '@/features/arqueos/pages/ArqueosPage';

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
 * TopNav (identity: email + profile + logout) wraps EVERY authed
 * group — global, picker, and branch-scoped alike. In branch-scoped
 * routes, `showBranchNav` is passed so TopNav also renders the section
 * nav and branch selector. The `<AdminChrome />` is now just a layout
 * wrapper for the Outlet.
 *
 * DEC-LOGIN-07 revisado: el post-login ya no fuerza
 * `/seleccionar-sucursal`. El admin aterriza en `/` (HomeHub). La
 * decisión previa (siempre re-confirmar sucursal) está revertida; el
 * comentario histórico vive en `Login.tsx::getNextPath`.
 *
 * `/admin/usuarios` y `/gestion-usuarios` son redirects permanentes a
 * `/usuarios` (PR1 of the admin redesign + HU-F16) para que los links
 * antiguos sigan funcionando mientras la app apunta al nombre canónico.
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
              <TopNav />
              <SeleccionarSucursal />
            </RequireAdmin>
          }
        />

        {/* Global routes — auth required, NO branch required.
            `Catalogos`, `Empresa`, and `Usuarios` are tenant-global
            surfaces (DEC-CATALOG-01), so they sit OUTSIDE
            `<RequireSucursal>`. The TopNav wraps them so the operator
            always sees their identity + logout even before picking a
            branch — pineado by `App.test.tsx` "mounts TopNav but NOT
            AdminChrome on /". */}
        <Route
          element={
            <RequireAdmin>
              <TopNav />
              <Outlet />
            </RequireAdmin>
          }
        >
          <Route path="/" element={<HomeHub />} />
          <Route path="/catalogos" element={<CatalogPage />} />
          <Route path="/empresa" element={<EmpresaPage />} />
          <Route path="/usuarios" element={<UsuariosList />} />
          <Route path="/usuarios/:uuid" element={<UsuarioDetalle />} />
          {/* HU-F15.1: detalle de sucursal (datos generales + tabs de
              parametrización). Global como `/empresa` y `/usuarios/:uuid`
              -- gestionar UNA sucursal no requiere tener una sucursal
              ACTIVA seleccionada en el topbar (ver `lib/sucursal-context`),
              así que vive fuera de `<RequireSucursal>`. El único flujo
              existente de selección de sucursal (`SeleccionarSucursal.tsx`,
              modal de edición embebido) queda intacto: esta ruta es
              ADICIONAL, no un reemplazo. */}
          <Route path="/sucursales/:uuid" element={<SucursalDetalle />} />
          <Route path="/arqueos" element={<ArqueosPage />} />
          <Route path="/perfil" element={<Perfil />} />
        </Route>

        {/* Branch-scoped routes — auth + branch required, render inside AdminChrome.
            TopNav wraps the whole branch-scoped group as the identity bar.
            AdminChrome is just a layout wrapper for the Outlet. */}
        <Route
          element={
            <RequireAdmin>
              <TopNav />
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
          <Route
            path="/gestion-usuarios"
            element={<Navigate to="/usuarios" replace />}
          />
          <Route
            path="/admin/usuarios"
            element={<Navigate to="/usuarios" replace />}
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
          <Route path="/reporteria" element={<Reporteria />} />
          <Route path="/audit" element={<AuditDashboard />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </WaitForAuth>
  );
}
