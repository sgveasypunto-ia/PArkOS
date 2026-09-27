import { Route, Routes, Navigate } from 'react-router-dom';
import { Login } from '@/features/auth/pages/Login';
import { RequireAdmin } from '@/components/auth/RequireAdmin';
import Dashboard from '@/pages/Dashboard';
import SucursalesList from '@/features/sucursales/pages/SucursalesList';
import AuditDashboard from '@/features/audit/pages/AuditDashboard';
import UsuariosList from '@/features/admin/pages/UsuariosList';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/dashboard"
        element={
          <RequireAdmin>
            <Dashboard />
          </RequireAdmin>
        }
      />
      <Route
        path="/sucursales"
        element={
          <RequireAdmin>
            <SucursalesList />
          </RequireAdmin>
        }
      />
      <Route
        path="/admin/usuarios"
        element={
          <RequireAdmin>
            <UsuariosList />
          </RequireAdmin>
        }
      />
      <Route
        path="/audit"
        element={
          <RequireAdmin>
            <AuditDashboard />
          </RequireAdmin>
        }
      />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
