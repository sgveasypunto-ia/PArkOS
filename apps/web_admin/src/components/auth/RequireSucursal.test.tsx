import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { SucursalProvider } from '@/lib/sucursal-context';

/**
 * Mock factory reads the current auth state from `globalThis` so each
 * test can swap the return value without re-importing the module
 * (Vitest hoists `vi.mock` above imports).
 */
const { setAuthState } = vi.hoisted(() => ({
  setAuthState: (
    v:
      | { isLoading: true; sucursalUuids: string[] }
      | { isLoading: false; sucursalUuids: [] }
      | { isLoading: false; sucursalUuids: string[] },
  ): void => {
    (globalThis as { __SUCURSAL_AUTH_STATE?: unknown }).__SUCURSAL_AUTH_STATE = v;
  },
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => {
    const state = (globalThis as { __SUCURSAL_AUTH_STATE?: unknown })
      .__SUCURSAL_AUTH_STATE as
      | { isLoading: true; sucursalUuids: string[] }
      | { isLoading: false; sucursalUuids: [] }
      | { isLoading: false; sucursalUuids: string[] }
      | undefined;
    if (!state) {
      return { isLoading: false, sucursalUuids: [] };
    }
    return state;
  },
}));

import { RequireSucursal } from './RequireSucursal';

function Page({ id }: { id: string }): JSX.Element {
  return <div data-testid={id}>rendered</div>;
}

function renderAt(initialEntry: string) {
  return render(
    <SucursalProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route element={<RequireSucursal />}>
            <Route path="/dashboard" element={<Page id="page-dashboard" />} />
          </Route>
          <Route
            path="/seleccionar-sucursal"
            element={<Page id="page-seleccionar-sucursal" />}
          />
          <Route path="/forbidden" element={<Page id="page-forbidden" />} />
        </Routes>
      </MemoryRouter>
    </SucursalProvider>,
  );
}

const UUID_OK = '11111111-1111-1111-1111-111111111111';

describe('RequireSucursal', () => {
  beforeEach(() => {
    window.localStorage.removeItem('parkos.lastSelectedSucursal');
  });

  it('renders loading state while useAdminAuth is loading', () => {
    setAuthState({ isLoading: true, sucursalUuids: [] });
    renderAt('/dashboard');
    expect(screen.getByTestId('require-sucursal-loading')).toBeInTheDocument();
  });

  it('redirects to /forbidden when the admin has no permitted branches', async () => {
    setAuthState({ isLoading: false, sucursalUuids: [] });
    renderAt('/dashboard');
    await waitFor(() => {
      expect(screen.getByTestId('page-forbidden')).toBeInTheDocument();
    });
  });

  it('redirects to /seleccionar-sucursal when no branch is selected', async () => {
    setAuthState({ isLoading: false, sucursalUuids: [UUID_OK] });
    renderAt('/dashboard');
    await waitFor(() => {
      expect(screen.getByTestId('page-seleccionar-sucursal')).toBeInTheDocument();
    });
  });

  it('redirects to /seleccionar-sucursal when the persisted UUID is not permitted', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', 'revoked-uuid');
    setAuthState({ isLoading: false, sucursalUuids: [UUID_OK] });
    renderAt('/dashboard');
    await waitFor(() => {
      expect(screen.getByTestId('page-seleccionar-sucursal')).toBeInTheDocument();
    });
    // The guard clears stale selection so the picker truly starts fresh.
    expect(window.localStorage.getItem('parkos.lastSelectedSucursal')).toBeNull();
  });

  it('renders the protected Outlet when the persisted UUID is valid', () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', UUID_OK);
    setAuthState({ isLoading: false, sucursalUuids: [UUID_OK] });
    renderAt('/dashboard');
    expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
  });
});
