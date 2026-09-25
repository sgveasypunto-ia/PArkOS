/**
 * Unit tests for `<Dashboard />` container (F3.3 — T4 + REQ-OPS-136).
 *
 * Coverage (verbatim tasks.md §2):
 *   U15: Operador sin sesión activa → `navigate('/caja/abrir-turno', { replace: true })`.
 *   U16: Operador con sesión activa → renderiza el hub con placa hero
 *        + secciones placeholder (alertas / fe-retry) + el badge real
 *        de sync (`dashboard-online`, F11.1 realineado — ya no vive en
 *        un `dashboard-section-sync` sr-only, ver `SyncStatusBadge`).
 *   U17: SWR 500 error → `<Alert>` + retry button.
 *   U18: isLoading=true → `<Skeleton>` sin redirect.
 *   U19: secciones renderizan con `data-testid="dashboard-section-*"`
 *        (REQ-OPS-137 §composable-section contract). Note: ingreso and
 *        salida wrappers were removed in `fix/dashboard-f6-wire` —
 *        those panels now live inside DrawerHost via IngresoSheet /
 *        SalidaSheet, not as sr-only anchors here.
 *
 * HU-F7.1 (búsqueda sin placa, T5) — PlacaInputHero autocomplete:
 *   U20: typing a partial placa renders a matching suggestion.
 *   U21: selecting a placa suggestion → opens the salida drawer with
 *        that placa (`initialPlaca`), exactly like the legacy fallback.
 *   U22: selecting a NO-placa (consecutivo) suggestion → opens the
 *        salida drawer via `initialUuidIngreso` instead of `initialPlaca`.
 *   U23: ArrowDown highlights the first suggestion (aria-activedescendant).
 *   U24: Escape closes the suggestion listbox.
 *   U25: Enter with NO suggestion highlighted preserves the legacy
 *        fallback (`getIngresosByPlaca` smart-routing), unchanged.
 *
 * Mocking strategy: vi.mock('../hooks/useSesionActiva') → return control.
 * `useAuth` se mockea para devolver `{ isAuthenticated: true }` por
 * default. `<TurnoActivoToggle>` y `<CuposLibresStrip>` se mockean como
 * passthrough con data-testid para evitar cargar primitives de Radix.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type * as ReactRouterDom from 'react-router-dom';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
// Named type-only import so the `vi.mock` factory below can reference
// `typeof IngresoActivoApiModule` instead of an inline `import()` type
// query (`@typescript-eslint/consistent-type-imports` forbids the latter).
import type * as IngresoActivoApiModule from '../../operacion/api/ingresoActivoApi';

const mockNavigate = vi.fn();
// Safe baseline (not a bare `vi.fn()`) so `Dashboard`'s unconditional
// `useSesionActiva()` destructure never sees `undefined` if a render
// slips in before a test configures its own return value.
const mockUseSesionActiva = vi.fn(() => ({
  sesion: null,
  isLoading: true,
  error: undefined,
  refresh: vi.fn(),
}));
const mockRefresh = vi.fn();
const mockUseAuth = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof ReactRouterDom>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../hooks/useSesionActiva', () => ({
  useSesionActiva: () => mockUseSesionActiva(),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => mockUseAuth(),
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

// Stub useIngresoActivo so PlacaInputHero doesn't try to fetch SWR.
vi.mock('../../operacion/hooks/useIngresoActivo', () => ({
  useIngresoActivo: () => ({
    hasActive: false,
    latestIngreso: null,
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
  }),
}));

// HU-F7.1 (T5) — PlacaInputHero autocomplete deps: the live active-ingresos
// snapshot (controlled per-test) and the legacy fallback fetch used when
// Enter is pressed with no suggestion highlighted.
const mockUseIngresosActivos = vi.fn();
vi.mock('../../operacion/hooks/useIngresosActivos', () => ({
  useIngresosActivos: (...args: unknown[]) => mockUseIngresosActivos(...args),
}));

const mockGetIngresosByPlaca = vi.fn();
vi.mock('../../operacion/api/ingresoActivoApi', async (importOriginal) => {
  const actual = await importOriginal<typeof IngresoActivoApiModule>();
  return {
    ...actual,
    getIngresosByPlaca: (...args: unknown[]) => mockGetIngresosByPlaca(...args),
  };
});

// Passthrough TurnoActivoToggle — expone data-testid para verificar render.
vi.mock('../components/TurnoActivoToggle', () => ({
  TurnoActivoToggle: ({ sesion }: { sesion: { uuid: string } }) => (
    <div data-testid="turno-activo-toggle-mock">
      <p>UUID: {sesion.uuid}</p>
    </div>
  ),
}));

// Passthrough CuposLibresStrip (footer, reemplazó a OcupacionPanel en el
// dashboard el 2026-09-22 — ver Dashboard.tsx). Pre-existing bug found
// while working on HU-F7.1: this mock/assertion still targeted the OLD
// `OcupacionPanel` component, which the dashboard no longer renders —
// U16 failed unconditionally (unrelated to this HU). Fixed by pointing
// the stub at the component actually rendered today.
vi.mock('../../operacion/components/CuposLibresStrip', () => ({
  CuposLibresStrip: () => <div data-testid="cupos-libres-strip-mock" />,
}));

// Stub IngresoSheet + SalidaSheet — DrawerHost tests cover the
// real wiring; here we just need to render the dashboard without
// SWR / IPC dependencies.
vi.mock('../../operacion/components/IngresoSheet', () => ({
  IngresoSheet: () => <div data-testid="ingreso-sheet-mock" />,
}));
vi.mock('../../operacion/components/SalidaSheet', () => ({
  SalidaSheet: () => <div data-testid="salida-sheet-mock" />,
}));

// Stub FacturaElectronicaRetryPanel — uses useFacturaElectronica SWR
// which would require parkosFetch + authStore mocks.
vi.mock('../../facturacion/components/FacturaElectronicaRetryPanel', () => ({
  FacturaElectronicaRetryPanel: () => <div data-testid="fe-retry-panel-mock" />,
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
  mockUseAuth.mockReturnValue({
    isAuthenticated: true,
    isLoading: false,
    sucursal: { uuid: 'suc-uuid-1' },
  });
  mockUseIngresosActivos.mockReturnValue([]);
  mockGetIngresosByPlaca.mockResolvedValue([]);
  useDashboardDrawerStore.getState().close();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('<Dashboard /> container — T4 + REQ-OPS-136 hub', () => {
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

  it('U16: sesion poblado → render hub con placa hero + secciones placeholder', () => {
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
    expect(screen.getByTestId('dashboard-hub')).toBeInTheDocument();
    expect(screen.getByTestId('turno-activo-toggle-mock')).toBeInTheDocument();
    expect(screen.getByText(/UUID: sess-uuid-123/)).toBeInTheDocument();
    expect(screen.getByTestId('cupos-libres-strip-mock')).toBeInTheDocument();
    // The placa hero (REQ-OPS-136 smart-routing entry point).
    expect(screen.getByTestId('placa-hero-input')).toBeInTheDocument();
    // Legacy sections retained as sr-only anchors for tests/audit.
    // Ingreso + salida wrappers were removed in fix/dashboard-f6-wire
    // because those panels now live inside DrawerHost.
    // SuscripcionesPanel sr-only anchor was removed in
    // feat/ux-remover-suscripciones-vencer (2026-09-22) — el panel
    // de vencimientos se mudó a otra ruta, fuera del kiosko.
    // F11.1 realineado (2026-09-24): el `dashboard-section-sync` sr-only
    // se retiró — el indicador de sync ahora es el badge real
    // `dashboard-online` del header (ver SyncStatusBadge), no un anchor
    // invisible.
    expect(screen.queryByTestId('dashboard-section-sync')).not.toBeInTheDocument();
    expect(screen.getByTestId('dashboard-online')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-section-alertas')).toBeInTheDocument();
    expect(screen.queryByTestId('dashboard-section-ingreso')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dashboard-section-salida')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dashboard-section-suscripciones')).not.toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalledWith('/caja/abrir-turno', expect.anything());
  });

  it('U16b: cada botón de acción del sidebar muestra su badge <kbd> de atajo', () => {
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
    const expectedBadges: Array<[string, string]> = [
      ['sidebar-ingreso', 'F1'],
      ['sidebar-salida', 'F2'],
      ['sidebar-suscripciones', 'F3'],
      ['sidebar-arqueo', 'F4'],
    ];
    for (const [testId, hotkey] of expectedBadges) {
      const button = screen.getByTestId(testId);
      const badge = within(button).getByText(hotkey);
      expect(badge.tagName).toBe('KBD');
    }
  });

  it('U17: error ParkosHttpError(500) → dashboard-error + retry button → click llama refresh', () => {
    mockUseSesionActiva.mockReturnValue({
      sesion: null,
      isLoading: false,
      error: new ParkosHttpError(500),
      refresh: mockRefresh,
    });
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('dashboard-error')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-retry')).toBeInTheDocument();
    screen.getByTestId('dashboard-retry').click();
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

  it('U19: !isAuthenticated → navigate("/login", { replace: true })', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      sucursal: null,
    });
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
      expect(mockNavigate).toHaveBeenCalledWith('/login', { replace: true });
    });
  });
});

describe('<PlacaInputHero /> — HU-F7.1 búsqueda sin placa (T5) autocomplete', () => {
  function renderDashboardConSesion(): void {
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
  }

  const ITEM_ABC123 = {
    uuid: 'uuid-ingreso-abc123',
    placa: 'ABC123',
    fecha_ingreso: '2026-09-19T10:00:00Z',
    consecutivo: null,
    created_at: '2026-09-19T10:00:00Z',
    uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
    uuid_sucursal: 'suc-uuid-1',
  };
  const ITEM_PATINETA = {
    uuid: 'uuid-ingreso-patineta',
    placa: null,
    fecha_ingreso: '2026-09-19T10:00:00Z',
    consecutivo: 'PATINETA-000003-34a24bae',
    created_at: '2026-09-19T10:00:00Z',
    uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000002',
    uuid_sucursal: 'suc-uuid-1',
  };

  it('U20: typing a partial placa renders a matching suggestion', async () => {
    mockUseIngresosActivos.mockReturnValue([ITEM_ABC123]);
    renderDashboardConSesion();

    await userEvent.type(screen.getByTestId('placa-hero-input'), 'ABC');

    expect(await screen.findByRole('option', { name: /ABC123/ })).toBeInTheDocument();
  });

  it('U21: selecting a placa suggestion → opens salida drawer with that placa', async () => {
    mockUseIngresosActivos.mockReturnValue([ITEM_ABC123]);
    renderDashboardConSesion();

    await userEvent.type(screen.getByTestId('placa-hero-input'), 'ABC');
    const option = await screen.findByRole('option', { name: /ABC123/ });
    await userEvent.click(option);

    await waitFor(() => {
      expect(useDashboardDrawerStore.getState().openDrawer).toBe('salida');
    });
    expect(useDashboardDrawerStore.getState().initialPlaca).toBe('ABC123');
    expect(mockGetIngresosByPlaca).not.toHaveBeenCalled();
  });

  it('U22: selecting a NO-placa (consecutivo) suggestion → opens salida drawer via initialUuidIngreso', async () => {
    mockUseIngresosActivos.mockReturnValue([ITEM_PATINETA]);
    renderDashboardConSesion();

    await userEvent.type(screen.getByTestId('placa-hero-input'), 'PATIN');
    const option = await screen.findByRole('option', { name: /PATINETA-000003-34a24bae/ });
    await userEvent.click(option);

    await waitFor(() => {
      expect(useDashboardDrawerStore.getState().openDrawer).toBe('salida');
    });
    const state = useDashboardDrawerStore.getState();
    expect(state.initialPlaca).toBeNull();
    expect(state.initialUuidIngreso).toBe('uuid-ingreso-patineta');
  });

  it('U23: ArrowDown highlights the first suggestion (aria-activedescendant)', async () => {
    mockUseIngresosActivos.mockReturnValue([ITEM_ABC123]);
    renderDashboardConSesion();

    const input = screen.getByTestId('placa-hero-input');
    await userEvent.type(input, 'ABC');
    const option = await screen.findByRole('option', { name: /ABC123/ });

    expect(input).toHaveAttribute('aria-expanded', 'true');
    await userEvent.keyboard('{ArrowDown}');
    expect(input.getAttribute('aria-activedescendant')).toBe(option.id);
  });

  it('U24: Escape closes the suggestion listbox', async () => {
    mockUseIngresosActivos.mockReturnValue([ITEM_ABC123]);
    renderDashboardConSesion();

    const input = screen.getByTestId('placa-hero-input');
    await userEvent.type(input, 'ABC');
    await screen.findByRole('listbox');

    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(input).toHaveAttribute('aria-expanded', 'false');
  });

  it('U25: Enter with no suggestion highlighted preserves the legacy fallback (getIngresosByPlaca smart-routing)', async () => {
    mockUseIngresosActivos.mockReturnValue([]);
    mockGetIngresosByPlaca.mockResolvedValue([]);
    renderDashboardConSesion();

    const input = screen.getByTestId('placa-hero-input');
    await userEvent.type(input, 'ZZZ999');
    await userEvent.keyboard('{Enter}');

    await waitFor(() => {
      expect(useDashboardDrawerStore.getState().openDrawer).toBe('ingreso');
    });
    expect(useDashboardDrawerStore.getState().initialPlaca).toBe('ZZZ999');
    expect(mockGetIngresosByPlaca).toHaveBeenCalledWith('ZZZ999');
  });
});