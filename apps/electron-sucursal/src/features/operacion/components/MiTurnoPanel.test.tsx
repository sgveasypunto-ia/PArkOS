/**
 * Unit tests for `<MiTurnoPanel />` (HU-F12.1 — REQ-OPS-187).
 *
 * Coverage (directiva 2026-09-22: panel = lista vertical con 3 filas
 * — ingresos en mi turno, salidas en mi turno, cupos libres en la
 * sucursal; SIN dinero):
 *   T1: zero-state (uuid_sesion=null OR data=undefined) renderiza las
 *       3 filas con valores `0` / `—` (cupos_libres sin branch =
 *       load-state emdash) y NO skeleton / NO error UI (DA-F12.1-4).
 *   T2: non-zero rendering — 3 filas pobladas desde los hooks
 *       (`useMiTurno` + `useOcupacion`). Ingresos y salidas vienen del
 *       MiTurnoRead; cupos_libres = sum de OcupacionItem.disponible.
 *   T2b: zero-state con uuid_sesion válido renderiza `0`s
 *       (DA-F12.1-4).
 *   T3: 401 mid-polling → panel renderiza fallback (zeros), no crash
 *       (auth cleanup ocurre en el onError del hook).
 *   T4: 5xx → panel renderiza fallback (zeros + data-stale="true"),
 *       no crash.
 *   T5: el panel NO expone ningún CTA (2026-09-22: Arqueo button
 *       removido — vive sólo en el sidebar izquierdo). "Cerrar turno"
 *       tampoco se duplica aquí (single source of truth en el header).
 *   T6 (nuevo): NO se renderiza ningún KPI de dinero — el contrato BE
 *       sigue trayendo `total_cobrado_*` en el wire, pero el panel no
 *       los muestra. Esto bloquea regresiones si alguien vuelve a
 *       meter `<MiTurnoKpiCard>` con las keys dinero.
 *
 * Mocking strategy:
 *   - vi.mock('../../hooks/useMiTurno')       → stub del hook.
 *   - vi.mock('../../hooks/useOcupacion')     → stub del hook nuevo.
 *   - vi.mock('@/store/dashboardDrawerStore') → captura openDrawer calls.
 *   - vi.mock('react-router-dom')             → navigate debe ser ZERO.
 *   - vi.mock('react-i18next')                → stub t().
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

const navigateMock = vi.fn();
const openDrawerMock = vi.fn();
const closeMock = vi.fn();

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

const useOcupacionMock = vi.fn();
vi.mock('../hooks/useOcupacion', () => ({
  useOcupacion: (uuid_sucursal: string | null) => useOcupacionMock(uuid_sucursal),
}));

vi.mock('@/store/dashboardDrawerStore', () => ({
  useDashboardDrawerStore: (
    selector: (s: { open: typeof openDrawerMock; close: typeof closeMock }) => unknown,
  ) => selector({ open: openDrawerMock, close: closeMock }),
}));

import { MiTurnoPanel } from './MiTurnoPanel';

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

const UUID_SESION = '00000000-0000-0000-0000-000000000099';
const UUID_SUCURSAL = '00000000-0000-0000-0000-000000000098';

const SAMPLE_OK = {
  data: {
    uuid_sesion: UUID_SESION,
    uuid_sucursal: UUID_SUCURSAL,
    timestamp_calculo: '2026-09-21T08:00:00Z',
    ingresos_count: 3,
    salidas_count: 2,
    // Campos dinero siguen en el wire por el contrato BE locked
    // (DA-F12.1-1 GATING); el panel simplemente no los renderiza.
    total_cobrado_efectivo_cop: 50000,
    total_cobrado_datafono_cop: 30000,
  },
  error: undefined,
  isLoaded: true,
};

const SAMPLE_OK_OCUPACION = {
  data: {
    uuid_sucursal: UUID_SUCURSAL,
    generado_en: '2026-09-21T08:00:00Z',
    items: [
      { uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001', tipo: 'carro', cupo_maximo: 10, activos: 4, disponible: 6 },
      { uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000002', tipo: 'moto',  cupo_maximo: 5,  activos: 3, disponible: 2 },
      // cupo_maximo = 0 → excluido del sum (no es un cupo real).
      { uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000003', tipo: 'bici',  cupo_maximo: 0,  activos: 0, disponible: 0 },
    ],
  },
  error: undefined,
};

const SAMPLE_ZERO = {
  data: {
    uuid_sesion: UUID_SESION,
    uuid_sucursal: UUID_SUCURSAL,
    timestamp_calculo: '2026-09-21T08:00:00Z',
    ingresos_count: 0,
    salidas_count: 0,
    total_cobrado_efectivo_cop: 0,
    total_cobrado_datafono_cop: 0,
  },
  error: undefined,
  isLoaded: true,
};

const SAMPLE_ZERO_OCUPACION = {
  data: {
    uuid_sucursal: UUID_SUCURSAL,
    generado_en: '2026-09-21T08:00:00Z',
    items: [],
  },
  error: undefined,
};

describe('<MiTurnoPanel /> — REQ-OPS-187 (HU-F12.1)', () => {
  it('T1: zero-state (uuid_sesion=null) renderiza filas en 0/—, no skeleton, no error', () => {
    useMiTurnoMock.mockReturnValue({ data: undefined, error: undefined });
    useOcupacionMock.mockReturnValue({ data: undefined, error: undefined });
    render(<MiTurnoPanel uuid_sesion={null} uuid_sucursal={null} />);
    // 3 filas visibles, sin importar si hay branch/sesion.
    expect(screen.getByTestId('mi-turno-list')).toBeInTheDocument();
    expect(screen.getByTestId('mi-turno-row-ingresos').textContent).toMatch(/0/);
    expect(screen.getByTestId('mi-turno-row-salidas').textContent).toMatch(/0/);
    // Sin uuid_sucursal el panel no conoce cupos_libres → emdash (load-state).
    expect(screen.getByTestId('mi-turno-cupos-libres-value').textContent).toMatch(/—/);
    // 2026-09-22: el Arqueo button se sacó del panel (vive en el sidebar
    // izquierdo). El panel es vista informativa de sólo-lectura.
    expect(screen.queryByTestId('mi-turno-arqueo-button')).not.toBeInTheDocument();
    // "Cerrar turno" sigue siendo header-only.
    expect(screen.queryByTestId('mi-turno-cerrar-button')).not.toBeInTheDocument();
  });

  it('T2: non-zero rendering — 3 filas pobladas desde los hooks', () => {
    useMiTurnoMock.mockReturnValue(SAMPLE_OK);
    useOcupacionMock.mockReturnValue(SAMPLE_OK_OCUPACION);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    // ingresos=3, salidas=2, cupos_libres = 6 (carro) + 2 (moto) = 8
    // (el tipo bici con cupo_maximo=0 se excluye del sum).
    expect(screen.getByTestId('mi-turno-row-ingresos').textContent).toMatch(/3/);
    expect(screen.getByTestId('mi-turno-row-salidas').textContent).toMatch(/2/);
    expect(screen.getByTestId('mi-turno-cupos-libres-value').textContent).toMatch(/8/);
  });

  it('T2b: zero-state con uuid_sesion válido renderiza 0s (DA-F12.1-4)', () => {
    useMiTurnoMock.mockReturnValue(SAMPLE_ZERO);
    useOcupacionMock.mockReturnValue(SAMPLE_ZERO_OCUPACION);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    expect(screen.getByTestId('mi-turno-row-ingresos').textContent).toMatch(/0/);
    expect(screen.getByTestId('mi-turno-row-salidas').textContent).toMatch(/0/);
    // items=[] → cupos_libres=0 (no emdash: branch existe, simplemente
    // no hay tipos configurados todavía).
    expect(screen.getByTestId('mi-turno-cupos-libres-value').textContent).toMatch(/0/);
  });

  it('T3: 401 mid-polling → panel renderiza fallback (zeros), no crash', () => {
    // El onError del hook maneja el auth cleanup; el panel sólo necesita
    // renderizar sin crashear. SWR mantiene `data` poblado entre
    // errores → vemos el último payload bueno (zeros).
    useMiTurnoMock.mockReturnValue({
      data: SAMPLE_ZERO.data,
      error: new Error('parkos:auth:cleared'),
    });
    useOcupacionMock.mockReturnValue({
      data: SAMPLE_ZERO_OCUPACION.data,
      error: new Error('parkos:auth:cleared'),
    });
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    expect(screen.getByTestId('mi-turno-panel')).toBeInTheDocument();
    expect(screen.getByTestId('mi-turno-row-ingresos').textContent).toMatch(/0/);
  });

  it('T4: 5xx con data previo → panel renderiza último bueno + data-stale="true", no crash', () => {
    // SWR mantiene `data` poblado entre errores → `isStale = data && error`.
    // Sin data previa (caso primer poll falla), `isStale=false` y el
    // panel renderiza 0/— (zero-state). Con data previa + error nuevo,
    // `isStale=true` y la lista muestra el último payload bueno con el
    // atributo data-stale="true" para que el operador sepa que el dato
    // está refrescándose.
    //
    // Importante: el hook expone `isStale` como parte de su return —
    // mockeamos `useMiTurno` y debemos setear el campo, sino el panel
    // destructura `undefined` y `data-stale="false"` aunque el hook real
    // hubiera computado `true`.
    useMiTurnoMock.mockReturnValue({
      data: SAMPLE_ZERO.data,
      error: new Error('server error'),
      isStale: true,
      refresh: vi.fn(),
    });
    useOcupacionMock.mockReturnValue({
      data: SAMPLE_ZERO_OCUPACION.data,
      error: new Error('server error'),
    });
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    expect(screen.getByTestId('mi-turno-panel')).toBeInTheDocument();
    expect(screen.getByTestId('mi-turno-panel').getAttribute('data-stale')).toBe('true');
    // Último payload bueno: ingresos=0, salidas=0, cupos_libres=0
    // (items=[] en SAMPLE_ZERO_OCUPACION).
    expect(screen.getByTestId('mi-turno-row-ingresos').textContent).toMatch(/0/);
    expect(screen.getByTestId('mi-turno-cupos-libres-value').textContent).toMatch(/0/);
  });

  it('T4b: 5xx sin data previa → zero-state (zeros + emdash), data-stale="false"', () => {
    // Primer poll falla (no hay data previo). El panel cae al zero-
    // state del hook (counts=0) y al emdash para cupos_libres
    // (useOcupacion sin data). `data-stale="false"` porque `isStale`
    // requiere `data !== undefined`.
    useMiTurnoMock.mockReturnValue({
      data: undefined,
      error: new Error('server error'),
    });
    useOcupacionMock.mockReturnValue({
      data: undefined,
      error: new Error('server error'),
    });
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    expect(screen.getByTestId('mi-turno-panel')).toBeInTheDocument();
    expect(screen.getByTestId('mi-turno-panel').getAttribute('data-stale')).toBe('false');
    expect(screen.getByTestId('mi-turno-row-ingresos').textContent).toMatch(/0/);
    expect(screen.getByTestId('mi-turno-cupos-libres-value').textContent).toMatch(/—/);
  });

  it('T5: MiTurnoPanel NO expone CTAs; Arqueo vive en el sidebar (2026-09-22)', () => {
    useMiTurnoMock.mockReturnValue(SAMPLE_OK);
    useOcupacionMock.mockReturnValue(SAMPLE_OK_OCUPACION);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    // 2026-09-22 (directiva del operador): el Arqueo button se sacó
    // de MiTurnoPanel — vive sólo en el sidebar izquierdo (`data-testid=
    // "sidebar-arqueo"` en Dashboard.tsx) + atajo F4. El panel es vista
    // informativa de sólo-lectura.
    expect(screen.queryByTestId('mi-turno-arqueo-button')).not.toBeInTheDocument();
    // "Cerrar turno" NO está acá — header es single source of truth.
    expect(screen.queryByTestId('mi-turno-cerrar-button')).not.toBeInTheDocument();
    // MiTurnoPanel no dispara ningún drawer por sí solo (es sólo-lectura).
    expect(openDrawerMock).not.toHaveBeenCalled();
    // Y tampoco navega.
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('T6: muestra el efectivo cobrado en una region accesible con formato COP es-CO', () => {
    useMiTurnoMock.mockReturnValue(SAMPLE_OK);
    useOcupacionMock.mockReturnValue(SAMPLE_OK_OCUPACION);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    const region = screen.getByRole('region', { name: 'miTurno.cobrado.regionLabel' });
    expect(region).toBeInTheDocument();
    const valor = screen.getByTestId('mi-turno-cobrado-efectivo-value');
    expect(valor.textContent).toMatch(/50\.000/);
    expect(valor.textContent).toMatch(/\$/);
    expect(region.textContent).toMatch(/miTurno\.cobrado\.efectivo/);
  });

  it('T6b: NO muestra datafono ni total general (el BE lo fija en 0 por F12.1.1)', () => {
    useMiTurnoMock.mockReturnValue(SAMPLE_OK);
    useOcupacionMock.mockReturnValue(SAMPLE_OK_OCUPACION);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    const panel = screen.getByTestId('mi-turno-panel');
    expect(panel.textContent).not.toMatch(/30\.000/);
    expect(panel.textContent).not.toMatch(/datafono/i);
    expect(screen.queryByTestId('mi-turno-cobrado-datafono-value')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mi-turno-cobrado-total-value')).not.toBeInTheDocument();
  });

  it('T6c: efectivo en cero renderiza $ 0 (valor real, no vacio)', () => {
    useMiTurnoMock.mockReturnValue(SAMPLE_ZERO);
    useOcupacionMock.mockReturnValue(SAMPLE_ZERO_OCUPACION);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    expect(screen.getByTestId('mi-turno-cobrado-efectivo-value').textContent).toMatch(/\$\s?0$/);
  });

  it('T6d: sin turno (uuid_sesion=null) o sin datos cargados renderiza em dash, no un cero falso', () => {
    useMiTurnoMock.mockReturnValue({ data: undefined, error: undefined, isLoaded: false });
    useOcupacionMock.mockReturnValue({ data: undefined, error: undefined });
    render(<MiTurnoPanel uuid_sesion={null} uuid_sucursal={null} />);
    expect(screen.getByTestId('mi-turno-cobrado-efectivo-value').textContent).toBe('—');
  });

  it('T6e: error sin datos previos muestra em dash y mensaje de error accesible', () => {
    useMiTurnoMock.mockReturnValue({
      data: undefined,
      error: new Error('server error'),
      isLoaded: false,
    });
    useOcupacionMock.mockReturnValue({ data: undefined, error: undefined });
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    expect(screen.getByTestId('mi-turno-cobrado-efectivo-value').textContent).toBe('—');
    expect(screen.getByRole('alert').textContent).toMatch(/miTurno\.cobrado\.error/);
  });

  it('T6f: con datos previos y error nuevo conserva el valor y no muestra alerta', () => {
    useMiTurnoMock.mockReturnValue({ ...SAMPLE_OK, error: new Error('x'), isStale: true });
    useOcupacionMock.mockReturnValue(SAMPLE_OK_OCUPACION);
    render(<MiTurnoPanel uuid_sesion={UUID_SESION} uuid_sucursal={UUID_SUCURSAL} />);
    expect(screen.getByTestId('mi-turno-cobrado-efectivo-value').textContent).toMatch(/50\.000/);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
