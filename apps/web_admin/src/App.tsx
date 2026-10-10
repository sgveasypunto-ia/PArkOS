import { Route, Routes, Navigate, Outlet } from 'react-router-dom';
import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { Login } from '@/features/auth/pages/Login';
import { RequireAdmin } from '@/components/auth/RequireAdmin';
import { RequireSucursal } from '@/components/auth/RequireSucursal';
import { WaitForAuth } from '@/components/WaitForAuth';
import { AdminChrome } from '@/components/chrome/AdminChrome';
import { TopNav } from '@/components/chrome/TopNav';
import { AppSidebar } from '@/components/chrome/AppSidebar';
import GlobalHQ, { HUB_CARDS } from '@/pages/GlobalHQ';
import Dashboard from '@/features/dashboard/pages/Dashboard';
import SeleccionarSucursal from '@/pages/SeleccionarSucursal';
import Perfil from '@/pages/Perfil';
import CatalogPage from '@/features/catalogos/CatalogPage';
import EmpresaPage from '@/features/empresa/pages/EmpresaPage';
import AuditDashboard from '@/features/audit/pages/AuditDashboard';
import UsuariosList from '@/features/admin/pages/UsuariosList';
import { UsuarioDetalle } from '@/features/usuarios/pages/UsuarioDetalle';
import SucursalDetalle from '@/features/parametrizacion/pages/SucursalDetalle';
import ClientesList from '@/features/clientes/pages/ClientesList';
import ClienteDetalle from '@/features/clientes/pages/ClienteDetalle';
import Tarifas from '@/features/tarifas/pages/Tarifas';
import Cupos from '@/features/cupos/pages/Cupos';
import TiposVehiculo from '@/features/tipos-vehiculo/pages/TiposVehiculo';
import TipoTarifa from '@/features/tipo-tarifa/pages/TipoTarifa';
import ConfiguracionTolerancias from '@/features/configuracion-tolerancias/pages/ConfiguracionTolerancias';
import ConfiguracionSeguridad from '@/features/configuracion-seguridad/pages/ConfiguracionSeguridad';
import Reporteria from '@/features/reporteria/pages/Reporteria';
import ReporteriaFinanciera from '@/features/reporteria/pages/ReporteriaFinanciera';
import ReporteriaSuscripciones from '@/features/reporteria/pages/ReporteriaSuscripciones';
import { ArqueosPage } from '@/features/arqueos/pages/ArqueosPage';
import Pairing from '@/features/pairing/pages/Pairing';
import AlertasList from '@/features/alertas/pages/AlertasList';
import AlertaDetalle from '@/features/alertas/pages/AlertaDetalle';
import AnulacionesList from '@/features/workflows/pages/AnulacionesList';
import AnulacionDetalle from '@/features/workflows/pages/AnulacionDetalle';
import ReclamosList from '@/features/workflows/pages/ReclamosList';
import ReclamoDetalle from '@/features/workflows/pages/ReclamoDetalle';
import SyncDashboard from '@/features/sync/pages/SyncDashboard';
import DianCola from '@/features/dian/pages/DianCola';
import DianDetalle from '@/features/dian/pages/DianDetalle';
import LogTransaccional from '@/features/auditoria/pages/LogTransaccional';
import LogDetalle from '@/features/auditoria/pages/LogDetalle';
import HashChainVerify from '@/features/auditoria/pages/HashChainVerify';
import BuscarGlobal from '@/features/auditoria/pages/BuscarGlobal';

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
 * sees it. The picker is a focused, fullscreen experience — it does
 * NOT use the persistent sidebar.
 *
 * Chrome layout (post-sidebar refactor): `<TopNav /> + <AppSidebar />`
 * is a single layout shell that wraps EVERY authed route except
 * `/login` and `/seleccionar-sucursal`. The shell renders on `/`
 * (outside `<RequireSucursal>`) just fine: the sidebar is pure
 * navigation and the branch selector stays in `<TopNav>` where it
 * only mounts when `selected !== null` — so the H1 invariant
 * ("no branch-scoped chrome on /") is preserved. Pineado por
 * `App.test.tsx` "mounts TopNav AND AppSidebar but NOT AdminChrome
 * on /".
 *
 * Inside the shell, the global routes and the branch-scoped routes
 * are nested:
 *   - global routes (`/`, `/catalogos`, `/empresa`, ...) render
 *     directly as `<Outlet />` children.
 *   - branch-scoped routes (`/dashboard`, `/tarifas`, ...) nest a
 *     `<RequireSucursal><AdminChrome /></RequireSucursal>` route
 *     so the picker bounce happens before the route's page mounts.
 *
 * DEC-LOGIN-07 revisado: el post-login ya no fuerza
 * `/seleccionar-sucursal`. El admin aterriza en `/` (GlobalHQ). La
 * decisión previa (siempre re-confirmar sucursal) está revertida; el
 * comentario histórico vive en `Login.tsx::getNextPath`.
 *
 * `/admin/usuarios` y `/gestion-usuarios` son redirects permanentes a
 * `/usuarios` (PR1 of the admin redesign + HU-F16) para que los links
 * antiguos sigan funcionando mientras la app apunta al nombre canónico.
 */
export default function App() {
  const { permisos } = useAdminAuth();

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

        {/* Authed routes with persistent chrome. The shell renders
            TopNav (identity + branch switcher) AND AppSidebar (left
            nav with the 8 quick-launch items) for every route in
            this group. Branch-scoped routes nest RequireSucursal +
            AdminChrome so the picker bounce happens at the right
            level. */}
        <Route
          element={
            <RequireAdmin>
              <div className="flex min-h-screen flex-col">
                <TopNav />
                <div className="flex flex-1 min-h-0">
                  <AppSidebar items={HUB_CARDS} permisos={permisos} />
                  <Outlet />
                </div>
              </div>
            </RequireAdmin>
          }
        >
          {/* Global routes — auth required, NO branch required.
              `Catalogos`, `Empresa`, and `Usuarios` are tenant-global
              surfaces (DEC-CATALOG-01), so they sit OUTSIDE
              `<RequireSucursal>`. The chrome shell wraps them so
              the operator always sees their identity + logout even
              before picking a branch. */}
          <Route path="/" element={<GlobalHQ />} />
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
          {/* HU-F20.1: clientes directory + detail. Global like
              `/usuarios` and `/sucursales/:uuid` -- gestionar clientes is
              a tenant-wide, cross-branch surface, not branch-scoped, so
              it sits outside `<RequireSucursal>` alongside them. */}
          <Route path="/clientes" element={<ClientesList />} />
          <Route path="/clientes/:uuid" element={<ClienteDetalle />} />
          <Route path="/arqueos" element={<ArqueosPage />} />
          {/* HU-F19.3: pairing-token issuance/revoke. Cross-branch list
              (all sucursales, not just the one active in the topbar),
              so it sits here alongside /sucursales/:uuid and /arqueos
              rather than inside the <RequireSucursal> branch-scoped
              group below. */}
          <Route path="/pairing" element={<Pairing />} />
          {/* HU-F19.5: bandeja de alertas. Cross-branch (sucursales
              permitidas del actor, no solo la sucursal activa en el
              topbar) -- mismo motivo que /pairing y /arqueos para vivir
              acá en vez de dentro del grupo <RequireSucursal>. */}
          <Route path="/alertas" element={<AlertasList />} />
          <Route path="/alertas/:uuid" element={<AlertaDetalle />} />
          {/* HU-F20.3: anulaciones y reclamos -- transiciones reales
              sobre el mismo `[L-W]` workflow chain que alerta (HU-F19.5).
              Cross-branch cursor-paginated inbox -- mismo motivo que
              /alertas, /pairing y /arqueos para vivir acá en vez de
              dentro del grupo <RequireSucursal>. */}
          <Route path="/anulaciones" element={<AnulacionesList />} />
          <Route path="/anulaciones/:uuid" element={<AnulacionDetalle />} />
          <Route path="/reclamos" element={<ReclamosList />} />
          <Route path="/reclamos/:uuid" element={<ReclamoDetalle />} />
          {/* HU-F19.2: cross-branch sync monitoring dashboard (heatmap +
              resumen verde/amarillo/rojo, log, conflictos). Cross-branch
              by nature (same reasoning as /pairing just above), so it
              sits here instead of inside the <RequireSucursal> group
              below. */}
          <Route path="/sync" element={<SyncDashboard />} />
          {/* HU-F20.5: monitor de envíos DIAN (cola, reintento). Cross-branch
              (sucursales permitidas del actor), same reasoning as /alertas
              and /sync just above. */}
          <Route path="/dian" element={<DianCola />} />
          <Route path="/dian/:uuid" element={<DianDetalle />} />
          {/* HU-F20.4: bitácora cross-branch (log_transaccional), chain
              verification + global typeahead. Cross-branch by nature
              (same reasoning as /sync just above), so it sits here
              instead of inside the <RequireSucursal> group below. Not
              to be confused with /audit (IT-12, single-branch, ambient
              tenant context) below in the branch-scoped group -- that
              one stays untouched. */}
          <Route path="/auditoria/log" element={<LogTransaccional />} />
          <Route path="/auditoria/log/:uuid" element={<LogDetalle />} />
          <Route path="/auditoria/verify-chain" element={<HashChainVerify />} />
          <Route path="/auditoria/buscar" element={<BuscarGlobal />} />
          <Route path="/perfil" element={<Perfil />} />

          {/* Branch-scoped routes — auth + branch required, render inside AdminChrome.
              RequireSucursal inside the chrome shell redirects to the
              picker when no branch is selected. AdminChrome is just a
              layout wrapper for the Outlet (the persistent chrome
              already lives in the parent shell). */}
          <Route
            element={
              <RequireSucursal>
                <AdminChrome />
              </RequireSucursal>
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
            <Route
              path="/reporteria/financiera"
              element={<ReporteriaFinanciera />}
            />
            <Route
              path="/reporteria/suscripciones"
              element={<ReporteriaSuscripciones />}
            />
            <Route path="/audit" element={<AuditDashboard />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </WaitForAuth>
  );
}
