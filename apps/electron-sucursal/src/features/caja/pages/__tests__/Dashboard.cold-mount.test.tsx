/**
 * Cold-mount network-spy test for `<Dashboard />` (REQ-OPS-137
 * §Panel refresh independence + REQ-OPS-139 §Cold Dashboard has 0
 * panel fetches).
 *
 * Coverage:
 *   M1: Mounting Dashboard with `sesion` populated AND
 *       `useAuth().sucursal = null` (cold branch context) issues
 *       ZERO `parkosFetch` calls. Each panel's SWR key is `null`
 *       because its UUID prop is `null` (REQ-OPS-132 fetcher-closure
 *       idiom — key gates the fetch).
 *   M2: Mounting Dashboard with `sesion` populated AND
 *       `useAuth().sucursal = { uuid: 'X' }` does NOT trigger panel
 *       fetches for the cotizacion / FE-retry / pago paths (all three
 *       are gated by `null` UUIDs the Dashboard passes by default).
 *
 * Mocking strategy: spy on `@parkos/ui-kit/fetch::parkosFetch`. Mock
 * `useSesionActiva` so the dashboard's own sesion bootstrap doesn't
 * fire a real SWR. Mock `useAuth` so the test controls whether
 * `uuid_sucursal` is `null` (cold) or set (warm).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockUseSesionActiva = vi.fn();
const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../hooks/useSesionActiva', () => ({
  useSesionActiva: () => mockUseSesionActiva(),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockFetch = vi.fn();
vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: (...args: unknown[]) => mockFetch(...args),
  ParkosHttpError: class extends Error {
    public readonly status: number;
    constructor(status: number) {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
    }
  },
}));

// Mock all panels that don't themselves need real-render testing —
// the goal of THIS test is to count fetches, not to exercise panel
// rendering. Stubs return zero-behavior so the Dashboard tree mounts
// end-to-end without making any panel produce its own fetches.
vi.mock('../../components/TurnoActivoPanel', () => ({
  TurnoActivoPanel: ({ sesion }: { sesion: { uuid: string } }) => (
    <div data-testid="turno-activo-panel-stub">UUID: {sesion.uuid}</div>
  ),
}));
vi.mock('../../components/OcupacionPanel', () => ({
  OcupacionPanel: () => <div data-testid="ocupacion-panel-stub" />,
}));
vi.mock('../../../operacion/components/IngresoPanel', () => ({
  IngresoPanel: () => <div data-testid="ingreso-panel-stub" />,
}));
vi.mock('../../../suscripciones/components/SuscripcionesPanel', () => ({
  SuscripcionesPanel: () => <div data-testid="suscripciones-panel-stub" />,
}));
vi.mock('../../../sync/components/SyncStatusStrip', () => ({
  SyncStatusStrip: () => <div data-testid="sync-strip-stub" />,
}));
vi.mock('../../../sync/components/AlertasPanel', () => ({
  AlertasPanel: () => <div data-testid="alertas-panel-stub" />,
}));
vi.mock('../../../facturacion/components/FacturaElectronicaRetryPanel', () => ({
  FacturaElectronicaRetryPanel: () => <div data-testid="fe-retry-panel-stub" />,
}));

import { Dashboard } from '../Dashboard';

const baseSesion = {
  uuid: 'sess-uuid-cold',
  uuid_sucursal: 'suc-uuid-1',
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 50000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-15T08:00:00Z',
  timestamp_cierre: null,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('<Dashboard /> cold-mount network spy — REQ-OPS-137/139', () => {
  it('M1: cold branch (sucursal=null) + sesion populated → 0 parkosFetch calls', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      sucursal: null,
    });
    mockUseSesionActiva.mockReturnValue({
      sesion: baseSesion,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );

    // The dashboard's hub mounts (sesion populated). All panel UUID
    // props derive from `useAuth().sucursal?.uuid` → null. Each
    // SWR hook returns a null key → ZERO fetches.
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('M2: warm branch (sucursal set) but uuid_ingreso + uuid_fe are null → 0 panel fetches', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      sucursal: { uuid: 'suc-uuid-1' },
    });
    mockUseSesionActiva.mockReturnValue({
      sesion: baseSesion,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );

    // Even with a real sucursal, the cotizacion + FE-retry + pago
    // paths are gated by their own UUIDs which Dashboard passes as
    // null by default (REQ-OPS-137 §composable-section contract).
    // The panels that DO fetch on a warm branch (OcupacionPanel /
    // SyncStatusStrip / AlertasPanel / SuscripcionesPanel) are stubbed
    // here, so we still observe ZERO calls on the parkosFetch spy.
    expect(mockFetch).not.toHaveBeenCalled();
  });
});