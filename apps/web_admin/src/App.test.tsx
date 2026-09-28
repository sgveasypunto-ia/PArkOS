import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';
import { SucursalProvider } from '@/lib/sucursal-context';
import App from './App';

// Default mock: authenticated admin with one permitted branch.
// The "redirect when unauthenticated" test is in its own file
// (App.unauthenticated.test.tsx) because Vitest hoists `vi.mock` above
// imports and there is no per-test mock override once the module is
// loaded.
//
// `useAdminAuth` is the hook this app actually runs on: `/auth/me` is
// hardcoded to the `operador-` issuer and 404s for admin tokens, so
// `useAuth` would hand every component a permanently null profile.
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: { uuid: '00000000-0000-0000-0000-0000000000ad', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['2049f2cd-b2a8-4e45-9d19-31fa87eb67c6'],
    permisos: ['admin_usuarios', 'audit_read', 'config_sucursal'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

const ALLOWED_UUID = '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6';

function Providers({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <SWRConfig value={{ provider: () => new Map() }}>
      <SucursalProvider>{children}</SucursalProvider>
    </SWRConfig>
  );
}

describe('App (authenticated)', () => {
  beforeEach(() => {
    // The branch gate (PR1) forces every protected route through a
    // valid `parkos.lastSelectedSucursal` selection. Tests that aim
    // at protected surfaces seed the storage key here.
    window.localStorage.setItem('parkos.lastSelectedSucursal', ALLOWED_UUID);
  });

  it('renders the hub at the root path', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('page-home')).toBeInTheDocument();
  });

  it('renders every real section on the hub, including gated Auditoría', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('home-card-dashboard')).toBeInTheDocument();
    expect(screen.getByTestId('home-card-sucursales')).toBeInTheDocument();
    expect(screen.getByTestId('home-card-gestion-usuarios')).toBeInTheDocument();
    expect(screen.getByTestId('home-card-auditoria')).toBeInTheDocument();
  });

  it('renders the dashboard page on /dashboard when authenticated', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/dashboard']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
  });

  it('keeps /dashboard reachable as its own page, not aliased to the hub', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/dashboard']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.queryByTestId('page-home')).not.toBeInTheDocument();
  });

  it('mounts the persistent chrome with a logout control', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('admin-chrome')).toBeInTheDocument();
    expect(screen.getByTestId('admin-logout')).toBeInTheDocument();
  });

  it('renders the branch selector badge in the chrome', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('chrome-sucursal-selector')).toBeInTheDocument();
  });

  it('redirects /admin/usuarios to /gestion-usuarios', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/admin/usuarios']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('page-usuarios')).toBeInTheDocument();
  });

  it('redirects to /seleccionar-sucursal when the branch gate finds no selection', () => {
    window.localStorage.removeItem('parkos.lastSelectedSucursal');
    render(
      <Providers>
        <MemoryRouter initialEntries={['/dashboard']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    // The picker renders the loading state inside `<SucursalPicker />`
    // because `isLoading` for the SWR is true under jsdom; either the
    // picker or its loading shim is enough to prove the gate fired.
    expect(screen.getByTestId('sucursal-picker')).toBeInTheDocument();
  });
});
