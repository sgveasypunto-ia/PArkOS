/**
 * ConfiguracionSeguridad — page-level integration tests.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/features/sucursales/api/sucursalesApi', () => ({
  listSucursales: vi.fn(),
}));

vi.mock('../api/configuracionSeguridadApi', () => ({
  listConfiguracionSeguridad: vi.fn(),
  getConfiguracionSeguridad: vi.fn(),
  getConfiguracionSeguridadEfectiva: vi.fn(),
  createConfiguracionSeguridad: vi.fn(),
  updateConfiguracionSeguridad: vi.fn(),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: { uuid: 'u-1', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['suc-1'],
    permisos: ['config_seguridad'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

import { useAuthStore } from '@parkos/ui-kit/store';
import { listConfiguracionSeguridad } from '../api/configuracionSeguridadApi';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import ConfiguracionSeguridad from './ConfiguracionSeguridad';

const mockedList = listConfiguracionSeguridad as ReturnType<typeof vi.fn>;
const mockedListSucursales = listSucursales as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

function fullWrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(MemoryRouter, null, createElement(wrapper, { children }));
}

const SUCURSAL = 'dddddddd-1111-1111-1111-111111111111';

const GLOBAL_ROW = {
  uuid: '11111111-1111-1111-1111-111111111111',
  uuid_sucursal: null,
  dias_expiracion_password: 90,
  max_intentos_login: 5,
  minutos_bloqueo_login: 15,
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockedList.mockReset();
  mockedListSucursales.mockReset();
  mockedListSucursales.mockResolvedValue([
    { uuid: SUCURSAL, nombre: 'Sucursal Centro' },
  ]);
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('ConfiguracionSeguridad page', () => {
  it('CS1: empty state when the API returns []', async () => {
    mockedList.mockResolvedValue([]);
    render(<ConfiguracionSeguridad />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('seguridad-empty')).toBeInTheDocument();
    });
  });

  it('CS2: renders the global row separately from overrides', async () => {
    mockedList.mockResolvedValue([
      GLOBAL_ROW,
      {
        ...GLOBAL_ROW,
        uuid: '22222222-2222-2222-2222-222222222222',
        uuid_sucursal: SUCURSAL,
        max_intentos_login: 3,
        minutos_bloqueo_login: 30,
      },
    ]);
    render(<ConfiguracionSeguridad />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('seguridad-card-global')).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('seguridad-card-override-dddddddd-1111-1111-1111-111111111111'),
    ).toBeInTheDocument();
  });

  it('CS3: "Nueva configuración" opens the modal with an empty form', async () => {
    const user = userEvent.setup();
    mockedList.mockResolvedValue([]);
    render(<ConfiguracionSeguridad />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('seguridad-empty'));
    await user.click(screen.getByTestId('seguridad-new'));
    expect(screen.getByTestId('seguridad-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('configuracion-seguridad-form')).toBeInTheDocument();
  });
});
