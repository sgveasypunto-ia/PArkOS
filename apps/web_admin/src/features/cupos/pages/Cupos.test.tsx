/**
 * Cupos — page-level integration tests (mock the api layer).
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

vi.mock('../api/cuposApi', () => ({
  listCupos: vi.fn(),
  listCuposByKey: vi.fn(),
  getCupo: vi.fn(),
  createCupo: vi.fn(),
  updateCupo: vi.fn(),
  CantidadOverlapError: class CantidadOverlapError extends Error {},
  CantidadBajoIngresosError: class CantidadBajoIngresosError extends Error {},
  CantidadSucursalInmutableError: class CantidadSucursalInmutableError extends Error {},
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: { uuid: 'u-1', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['suc-1'],
    permisos: ['config_cupos'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

import { listCupos, createCupo } from '../api/cuposApi';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import { useAuthStore } from '@parkos/ui-kit/store';
import Cupos from './Cupos';

const mockedListCupos = listCupos as ReturnType<typeof vi.fn>;
const mockedCreateCupo = createCupo as ReturnType<typeof vi.fn>;
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

const SUCURSAL_1 = '11111111-1111-1111-1111-111111111111';

const SAMPLE_CUPO: {
  uuid: string;
  uuid_sucursal: string;
  uuid_tipo_vehiculo: null;
  cantidad: number;
  vigente_desde: string;
  vigente_hasta: null;
  estado: string;
  created_at: string;
  created_by: null;
  sync_status: string | null;
} = {
  uuid: 'aaaaaaaa-1111-1111-1111-111111111111',
  uuid_sucursal: SUCURSAL_1,
  uuid_tipo_vehiculo: null,
  cantidad: 50,
  vigente_desde: '2026-09-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-09-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockedListCupos.mockReset();
  mockedCreateCupo.mockReset();
  mockedListSucursales.mockReset();
  mockedListSucursales.mockResolvedValue([
    { uuid: SUCURSAL_1, nombre: 'Sucursal Centro' },
  ]);
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('Cupos page', () => {
  it('CP1: empty state when the API returns []', async () => {
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('cupo-empty')).toBeInTheDocument();
    });
  });

  it('CP2: list grouped by sucursal with the vigente rows', async () => {
    mockedListCupos.mockResolvedValue([
      { ...SAMPLE_CUPO, uuid_sucursal: SUCURSAL_1, cantidad: 50 },
    ]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('cupo-sucursal-group-11111111-1111-1111-1111-111111111111')).toBeInTheDocument();
    });
    expect(screen.getByTestId('cupo-row-aaaaaaaa-1111-1111-1111-111111111111')).toBeInTheDocument();
  });

  it('CP3: "Nuevo cupo" opens the modal with an empty form', async () => {
    const user = userEvent.setup();
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    await user.click(screen.getByTestId('cupo-new'));
    expect(screen.getByTestId('cupo-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('cupo-form')).toBeInTheDocument();
  });
});
