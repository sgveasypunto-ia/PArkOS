/**
 * Tests for `<Listado />` page (HU-F9.2, REQ-OPS-182).
 *
 * Coverage (3 component tests):
 *   T1: render → table shows the 5 columns (cliente, plan,
 *       fecha_vencimiento, dias_restantes, estado) header.
 *   T2: type "ABC123" into search input → only the matching row
 *       is visible (client-side filter, no new GET).
 *   T3: empty search → all rows shown.
 *
 * Mock strategy mirrors Venta.test.tsx (F9.1) and the
 * useSuscripcionesProximasVencer test — `@parkos/ui-kit/fetch` and
 * `react-i18next` are mocked at module scope.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) =>
      opts?.defaultValue ?? key,
  }),
}));

vi.mock('@parkos/ui-kit/store', () => {
  const state = { accessToken: 'tok-abc', clear: vi.fn() };
  return {
    useAuthStore: Object.assign(
      (sel: (s: typeof state) => unknown) => sel(state),
      { getState: () => state },
    ),
  };
});

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
    user: { email: 'operador@parkos.local' },
    sucursal: { uuid: 'uuid-sucursal-test-1', prefijo_nombre: 'BOG' },
  }),
}));

const mockFetch = vi.fn();
vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: (...args: unknown[]) => mockFetch(...args),
  ParkosHttpError: class extends Error {
    public readonly status: number;
    public readonly body: string;
    constructor(status: number, body = '') {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
      this.body = body;
    }
  },
}));

import { Listado } from './Listado';

const mockRows = [
  {
    uuid: 'uuid-1',
    placa: 'ABC123',
    cliente_nombre: 'Cliente Alpha',
    plan_nombre: 'Mensual',
    fecha_vencimiento: '2030-01-01',
    estado: 'activa' as const,
  },
  {
    uuid: 'uuid-2',
    placa: 'DEF456',
    cliente_nombre: 'Cliente Beta',
    plan_nombre: 'Mensual',
    fecha_vencimiento: '2030-06-01',
    estado: 'activa' as const,
  },
  {
    uuid: 'uuid-3',
    placa: 'GHI789',
    cliente_nombre: 'Cliente Gamma',
    plan_nombre: 'Anual',
    fecha_vencimiento: '2020-01-01',
    estado: 'vencida' as const,
  },
];

// Wrap each render in a fresh SWR cache so cached data from prior
// tests does not pollute subsequent test assertions about the
// `fetch.mock.calls` length.
const renderListado = (): ReturnType<typeof render> =>
  render(
    <SWRConfig value={{ provider: () => new Map() }}>
      <MemoryRouter>
        <Listado />
      </MemoryRouter>
    </SWRConfig>,
  );

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockFetch.mockReset();
  mockFetch.mockResolvedValue(mockRows);
});

describe('<Listado /> — REQ-OPS-182', () => {
  it('T1: render → table shows 5 column headers', async () => {
    renderListado();
    await waitFor(() => expect(screen.getByTestId('listado-row-ABC123')).toBeDefined());
    expect(screen.getByText('Cliente')).toBeDefined();
    expect(screen.getByText('Plan')).toBeDefined();
    expect(screen.getByText('Fecha vencimiento')).toBeDefined();
    expect(screen.getByText('Días restantes')).toBeDefined();
    expect(screen.getByText('Estado')).toBeDefined();
  });

  it('T2: search by placa → only matching row visible (no new GET)', async () => {
    renderListado();
    await waitFor(() => expect(screen.getByTestId('listado-row-ABC123')).toBeDefined());

    fireEvent.change(screen.getByTestId('listado-search-input'), {
      target: { value: 'ABC123' },
    });

    await waitFor(() => {
      expect(screen.getByTestId('listado-row-ABC123')).toBeDefined();
      expect(screen.queryByTestId('listado-row-DEF456')).toBeNull();
      expect(screen.queryByTestId('listado-row-GHI789')).toBeNull();
    });

    // The fetch is called only once (the initial mount GET). No
    // refetch on every keystroke — the filter is client-side.
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('T3: empty search shows all rows', async () => {
    renderListado();
    await waitFor(() => expect(screen.getByTestId('listado-row-ABC123')).toBeDefined());

    fireEvent.change(screen.getByTestId('listado-search-input'), {
      target: { value: '' },
    });

    expect(screen.getByTestId('listado-row-ABC123')).toBeDefined();
    expect(screen.getByTestId('listado-row-DEF456')).toBeDefined();
    expect(screen.getByTestId('listado-row-GHI789')).toBeDefined();
  });
});
