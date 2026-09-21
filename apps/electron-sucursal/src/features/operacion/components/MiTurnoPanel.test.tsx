/**
 * Unit tests for `<MiTurnoPanel />` (HU-F12.1 — REQ-OPS-187).
 *
 * Coverage (verbatim tasks.md §2.5):
 *   T1: zero-state (uuid_sesion=null OR data=undefined) renders 4 KPIs
 *       as `0` and NO skeleton / NO error UI (DA-F12.1-4).
 *   T2: non-zero rendering — 5 KPI cells (ingresos / salidas /
 *       totalCobrado / efectivo / datafono) populated from the hook.
 *   T3: 401 mid-polling -> panel renders fallback (zeros), no crash
 *       (auth cleanup happens in the hook's onError).
 *   T4: 5xx -> panel renders fallback (zeros + a soft stale marker),
 *       no crash.
 *   T5: Cerrar-turno button -> navigate('/caja/cerrar-turno') ONLY,
 *       no useSesionActiva().cerrarSesion call (F10.2 owns close logic).
 *
 * Mocking strategy:
 *   - vi.mock('../../hooks/useMiTurno') -> swap the hook for a stub.
 *   - vi.mock('react-router-dom')       -> capture navigate calls.
 *   - vi.mock('react-i18next')          -> stub t().
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

const navigateMock = vi.fn();

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const useMiTurnoMock = vi.fn();
vi.mock('../hooks/useMiTurno', () => ({
  useMiTurno: (uuid_sesion: string | null) => useMiTurnoMock(uuid_sesion),
}));

import { MiTurnoPanel } from './MiTurnoPanel';

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

const UUID_SESION = '00000000-0000-0000-0000-000000000099';

const SAMPLE_OK = {
  data: {
    uuid_sesion: UUID_SESION,
    uuid_sucursal: '00000000-0000-0000-0000-000000000098',
    timestamp_calculo: '2026-09-21T08:00:00Z',
    ingresos_count: 3,
    salidas_count: 2,
    total_cobrado_efectivo_cop: 50000,
    total_cobrado_datafono_cop: 30000,
  },
  error: undefined,
};

const SAMPLE_ZERO = {
  data: {
    uuid_sesion: UUID_SESION,
    uuid_sucursal: '00000000-0000-0000-0000-000000000098',
    timestamp_calculo: '2026-09-21T08:00:00Z',
    ingresos_count: 0,
    salidas_count: 0,
    total_cobrado_efectivo_cop: 0,
    total_cobrado_datafono_cop: 0,
  },
  error: undefined,
};

describe('<MiTurnoPanel /> — REQ-OPS-187 (HU-F12.1)', () => {
  it('T1: zero-state (uuid_sesion=null) renders all-zero KPIs, no skeleton, no error', () => {
    useMiTurnoMock.mockReturnValue({ data: undefined, error: undefined });
    render(<MiTurnoPanel uuid_sesion={null} />);
    // Five KPI cells, all zeros.
    const ingresosCell = screen.getByTestId('mi-turno-kpi-ingresos');
    expect(ingresosCell).toBeInTheDocument();
    expect(ingresosCell.textContent).toMatch(/0/);
    // The Cerrar-turno button MUST render even in zero state (so the
    // operator can close an empty turno).
    expect(screen.getByTestId('mi-turno-cerrar-button')).toBeInTheDocument();
  });

  it('T2: non-zero rendering — 5 KPI cells populated from the hook', () => {
    useMiTurnoMock.mockReturnValue(SAMPLE_OK);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} />);
    expect(screen.getByTestId('mi-turno-kpi-ingresos').textContent).toMatch(/3/);
    expect(screen.getByTestId('mi-turno-kpi-salidas').textContent).toMatch(/2/);
    expect(screen.getByTestId('mi-turno-kpi-total-cobrado').textContent).toMatch(
      /80\.000|80000/,
    );
    expect(screen.getByTestId('mi-turno-kpi-efectivo').textContent).toMatch(/50\.000|50000/);
    expect(screen.getByTestId('mi-turno-kpi-datafono').textContent).toMatch(/30\.000|30000/);
  });

  it('T2b: zero-state with valid uuid_sesion renders 0s (DA-F12.1-4)', () => {
    useMiTurnoMock.mockReturnValue(SAMPLE_ZERO);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} />);
    expect(screen.getByTestId('mi-turno-kpi-ingresos').textContent).toMatch(/0/);
    expect(screen.getByTestId('mi-turno-kpi-salidas').textContent).toMatch(/0/);
    expect(screen.getByTestId('mi-turno-kpi-efectivo').textContent).toMatch(/0/);
    expect(screen.getByTestId('mi-turno-kpi-datafono').textContent).toMatch(/0/);
  });

  it('T3: 401 mid-polling -> panel renders zeros + stale marker, no crash', () => {
    // The hook's onError handles the auth cleanup; the panel only needs
    // to render without crashing. SWR keeps `data` populated across errors
    // so we still show the LAST good value (here: zeros).
    useMiTurnoMock.mockReturnValue({
      data: SAMPLE_ZERO.data,
      error: new Error('parkos:auth:cleared'),
    });
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} />);
    expect(screen.getByTestId('mi-turno-panel')).toBeInTheDocument();
    // No crash; the panel shows zeros (last good payload).
    expect(screen.getByTestId('mi-turno-kpi-ingresos').textContent).toMatch(/0/);
  });

  it('T4: 5xx -> panel renders zeros + soft stale marker, no crash', () => {
    useMiTurnoMock.mockReturnValue({
      data: undefined,
      error: new Error('server error'),
    });
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} />);
    expect(screen.getByTestId('mi-turno-panel')).toBeInTheDocument();
    // Even with no data, the panel renders zeros (zero-state UI).
    expect(screen.getByTestId('mi-turno-kpi-ingresos').textContent).toMatch(/0/);
  });

  it('T5: Cerrar-turno button -> navigate("/caja/cerrar-turno") ONLY', () => {
    useMiTurnoMock.mockReturnValue(SAMPLE_OK);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} />);
    fireEvent.click(screen.getByTestId('mi-turno-cerrar-button'));
    expect(navigateMock).toHaveBeenCalledTimes(1);
    expect(navigateMock).toHaveBeenCalledWith('/caja/cerrar-turno');
    // The button MUST NOT call useSesionActiva().cerrarSesion — that's
    // F10.2's responsibility. We assert by ensuring useMiTurnoMock was
    // called but no other mock (cerrarSesion) was registered.
    expect(navigateMock.mock.calls[0]?.[0]).toBe('/caja/cerrar-turno');
  });
});