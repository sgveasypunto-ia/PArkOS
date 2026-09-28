/**
 * `App.unauthenticated.test.tsx` — Separated file because Vitest hoists
 * `vi.mock` above imports, so a single file cannot have two different
 * auth states. This file mocks `useAdminAuth` as unauthenticated and
 * asserts that the route guard redirects `/dashboard` to `/login`.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';
import { SucursalProvider } from '@/lib/sucursal-context';
import App from './App';

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: null,
    rol: null,
    sucursalUuids: [],
    permisos: [],
    isAuthenticated: false,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

function Providers({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <SWRConfig value={{ provider: () => new Map() }}>
      <SucursalProvider>{children}</SucursalProvider>
    </SWRConfig>
  );
}

describe('App (unauthenticated)', () => {
  beforeEach(() => {
    // Even with stale storage, the auth gate fires before the branch
    // gate. Clearing the key keeps the test deterministic.
    window.localStorage.removeItem('parkos.lastSelectedSucursal');
  });

  it('redirects /dashboard to /login', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/dashboard']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('page-login')).toBeInTheDocument();
  });

  it('redirects /seleccionar-sucursal to /login', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/seleccionar-sucursal']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('page-login')).toBeInTheDocument();
  });

  it('redirects / to /login', () => {
    render(
      <Providers>
        <MemoryRouter initialEntries={['/']}>
          <App />
        </MemoryRouter>
      </Providers>,
    );
    expect(screen.getByTestId('page-login')).toBeInTheDocument();
  });
});
