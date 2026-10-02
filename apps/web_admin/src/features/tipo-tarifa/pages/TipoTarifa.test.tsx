/**
 * TipoTarifa — page-level integration tests (mock the api layer).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../api/tipoTarifaApi', () => ({
  listTipoTarifa: vi.fn(),
  getTipoTarifa: vi.fn(),
  createTipoTarifa: vi.fn(),
  updateTipoTarifa: vi.fn(),
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
  createTipoTarifa,
  listTipoTarifa,
} from '../api/tipoTarifaApi';
import TipoTarifa from './TipoTarifa';

const mockedList = listTipoTarifa as ReturnType<typeof vi.fn>;
const mockedCreate = createTipoTarifa as ReturnType<typeof vi.fn>;

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
  uuid: 'bbbbbbbb-1111-1111-1111-111111111111',
  tipo: 'hora',
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

describe('TipoTarifa page', () => {
  it('TT1: empty state when the API returns []', async () => {
    mockedList.mockResolvedValue([]);
    render(<TipoTarifa />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('tipo-tarifa-empty')).toBeInTheDocument();
    });
  });

  it('TT2: list renders the table with one row per tipo', async () => {
    mockedList.mockResolvedValue([SAMPLE]);
    render(<TipoTarifa />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId('tipo-tarifa-row-bbbbbbbb-1111-1111-1111-111111111111'),
      ).toBeInTheDocument();
    });
    expect(screen.getByText('hora')).toBeInTheDocument();
  });

  it('TT3: "Nueva modalidad" opens the modal with an empty form', async () => {
    const user = userEvent.setup();
    mockedList.mockResolvedValue([]);
    render(<TipoTarifa />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('tipo-tarifa-empty'));
    await user.click(screen.getByTestId('tipo-tarifa-new'));
    expect(screen.getByTestId('tipo-tarifa-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('tipo-tarifa-form')).toBeInTheDocument();
  });

  it('TT4: "Editar" opens the modal pre-filled without crashing (regression)', async () => {
    // QA batch tarifas/cupos: the EDIT branch used to render
    // `<TipoTarifaForm form={undefined as never} .../>` directly
    // (never built via `useForm`), which threw
    // "Cannot read properties of undefined (reading 'handleSubmit')"
    // and crashed the whole page to a blank screen. Both branches
    // must now go through `TipoTarifaFormHarness`.
    const user = userEvent.setup();
    mockedList.mockResolvedValue([SAMPLE]);
    render(<TipoTarifa />, { wrapper: fullWrapper });
    await waitFor(() =>
      screen.getByTestId(`tipo-tarifa-row-${SAMPLE.uuid}`),
    );
    await user.click(screen.getByTestId(`tipo-tarifa-edit-${SAMPLE.uuid}`));
    expect(screen.getByTestId('tipo-tarifa-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('tipo-tarifa-field-tipo')).toHaveValue(SAMPLE.tipo);
  });
});
