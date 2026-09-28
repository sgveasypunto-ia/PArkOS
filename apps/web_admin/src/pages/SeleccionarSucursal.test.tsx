/**
 * SeleccionarSucursal.test.tsx -- unified page tests.
 *
 * Covers:
 *  - T1: default tab is "Seleccionar" (cards visible).
 *  - T2: clicking a card navigates to /dashboard.
 *  - T3: switching to "Administrar" tab shows the table.
 *  - T4: "Nueva sucursal" opens an empty form.
 *  - T5: clicking "Editar" opens the form pre-filled from the row.
 *  - T6: clicking "Token de pairing" opens the PairingTokenDialog.
 *  - T7: ?tab=admin query param lands directly on the admin tab.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { SWRConfig } from 'swr';

import { SucursalProvider } from '@/lib/sucursal-context';

vi.mock('@/features/sucursales/api/sucursalesApi', () => ({
  listSucursales: vi.fn(),
  createSucursal: vi.fn(),
  updateSucursal: vi.fn(),
  mintPairingToken: vi.fn(),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: { uuid: '00000000-0000-0000-0000-0000000000ad', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['11111111-1111-1111-1111-111111111111'],
    permisos: ['config_sucursal'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

import {
  listSucursales,
  createSucursal,
  updateSucursal,
  mintPairingToken,
} from '@/features/sucursales/api/sucursalesApi';
import SeleccionarSucursal from '@/pages/SeleccionarSucursal';

const mockedList = listSucursales as ReturnType<typeof vi.fn>;
const mockedCreate = createSucursal as ReturnType<typeof vi.fn>;
const mockedUpdate = updateSucursal as ReturnType<typeof vi.fn>;
const mockedPairing = mintPairingToken as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(
    SucursalProvider,
    null,
    createElement(
      SWRConfig,
      { value: { provider: (): never => new Map() as never } },
      children,
    ),
  );
}

function renderAt(initialEntries: string[]): void {
  render(
    createElement(
      wrapper,
      null,
      createElement(
        MemoryRouter,
        { initialEntries },
        createElement(
          Routes,
          null,
          createElement(Route, { path: '/dashboard', element: createElement('div', { 'data-testid': 'dashboard-target' }) }),
          createElement(Route, { path: '/seleccionar-sucursal', element: createElement(SeleccionarSucursal) }),
        ),
      ),
    ),
  );
}

const SUC_NORTE = {
  uuid: '11111111-1111-1111-1111-111111111111',
  nombre: 'Sucursal Norte',
  prefijo_nombre: 'BOG-NOR',
  direccion: null,
  telefono: null,
  ciudad: 'Bogota',
  horario: null,
  uuid_tipo_sucursal: null,
  uuid_empresa: null,
  vigente_desde: '2026-09-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-09-01T00:00:00',
  created_by: null,
  sync_status: null,
} as const;

beforeEach(() => {
  mockedList.mockReset();
  mockedCreate.mockReset();
  mockedUpdate.mockReset();
  mockedPairing.mockReset();
  // Default fetch OK for picker (admin_views endpoint); tests can override.
  globalThis.fetch = vi.fn(async () =>
    new Response(JSON.stringify({ items: [SUC_NORTE] }), { status: 200 }),
  ) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.removeItem('parkos.lastSelectedSucursal');
});

describe('SeleccionarSucursal unified page', () => {
  it('T1: defaults to the Seleccionar tab with cards', async () => {
    mockedList.mockResolvedValue([SUC_NORTE]);
    renderAt(['/seleccionar-sucursal']);
    await waitFor(() => {
      expect(screen.getByTestId('sucursal-picker')).toBeInTheDocument();
    });
    expect(screen.getByTestId('sucursal-tab-seleccionar')).toHaveAttribute(
      'data-state',
      'active',
    );
  });

  it('T2: clicking a card navigates to /dashboard', async () => {
    const user = userEvent.setup();
    mockedList.mockResolvedValue([SUC_NORTE]);
    renderAt(['/seleccionar-sucursal']);
    await waitFor(() =>
      expect(
        screen.getByTestId('sucursal-picker-option-11111111-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await user.click(
      screen.getByTestId('sucursal-picker-option-11111111-1111-1111-1111-111111111111'),
    );
    await waitFor(() => {
      expect(screen.getByTestId('dashboard-target')).toBeInTheDocument();
    });
  });

  it('T3: switching to Administrar tab shows the table', async () => {
    const user = userEvent.setup();
    mockedList.mockResolvedValue([SUC_NORTE]);
    renderAt(['/seleccionar-sucursal']);
    await user.click(screen.getByTestId('sucursal-tab-admin'));
    await waitFor(() => {
      expect(
        screen.getByTestId('sucursal-row-11111111-1111-1111-1111-111111111111'),
      ).toBeInTheDocument();
    });
  });

  it('T4: "Nueva sucursal" opens an empty form', async () => {
    const user = userEvent.setup();
    mockedList.mockResolvedValue([]);
    renderAt(['/seleccionar-sucursal?tab=admin']);
    await waitFor(() =>
      expect(screen.getByTestId('sucursal-empty')).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId('sucursal-new'));
    expect(screen.getByTestId('sucursal-form-card')).toBeInTheDocument();
    const nombre = screen.getByTestId('sucursal-field-nombre') as HTMLInputElement;
    expect(nombre.value).toBe('');
  });

  it('T5: clicking "Editar" opens the form pre-filled from the row', async () => {
    const user = userEvent.setup();
    mockedList.mockResolvedValue([SUC_NORTE]);
    renderAt(['/seleccionar-sucursal?tab=admin']);
    await waitFor(() =>
      expect(
        screen.getByTestId('sucursal-edit-11111111-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await user.click(
      screen.getByTestId('sucursal-edit-11111111-1111-1111-1111-111111111111'),
    );
    expect(screen.getByTestId('sucursal-form-editing')).toBeInTheDocument();
    const nombre = screen.getByTestId('sucursal-field-nombre') as HTMLInputElement;
    const prefijo = screen.getByTestId('sucursal-field-prefijo') as HTMLInputElement;
    expect(nombre.value).toBe('Sucursal Norte');
    expect(prefijo.value).toBe('BOG-NOR');
  });

  it('T6: clicking "Token de pairing" opens the PairingTokenDialog', async () => {
    const user = userEvent.setup();
    mockedList.mockResolvedValue([SUC_NORTE]);
    mockedPairing.mockResolvedValue({
      token: 'tk-test',
      expires_at: '2099-01-01T00:00:00',
      sucursal_uuid: SUC_NORTE.uuid,
    });
    renderAt(['/seleccionar-sucursal?tab=admin']);
    await waitFor(() =>
      expect(
        screen.getByTestId('sucursal-pairing-11111111-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await user.click(
      screen.getByTestId('sucursal-pairing-11111111-1111-1111-1111-111111111111'),
    );
    await waitFor(() => {
      expect(screen.getByTestId('pairing-token-dialog')).toBeInTheDocument();
    });
    expect(screen.getByTestId('pairing-token-value').textContent).toBe('tk-test');
  });

  it('T7: ?tab=admin query param lands directly on the Administrar tab', async () => {
    mockedList.mockResolvedValue([SUC_NORTE]);
    renderAt(['/seleccionar-sucursal?tab=admin']);
    await waitFor(() =>
      expect(
        screen.getByTestId('sucursal-row-11111111-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    expect(screen.getByTestId('sucursal-tab-admin')).toHaveAttribute(
      'data-state',
      'active',
    );
  });
});
