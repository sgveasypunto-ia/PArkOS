import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';
import { SucursalProvider } from '@/lib/sucursal-context';
import App from './App';

// Default mock: authenticated. The "redirect when unauthenticated"
// test is in its own file (App.unauthenticated.test.tsx) because
// Vitest hoists `vi.mock` above imports and there is no per-test
// mock override once the module is loaded.
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({
    user: { actor_uuid: '00000000-0000-0000-0000-0000000000ad' },
    sucursal: null,
    sucursalesPermitidas: [],
    permisos: [],
    expiresAt: null,
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
  }),
}));

function Providers({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <SWRConfig value={{ provider: () => new Map() }}>
      <SucursalProvider>{children}</SucursalProvider>
    </SWRConfig>
  );
}

describe('App (authenticated)', () => {
  it('redirects the root path to /dashboard and renders the dashboard heading', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
  });

  it('redirects /login to /dashboard when already authenticated', () => {
    // DEC-LOGIN-07: an already-authenticated user who hits /login
    // bounces to /dashboard. Verify by looking for the dashboard
    // sentinel.
    render(
      <Providers>
        <MemoryRouter initialEntries={['/login']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
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
});
