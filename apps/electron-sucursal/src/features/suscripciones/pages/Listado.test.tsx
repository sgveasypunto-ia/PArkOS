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

const U = (n: number): string => `00000000-0000-4000-8000-00000000000${n}`;
const item = (
  n: number,
  nombre: string,
  identificacion: string,
  plan: string,
  vence: string,
  dias: number,
) => ({
  uuid: U(n),
  cliente: { uuid: U(n + 3), nombre, apellido: 'Prueba', numero_identificacion: identificacion },
  plan: {
    uuid: U(n + 6),
    tipo: plan,
    valor: '100000.00',
    cantidad_maxima_vehiculos: 2,
    mismo_tipo_vehiculo: false,
  },
  fecha_inicio_cobertura: '2029-12-01',
  fecha_vencimiento: vence,
  cupo_maximo: 2,
  vehiculos_inscritos: 1,
  dias_restantes: dias,
  puede_renovar: false,
});

// Real wire shape of GET /api/v1/clientes/subscripciones-activas: a wrapped list.
const mockPayload = {
  items: [
    item(1, 'Alpha', '111', 'Mensual', '2030-01-01', 400),
    item(2, 'Beta', '222', 'Mensual', '2030-06-01', 500),
    item(3, 'Gamma', '333', 'Anual', '2020-01-01', -30),
  ],
};

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
  mockFetch.mockResolvedValue(mockPayload);
});

describe('<Listado /> — REQ-OPS-182', () => {
  it('T0: pide la ruta real /clientes/subscripciones-activas (no /suscripciones-cliente)', async () => {
    renderListado();
    await waitFor(() => expect(screen.getByTestId('listado-row-' + U(1))).toBeDefined());
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe('/api/v1/clientes/subscripciones-activas');
  });

  it('T1: render → table shows 5 column headers and wrapped rows', async () => {
    renderListado();
    await waitFor(() => expect(screen.getByTestId('listado-row-' + U(1))).toBeDefined());
    expect(screen.getByText('Cliente')).toBeDefined();
    expect(screen.getByText('Plan')).toBeDefined();
    expect(screen.getByText('Fecha vencimiento')).toBeDefined();
    expect(screen.getByText('Días restantes')).toBeDefined();
    expect(screen.getByText('Estado')).toBeDefined();
    expect(screen.getByText('Alpha Prueba')).toBeDefined();
    expect(screen.getByTestId('listado-diasrestantes-' + U(1)).textContent).toBe('400');
    expect(screen.getByTestId('listado-estado-' + U(1)).textContent).toBe('activa');
    expect(screen.getByTestId('listado-estado-' + U(3)).textContent).toBe('vencida');
    expect(screen.queryByTestId('listado-error')).toBeNull();
  });

  it('T2: search by cliente or identificación → only matching row (no new GET)', async () => {
    renderListado();
    await waitFor(() => expect(screen.getByTestId('listado-row-' + U(1))).toBeDefined());

    fireEvent.change(screen.getByTestId('listado-search-input'), { target: { value: 'alpha' } });
    await waitFor(() => {
      expect(screen.getByTestId('listado-row-' + U(1))).toBeDefined();
      expect(screen.queryByTestId('listado-row-' + U(2))).toBeNull();
      expect(screen.queryByTestId('listado-row-' + U(3))).toBeNull();
    });

    fireEvent.change(screen.getByTestId('listado-search-input'), { target: { value: '222' } });
    await waitFor(() => {
      expect(screen.getByTestId('listado-row-' + U(2))).toBeDefined();
      expect(screen.queryByTestId('listado-row-' + U(1))).toBeNull();
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('T3: empty search shows all rows', async () => {
    renderListado();
    await waitFor(() => expect(screen.getByTestId('listado-row-' + U(1))).toBeDefined());
    fireEvent.change(screen.getByTestId('listado-search-input'), { target: { value: '' } });
    expect(screen.getByTestId('listado-row-' + U(1))).toBeDefined();
    expect(screen.getByTestId('listado-row-' + U(2))).toBeDefined();
    expect(screen.getByTestId('listado-row-' + U(3))).toBeDefined();
  });

  it('T4: lista vacía → mensaje vacío y sin error', async () => {
    mockFetch.mockResolvedValue({ items: [] });
    renderListado();
    await waitFor(() => expect(screen.getByTestId('listado-empty')).toBeDefined());
    expect(screen.queryByTestId('listado-error')).toBeNull();
  });

  it('T5: fallo del backend → alerta de error', async () => {
    mockFetch.mockRejectedValue(new Error('boom'));
    renderListado();
    await waitFor(() => expect(screen.getByTestId('listado-error')).toBeDefined());
  });
});
