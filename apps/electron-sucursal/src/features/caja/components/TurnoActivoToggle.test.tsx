/**
 * Unit tests for `<TurnoActivoToggle />` — fix del bug de superposición
 * visual (operador: el panel de detalles quedaba "super puesto" sobre
 * el `placa-card` del Dashboard).
 *
 * Causa raíz: el panel era un `<div absolute top-full>` hecho a mano,
 * sin portal ni collision detection. El fix migra a `<Popover>`
 * (Radix, ya usado en el resto del proyecto) que portalea a
 * `document.body` y calcula side/align con collision detection.
 *
 * Cobertura:
 *   T1: sesion=null -> no renderiza nada.
 *   T2: colapsado por defecto -> trigger visible, detalles ausentes.
 *   T3: click en el trigger -> abre el panel de detalles (portal).
 *   T4: contenido del panel -> SesionDetails + ResumenTurno (ingresos/
 *       salidas/cupos) con los datos de los hooks.
 *   T5: click de nuevo en el trigger -> cierra el panel.
 *   T6: Escape con el panel abierto -> cierra el panel (comportamiento
 *       nativo de Radix Popover, ya no hay listener manual).
 *   T7: el trigger expone aria-expanded/aria-haspopup manejados por
 *       Radix (no atributos manuales hardcodeados).
 *
 * Mocking: useMiTurno / useOcupacion (mismos hooks que MiTurnoPanel).
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import '@/i18n';

const useMiTurnoMock = vi.fn();
vi.mock('../../operacion/hooks/useMiTurno', () => ({
  useMiTurno: (uuid_sesion: string | null) => useMiTurnoMock(uuid_sesion),
}));

const useOcupacionMock = vi.fn();
vi.mock('../../operacion/hooks/useOcupacion', () => ({
  useOcupacion: (uuid_sucursal: string | null) => useOcupacionMock(uuid_sucursal),
}));

import { TurnoActivoToggle } from './TurnoActivoToggle';

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

const UUID_SESION = 'sess-uuid-0000000001';
const UUID_SUCURSAL = 'suc-uuid-0000000001';

const baseSesion = {
  uuid: UUID_SESION,
  uuid_sucursal: UUID_SUCURSAL,
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 50000,
  valor_inicial_datafono: 0,
  timestamp_apertura: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
  timestamp_cierre: null,
  observaciones: null,
};

const MI_TURNO_OK = {
  data: {
    uuid_sesion: UUID_SESION,
    uuid_sucursal: UUID_SUCURSAL,
    timestamp_calculo: '2026-09-24T08:00:00Z',
    ingresos_count: 5,
    salidas_count: 3,
    total_cobrado_efectivo_cop: 0,
    total_cobrado_datafono_cop: 0,
  },
  error: undefined,
};

const OCUPACION_OK = {
  data: {
    uuid_sucursal: UUID_SUCURSAL,
    generado_en: '2026-09-24T08:00:00Z',
    items: [
      { uuid_tipo_vehiculo: 'tipo-1', tipo: 'carro', cupo_maximo: 10, activos: 4, disponible: 6 },
      { uuid_tipo_vehiculo: 'tipo-2', tipo: 'moto', cupo_maximo: 5, activos: 2, disponible: 3 },
    ],
  },
  error: undefined,
};

function setupHooks(): void {
  useMiTurnoMock.mockReturnValue(MI_TURNO_OK);
  useOcupacionMock.mockReturnValue(OCUPACION_OK);
}

describe('<TurnoActivoToggle /> — fix superposición sobre placa-card', () => {
  it('T1: sesion=null no renderiza nada', () => {
    setupHooks();
    const { container } = render(<TurnoActivoToggle sesion={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('T2: colapsado por defecto — trigger visible, detalles ausentes', () => {
    setupHooks();
    render(<TurnoActivoToggle sesion={baseSesion} />);
    expect(screen.getByTestId('turno-activo-toggle')).toBeInTheDocument();
    expect(screen.queryByTestId('turno-activo-toggle-details')).not.toBeInTheDocument();
  });

  it('T3: click en el trigger abre el panel de detalles (portal)', async () => {
    setupHooks();
    render(<TurnoActivoToggle sesion={baseSesion} />);
    fireEvent.click(screen.getByTestId('turno-activo-toggle'));
    expect(await screen.findByTestId('turno-activo-toggle-details')).toBeInTheDocument();
  });

  it('T4: el panel muestra SesionDetails + ResumenTurno (ingresos/salidas/cupos)', async () => {
    setupHooks();
    render(<TurnoActivoToggle sesion={baseSesion} />);
    fireEvent.click(screen.getByTestId('turno-activo-toggle'));
    await screen.findByTestId('turno-activo-toggle-details');

    expect(screen.getByTestId('turno-activo-details-uuid')).toHaveTextContent(UUID_SESION);
    expect(screen.getByTestId('turno-activo-resumen-row-ingresos')).toHaveTextContent('5');
    expect(screen.getByTestId('turno-activo-resumen-row-salidas')).toHaveTextContent('3');
    // cuposLibres = 6 (carro) + 3 (moto) = 9
    expect(screen.getByTestId('turno-activo-resumen-cupos-libres-value')).toHaveTextContent('9');
  });

  it('T5: click de nuevo en el trigger cierra el panel', async () => {
    setupHooks();
    render(<TurnoActivoToggle sesion={baseSesion} />);
    const trigger = screen.getByTestId('turno-activo-toggle');
    fireEvent.click(trigger);
    await screen.findByTestId('turno-activo-toggle-details');

    fireEvent.click(trigger);
    expect(screen.queryByTestId('turno-activo-toggle-details')).not.toBeInTheDocument();
  });

  it('T6: Escape con el panel abierto lo cierra (comportamiento nativo de Radix Popover)', async () => {
    setupHooks();
    render(<TurnoActivoToggle sesion={baseSesion} />);
    fireEvent.click(screen.getByTestId('turno-activo-toggle'));
    const details = await screen.findByTestId('turno-activo-toggle-details');

    fireEvent.keyDown(details, { key: 'Escape' });
    expect(screen.queryByTestId('turno-activo-toggle-details')).not.toBeInTheDocument();
  });

  it('T7: el trigger expone aria-expanded/aria-haspopup manejados por Radix', async () => {
    setupHooks();
    render(<TurnoActivoToggle sesion={baseSesion} />);
    const trigger = screen.getByTestId('turno-activo-toggle');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveAttribute('aria-haspopup');

    fireEvent.click(trigger);
    await screen.findByTestId('turno-activo-toggle-details');
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
  });
});
