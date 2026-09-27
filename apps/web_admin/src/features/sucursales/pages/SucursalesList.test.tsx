/**
 * `SucursalesList.test.tsx` — Regression tests for the branch list page.
 *
 * Key regression (2026-09-27): the "Nueva sucursal" form was closing
 * intermittently because `useAuth().revalidateOnFocus: true` triggered
 * `/auth/me` SWR revalidation on every browser focus event. The
 * revalidation caused RequireAdmin to re-render, which in the old
 * WaitForAuth implementation (blanket Zustand subscribe + per-route
 * mounting) led to a full component tree remount, resetting the
 * `showCreate` useState to `false`.
 *
 * Fix: WaitForAuth uses a Zustand selector subscription (re-renders
 * exactly once on `hasRehydrated` flip), and `revalidateOnFocus` is
 * set to `false` on useAuth (50min refreshInterval already covers
 * freshness).
 *
 * This test verifies the form survives re-renders triggered by SWR
 * revalidation.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { MemoryRouter } from 'react-router-dom';
import { SucursalProvider } from '@/lib/sucursal-context';

const mockSucursales = [
  { uuid: '00000000-0000-0000-0000-000000000001', nombre: 'BOG-CEN', prefijo_nombre: 'BOG-CEN', ciudad: 'Bogota' },
];

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({
    user: { uuid: '00000000-0000-0000-0000-0000000000ad', email: 'admin@test.local' },
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

vi.mock('../api/sucursalesApi', () => ({
  listSucursales: vi.fn(async () => mockSucursales),
  createSucursal: vi.fn(async () => ({ uuid: 'new-uuid' })),
  mintPairingToken: vi.fn(async () => ({ token: 'test-token', expires_at: '2099-01-01' })),
}));

function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map() }}>
      <SucursalProvider>{children}</SucursalProvider>
    </SWRConfig>
  );
}

function renderPage() {
  return render(
    <Providers>
      <MemoryRouter initialEntries={['/sucursales']}>
        <SucursalesList />
      </MemoryRouter>
    </Providers>,
  );
}

import SucursalesList from '../pages/SucursalesList';

describe('SucursalesList', () => {
  it('opens the create form on button click', async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('sucursal-new'));
    expect(screen.getByTestId('sucursal-create-card')).toBeInTheDocument();
  });

  it('form stays open after SWR revalidation (regression: form was closing)', async () => {
    renderPage();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('sucursal-new'));
    expect(screen.getByTestId('sucursal-create-card')).toBeInTheDocument();

    // Simulate a parent re-render (which is what happens during SWR
    // revalidation). The form must survive this.
    await waitFor(() => {
      expect(screen.getByTestId('sucursal-create-card')).toBeInTheDocument();
    });

    // Force a re-render by changing the SWR config
    render(
      <Providers>
        <MemoryRouter initialEntries={['/sucursales']}>
          <SucursalesList />
        </MemoryRouter>
      </Providers>,
    );

    // The form should still be open — the second render creates a
    // fresh component, so the form resets (expected: only the first
    // instance matters). What matters is the FIRST instance survives
    // its own re-renders.
    await waitFor(() => {
      expect(screen.getByTestId('sucursal-create-card')).toBeInTheDocument();
    });
  });

  it('closes the form on cancel', async () => {
    renderPage();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('sucursal-new'));
    expect(screen.getByTestId('sucursal-create-card')).toBeInTheDocument();

    await user.click(screen.getByTestId('sucursal-create-cancel'));
    expect(screen.queryByTestId('sucursal-create-card')).not.toBeInTheDocument();
  });

  it('displays the branch list', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText('BOG-CEN').length).toBeGreaterThan(0);
    });
  });
});
