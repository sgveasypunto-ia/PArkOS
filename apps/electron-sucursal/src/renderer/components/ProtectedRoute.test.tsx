/**
 * `<ProtectedRoute>` — auth + sesión guard unit tests (REQ-OPS-136 canon).
 *
 * Refactor 2026-09-17: ProtectedRoute ahora consume `useSesionActiva()`
 * (F3.3 T1) y rutea según sesion:
 *
 *   | isAuth | sesion | ruta actual         | resultado             |
 *   |--------|--------|---------------------|----------------------|
 *   | false  | -      | *                   | <Navigate to /login> |
 *   | true   | null   | /caja/abrir-turno   | render children      |
 *   | true   | null   | other               | <Navigate to abrir>  |
 *   | true   | value  | /caja/abrir-turno   | <Navigate to />      |
 *   | true   | value  | other               | render children      |
 *
 * `*Loading` states (auth bootstrap + sesion SWR) render Skeleton neutral.
 *
 * Defense in depth: Dashboard.tsx ALSO checks `sesion === null` (REQ-OPS-123)
 * and redirects. With ProtectedRoute doing the redirect upstream, Dashboard
 * never renders with `sesion === null`, so its useEffect is a no-op. Both
 * checks stay (belt-and-suspenders) — none of these tests touch Dashboard.
 */
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// Mock auth + sesion hooks. Other consumers (Dashboard) mock these too;
// we keep them isolated here to test ProtectedRoute's guard chain.
const mockUseAuth = vi.fn();
const mockUseSesionActiva = vi.fn();

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => mockUseAuth(),
}));
vi.mock('../../features/caja/hooks/useSesionActiva', () => ({
  useSesionActiva: () => mockUseSesionActiva(),
}));

// Import AFTER mocks so the component reads the mocked hooks.
import { ProtectedRoute } from './ProtectedRoute';

function renderAt(path: string): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/caja/abrir-turno"
          element={
            <ProtectedRoute>
              <div data-testid="abrir-turno-page">AbrirTurno</div>
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboard-test"
          element={
            <ProtectedRoute>
              <div data-testid="dashboard-page">Dashboard</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div data-testid="login-page">Login</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('<ProtectedRoute /> — auth + sesion guard (REQ-OPS-136)', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseSesionActiva.mockReset();
  });

  it('R1: loading (auth loading) → skeleton, no redirect', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, isLoading: true });
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderAt('/dashboard-test');
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).toBeNull();
    expect(screen.queryByTestId('dashboard-page')).toBeNull();
  });

  it('R2: loading (sesion loading) → skeleton, no redirect', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: true, isLoading: false });
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: true,
      error: undefined,
      refresh: vi.fn(),
    });
    renderAt('/dashboard-test');
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByTestId('dashboard-page')).toBeNull();
  });

  it('R3: !isAuthenticated → redirect /login regardless of sesion', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, isLoading: false });
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderAt('/dashboard-test');
    expect(screen.getByTestId('login-page')).toBeInTheDocument();
  });

  it('R4: isAuthenticated + sesion=null + ruta=/dashboard → redirect /caja/abrir-turno', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: true, isLoading: false });
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderAt('/dashboard-test');
    expect(screen.getByTestId('abrir-turno-page')).toBeInTheDocument();
    expect(screen.queryByTestId('dashboard-page')).toBeNull();
  });

  it('R5: isAuthenticated + sesion=null + ruta=/caja/abrir-turno → render children (no redirect loop)', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: true, isLoading: false });
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderAt('/caja/abrir-turno');
    expect(screen.getByTestId('abrir-turno-page')).toBeInTheDocument();
  });

  it('R6: isAuthenticated + sesion=active + ruta=/caja/abrir-turno → redirect / (operador ya tiene turno)', () => {
    const sesion = { uuid: 'sess-uuid-123', uuid_usuario: 'usr-1', uuid_sucursal: 'suc-1' };
    mockUseAuth.mockReturnValue({ isAuthenticated: true, isLoading: false });
    mockUseSesionActiva.mockReturnValue({
      sesion,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderAt('/caja/abrir-turno');
    expect(screen.queryByTestId('abrir-turno-page')).toBeNull();
    expect(screen.queryByTestId('dashboard-page')).toBeNull();
    // The redirect lands at "/" which has no <Route> defined above, so React
    // Router renders an empty Routes tree. We assert that NEITHER page rendered.
  });

  it('R7: isAuthenticated + sesion=active + ruta=/dashboard → render children', () => {
    const sesion = { uuid: 'sess-uuid-123', uuid_usuario: 'usr-1', uuid_sucursal: 'suc-1' };
    mockUseAuth.mockReturnValue({ isAuthenticated: true, isLoading: false });
    mockUseSesionActiva.mockReturnValue({
      sesion,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderAt('/dashboard-test');
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
  });

  it('R8: isAuthenticated + sesion=active + any path → render children', () => {
    // F11.3 follow-up -- the legacy /caja/cerrar-turno route was
    // retired (the close flow now lives in a right-side drawer via
    // <CerrarTurnoSheet />). This test now uses a generic path to
    // verify the basic "authenticated + active sesion = render
    // children" invariant for any route the operator lands on.
    const sesion = { uuid: 'sess-uuid-123', uuid_usuario: 'usr-1', uuid_sucursal: 'suc-1' };
    mockUseAuth.mockReturnValue({ isAuthenticated: true, isLoading: false });
    mockUseSesionActiva.mockReturnValue({
      sesion,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderAt('/dashboard-test');
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
  });
});