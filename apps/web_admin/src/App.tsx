import { Route, Routes, Navigate } from 'react-router-dom';
import { Login } from '@/features/auth/pages/Login';
import { RequireAdmin } from '@/components/auth/RequireAdmin';
import { WaitForAuth } from '@/components/WaitForAuth';
import { AdminChrome } from '@/components/chrome/AdminChrome';
import Home from '@/pages/Home';
import Dashboard from '@/pages/Dashboard';
import SucursalesList from '@/features/sucursales/pages/SucursalesList';
import AuditDashboard from '@/features/audit/pages/AuditDashboard';
import UsuariosList from '@/features/admin/pages/UsuariosList';
import Tarifas from '@/features/tarifas/pages/Tarifas';
import Cupos from '@/features/cupos/pages/Cupos';

/**
 * Route tree.
 *
 * The authenticated surface is a single layout route wrapping
 * `<AdminChrome />` (which renders `<Outlet />`), instead of repeating
 * `<RequireAdmin>` on every route. Same guard, one decision point.
 *
 * `/` is the hub; `/dashboard` stays the per-branch panel.
 * `/tarifas` and `/cupos` were added in PR-D-ui-tarifas-cupos.
 */
export default function App() {
  return (
    <WaitForAuth>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <RequireAdmin>
              <AdminChrome />
            </RequireAdmin>
          }
        >
          <Route path="/" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/sucursales" element={<SucursalesList />} />
          <Route path="/admin/usuarios" element={<UsuariosList />} />
          <Route path="/tarifas" element={<Tarifas />} />
          <Route path="/cupos" element={<Cupos />} />
          <Route path="/audit" element={<AuditDashboard />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </WaitForAuth>
  );
}
