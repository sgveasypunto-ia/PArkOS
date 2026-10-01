/**
 * ConfiguracionTolerancias — page-level integration tests.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

import { SucursalProvider } from '@/lib/sucursal-context';

vi.mock('@/features/sucursales/api/sucursalesApi', () => ({
  listSucursales: vi.fn(),
}));

vi.mock('../api/configuracionToleranciasApi', () => ({
  listConfiguracionTolerancias: vi.fn(),
  getConfiguracionTolerancias: vi.fn(),
  createConfiguracionTolerancias: vi.fn(),
  updateConfiguracionTolerancias: vi.fn(),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: { uuid: 'u-1', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['suc-1'],
    permisos: ['config_tolerancias'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

import { useAuthStore } from '@parkos/ui-kit/store';
import { listConfiguracionTolerancias } from '../api/configuracionToleranciasApi';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import ConfiguracionTolerancias from './ConfiguracionTolerancias';

const mockedList = listConfiguracionTolerancias as ReturnType<typeof vi.fn>;
const mockedListSucursales = listSucursales as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  // PR2 added the "Mi sucursal activa" tab which reads `useSucursal()`.
  const configValue = { provider: (): never => new Map() as never };
  return createElement(
    SucursalProvider,
    null,
    createElement(SWRConfig, { value: configValue }, children),
  );
}

function fullWrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(MemoryRouter, null, createElement(wrapper, { children }));
}

const SUCURSAL = 'cccccccc-1111-1111-1111-111111111111';

const GLOBAL_ROW = {
  uuid: '11111111-1111-1111-1111-111111111111',
  uuid_sucursal: null,
  tolerancia_efectivo: '100.0000',
  tolerancia_datafono: '200.0000',
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

const OVERRIDE_ROW = {
  uuid: '22222222-2222-2222-2222-222222222222',
  uuid_sucursal: SUCURSAL,
  tolerancia_efectivo: '50.0000',
  tolerancia_datafono: '150.0000',
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

describe('ConfiguracionTolerancias page', () => {
  it('CT1: empty state when the API returns []', async () => {
    mockedList.mockResolvedValue([]);
    render(<ConfiguracionTolerancias />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('tolerancia-empty')).toBeInTheDocument();
    });
  });

  it('CT2: renders the global row separately from overrides', async () => {
    mockedList.mockResolvedValue([GLOBAL_ROW, OVERRIDE_ROW]);
    render(<ConfiguracionTolerancias />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('tolerancia-card-global')).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('tolerancia-card-override-cccccccc-1111-1111-1111-111111111111'),
    ).toBeInTheDocument();
    expect(screen.getByText('100.0000')).toBeInTheDocument();
    expect(screen.getByText('50.0000')).toBeInTheDocument();
  });

  it('CT3: "Nueva tolerancia" opens the modal with an empty form', async () => {
    const user = userEvent.setup();
    mockedList.mockResolvedValue([]);
    render(<ConfiguracionTolerancias />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('tolerancia-empty'));
    await user.click(screen.getByTestId('tolerancia-new'));
    expect(screen.getByTestId('tolerancia-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('configuracion-tolerancias-form')).toBeInTheDocument();
  });
});
