/**
 * Unit tests for `<Dashboard />` container (F3.3 — T4).
 *
 * Cobertura U15..U17 (cross-ref tasks.md §2):
 *   U15: Operador sin sesión activa → `navigate('/caja/abrir-turno', { replace: true })`.
 *   U16: Operador con sesión activa → renderiza `<TurnoActivoPanel>` con
 +        resumen + botón cerrar.
 *   U17: SWR 500 error → `<Alert>` + retry button.
 *
 * Mocking strategy: vi.mock('../hooks/useSesionActiva') → return control.
 * `<TurnoActivoPanel>` se mockea como passthrough con data-testid para
 * evitar carga de Card primitives (card.tsx creado en T4 — depende de
 * Tailwind pero no radix).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
const mockUseSesionActiva = vi.fn();
const mockRefresh = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../hooks/useSesionActiva', () => ({
  useSesionActiva: () => mockUseSesionActiva(),
}));

vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class extends Error {
    public readonly status: number;
    constructor(status: number) {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
    }
  },
}));

// Passthrough TurnoActivoPanel — expone data-testid para verificar render.
vi.mock('../components/TurnoActivoPanel', () => ({
  TurnoActivoPanel: ({
    sesion,
    onCerrarClick,
  }: {
    sesion: { uuid: string };
    onCerrarClick: () => void;
  }) => (
    <div data-testid="turno-activo-panel">
      <p>UUID: {sesion.uuid}</p>
      <button type="button" onClick={onCerrarClick} data-testid="turno-activo-cerrar">
        Cerrar turno
      </button>
    </div>
  ),
}));

import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { Dashboard } from './Dashboard';

const baseSesion = {
  uuid: 'sess-uuid-123',
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

afterEach(() => {
  vi.restoreAllMocks();
});

describe('<Dashboard /> container — T4', () => {
  it('U15: sesion=null + !isLoading + !error → navigate("/caja/abrir-turno", { replace: true })', async () => {
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: false,
      error: undefined,
      refresh: mockRefresh,
    });
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/caja/abrir-turno', { replace: true });
    });
  });

  it('U16: sesion poblado → render <TurnoActivoPanel> con resumen + botón cerrar', () => {
    mockUseSesionActiva.mockReturnValue({
      sesion: baseSesion,
      isLoading: false,
      error: undefined,
      refresh: mockRefresh,
    });
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('turno-activo-panel')).toBeInTheDocument();
    expect(screen.getByText(/UUID: sess-uuid-123/)).toBeInTheDocument();
    expect(screen.getByTestId('turno-activo-cerrar')).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalledWith('/caja/abrir-turno', expect.anything());
  });

  it('U16b: click en botón cerrar → navigate("/caja/cerrar-turno")', async () => {
    mockUseSesionActiva.mockReturnValue({
      sesion: baseSesion,
      isLoading: false,
      error: undefined,
      refresh: mockRefresh,
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    await user.click(screen.getByTestId('turno-activo-cerrar'));
    expect(mockNavigate).toHaveBeenCalledWith('/caja/cerrar-turno');
  });

  it('U17: error ParkosHttpError(500) → dashboard-error + retry button → click llama refresh', async () => {
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: false,
      error: new ParkosHttpError(500),
      refresh: mockRefresh,
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('dashboard-error')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-retry')).toBeInTheDocument();
    await user.click(screen.getByTestId('dashboard-retry'));
    expect(mockRefresh).toHaveBeenCalledOnce();
  });

  it('U17b: error ParkosHttpError(404) → NO error state (operador sin turno es estado válido)', () => {
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: false,
      error: new ParkosHttpError(404),
      refresh: mockRefresh,
    });
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('dashboard-error')).not.toBeInTheDocument();
  });

  it('U18: isLoading=true → render Skeleton sin redirect', () => {
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: true,
      error: undefined,
      refresh: mockRefresh,
    });
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('dashboard-skeleton')).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});