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

  it('renders the HomeHub at / (the post-login landing)', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    // The HomeHub is the canonical landing post-login. It is mounted
    // OUTSIDE `<RequireSucursal>`, so the picker must NOT take over.
    expect(screen.getByTestId('home-hub')).toBeInTheDocument();
    expect(screen.getByTestId('home-hub-card-sucursales')).toBeInTheDocument();
    expect(screen.getByTestId('home-hub-card-catalogos')).toBeInTheDocument();
    expect(screen.queryByTestId('sucursal-picker')).not.toBeInTheDocument();
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

  it('keeps /dashboard reachable as its own page, not aliased to the picker', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/dashboard']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.queryByTestId('sucursal-picker')).not.toBeInTheDocument();
  });

  it('mounts TopNav with branch nav on protected routes', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/dashboard']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    // TopNav with showBranchNav renders section nav + branch selector.
    expect(screen.getByTestId('topnav')).toBeInTheDocument();
    expect(screen.getByTestId('topnav-email')).toHaveTextContent('admin@parkos.local');
    expect(screen.getByRole('navigation')).toBeInTheDocument();
    expect(screen.getByTestId('chrome-sucursal-selector')).toBeInTheDocument();
  });

  it('mounts TopNav without branch nav on / (HomeHub is global)', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.queryByTestId('chrome-sucursal-selector')).not.toBeInTheDocument();
    // The identity bar is on every authed route.
    expect(screen.getByTestId('topnav')).toBeInTheDocument();
    expect(screen.getByTestId('topnav-email')).toHaveTextContent('admin@parkos.local');
  });

  it('mounts TopNav without branch nav on /catalogos (global, no branch scope)', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/catalogos']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.getByTestId('topnav')).toBeInTheDocument();
  });

  it('mounts TopNav without branch nav on /seleccionar-sucursal (authed picker)', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/seleccionar-sucursal']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.getByTestId('topnav')).toBeInTheDocument();
  });

  it('renders the /perfil placeholder inside the global authed group', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/perfil']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('page-perfil')).toBeInTheDocument();
    expect(screen.getByTestId('topnav')).toBeInTheDocument();
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
