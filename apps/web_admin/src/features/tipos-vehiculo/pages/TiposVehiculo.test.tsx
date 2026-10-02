/**
 * TiposVehiculo — page-level integration tests (mock the api layer).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../api/tiposVehiculoApi', () => ({
  listTiposVehiculo: vi.fn(),
  getTipoVehiculo: vi.fn(),
  createTipoVehiculo: vi.fn(),
  updateTipoVehiculo: vi.fn(),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: { uuid: 'u-1', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['suc-1'],
    permisos: ['config_catalogo'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

import { useAuthStore } from '@parkos/ui-kit/store';
import {
  createTipoVehiculo,
  listTiposVehiculo,
} from '../api/tiposVehiculoApi';
import TiposVehiculo from './TiposVehiculo';

const mockedList = listTiposVehiculo as ReturnType<typeof vi.fn>;
const mockedCreate = createTipoVehiculo as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

function fullWrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(MemoryRouter, null, createElement(wrapper, { children }));
}

const SAMPLE: {
  uuid: string;
  tipo: string;
  vigente_desde: string;
  vigente_hasta: null;
  estado: string;
  created_at: string;
  created_by: null;
  sync_status: string | null;
} = {
  uuid: 'aaaaaaaa-1111-1111-1111-111111111111',
  tipo: 'carro',
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockedList.mockReset();
  mockedCreate.mockReset();
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('TiposVehiculo page', () => {
  it('TV1: empty state when the API returns []', async () => {
    mockedList.mockResolvedValue([]);
    render(<TiposVehiculo />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('tipo-vehiculo-empty')).toBeInTheDocument();
    });
  });

  it('TV2: list renders the table with one row per tipo', async () => {
    mockedList.mockResolvedValue([SAMPLE]);
    render(<TiposVehiculo />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId('tipo-vehiculo-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument();
    });
    expect(screen.getByText('carro')).toBeInTheDocument();
  });

  it('TV3: "Nuevo tipo de vehículo" opens the modal with an empty form', async () => {
    const user = userEvent.setup();
    mockedList.mockResolvedValue([]);
    render(<TiposVehiculo />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('tipo-vehiculo-empty'));
    await user.click(screen.getByTestId('tipo-vehiculo-new'));
    expect(screen.getByTestId('tipo-vehiculo-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('tipo-vehiculo-form')).toBeInTheDocument();
  });

  it('TV4: "Nuevo tipo de vehículo" is disabled when the catalog is at the 5-tipo cap', async () => {
    // Seed 5 active canonical tipos to mirror the post-migration state.
    const cinco = ['carro', 'moto', 'bicicleta', 'patineta', 'otro'].map(
      (tipo, idx) => ({
        ...SAMPLE,
        uuid: `aaaaaaaa-1111-1111-1111-1111111111${idx.toString().padStart(2, '0')}`,
        tipo,
      }),
    );
    mockedList.mockResolvedValue(cinco);
    render(<TiposVehiculo />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('tipo-vehiculo-card'));
    const newBtn = screen.getByTestId('tipo-vehiculo-new') as HTMLButtonElement;
    expect(newBtn).toBeDisabled();
    // Surface the cap to the operator (UX hint).
    expect(screen.getByTestId('tipo-vehiculo-cap-notice')).toHaveTextContent(
      /5\/5/,
    );
    // Edit still allowed — cap applies to creation only.
    expect(
      screen.getByTestId('tipo-vehiculo-edit-aaaaaaaa-1111-1111-1111-111111111100'),
    ).toBeInTheDocument();
  });

  it('TV5: "Nuevo tipo de vehículo" stays enabled when below the 5-tipo cap', async () => {
    mockedList.mockResolvedValue([SAMPLE]);
    render(<TiposVehiculo />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('tipo-vehiculo-card'));
    const newBtn = screen.getByTestId('tipo-vehiculo-new') as HTMLButtonElement;
    expect(newBtn).not.toBeDisabled();
    expect(screen.queryByTestId('tipo-vehiculo-cap-notice')).not.toBeInTheDocument();
  });

  it('TV6: "Editar" opens the modal pre-filled without crashing (regression)', async () => {
    // QA batch tarifas/cupos: the EDIT branch used to render
    // `<TipoVehiculoForm form={undefined as never} .../>` directly
    // (never built via `useForm`), which threw
    // "Cannot read properties of undefined (reading 'handleSubmit')"
    // and crashed the whole page to a blank screen. Both branches
    // must now go through `TipoVehiculoFormHarness`.
    const user = userEvent.setup();
    mockedList.mockResolvedValue([SAMPLE]);
    render(<TiposVehiculo />, { wrapper: fullWrapper });
    await waitFor(() =>
      screen.getByTestId(`tipo-vehiculo-row-${SAMPLE.uuid}`),
    );
    await user.click(screen.getByTestId(`tipo-vehiculo-edit-${SAMPLE.uuid}`));
    expect(screen.getByTestId('tipo-vehiculo-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('tipo-vehiculo-field-tipo')).toHaveValue(SAMPLE.tipo);
  });
});
