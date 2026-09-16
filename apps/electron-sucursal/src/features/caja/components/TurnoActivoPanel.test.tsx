/**
 * Unit tests for `<TurnoActivoPanel />` organism (F3.3 — T4).
 *
 * Cobertura U-T1..U-T3 (cross-ref tasks.md §2):
 *   U-T1: Renderiza uuid + timestamp + valores iniciales + botón cerrar.
 *   U-T2: Omite bloque Observaciones cuando `sesion.observaciones === null` o ''.
 *   U-T3: Click en botón cerrar invoca callback `onCerrarClick`.
 *
 * Mocking: NO vi.mock necesario — `<TurnoActivoPanel>` es presentational
 * puro (NO consume hooks, NO invoca parkosFetch, NO state interno).
 * `<Button>` y `<Card>` (shadcn) son primitives que no dependen de radix
 * deps (Card NO usa @radix-ui/*; Button usa @radix-ui/react-slot solo
 * cuando `asChild`, lo cual no usamos).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TurnoActivoPanel } from './TurnoActivoPanel';

const baseSesion = {
  uuid: 'sess-uuid-123',
  uuid_sucursal: 'suc-uuid-1',
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 50000,
  valor_inicial_datafono: 0,
  timestamp_apertura: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  timestamp_cierre: null,
  observaciones: 'Apertura turno mañana',
};

describe('<TurnoActivoPanel /> organism — T4', () => {
  it('U-T1: renderiza uuid + valores iniciales + apertura + botón cerrar', () => {
    const onCerrarClick = vi.fn();
    render(<TurnoActivoPanel sesion={baseSesion} onCerrarClick={onCerrarClick} />);
    expect(screen.getByTestId('turno-activo-panel')).toBeInTheDocument();
    expect(screen.getByTestId('turno-activo-uuid')).toHaveTextContent('sess-uuid-123');
    expect(screen.getByTestId('turno-activo-valor-efectivo')).toHaveTextContent(/50\.000/);
    expect(screen.getByTestId('turno-activo-valor-datafono')).toHaveTextContent(/\$ 0/);
    expect(screen.getByTestId('turno-activo-apertura')).toHaveTextContent(/hace 2 horas/);
    expect(screen.getByTestId('turno-activo-cerrar')).toBeInTheDocument();
  });

  it('U-T2a: omite bloque Observaciones cuando observaciones === null', () => {
    const onCerrarClick = vi.fn();
    render(
      <TurnoActivoPanel
        sesion={{ ...baseSesion, observaciones: null }}
        onCerrarClick={onCerrarClick}
      />,
    );
    expect(screen.queryByTestId('turno-activo-observaciones')).not.toBeInTheDocument();
  });

  it('U-T2b: omite bloque Observaciones cuando observaciones === ""', () => {
    const onCerrarClick = vi.fn();
    render(
      <TurnoActivoPanel
        sesion={{ ...baseSesion, observaciones: '' }}
        onCerrarClick={onCerrarClick}
      />,
    );
    expect(screen.queryByTestId('turno-activo-observaciones')).not.toBeInTheDocument();
  });

  it('U-T2c: renderiza bloque Observaciones cuando observaciones truthy', () => {
    const onCerrarClick = vi.fn();
    render(<TurnoActivoPanel sesion={baseSesion} onCerrarClick={onCerrarClick} />);
    const obs = screen.getByTestId('turno-activo-observaciones');
    expect(obs).toHaveTextContent('Apertura turno mañana');
  });

  it('U-T3: click en botón cerrar invoca callback onCerrarClick exactly once', async () => {
    const user = userEvent.setup();
    const onCerrarClick = vi.fn();
    render(<TurnoActivoPanel sesion={baseSesion} onCerrarClick={onCerrarClick} />);
    await user.click(screen.getByTestId('turno-activo-cerrar'));
    expect(onCerrarClick).toHaveBeenCalledOnce();
  });

  it('U-T4: CardTitle renderiza "Turno activo" (i18n key turnoActivo)', () => {
    render(<TurnoActivoPanel sesion={baseSesion} onCerrarClick={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Turno activo');
  });
});