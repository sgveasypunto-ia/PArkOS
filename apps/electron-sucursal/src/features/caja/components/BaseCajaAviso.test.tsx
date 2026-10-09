/**
 * `<BaseCajaAviso />` — dashboard notice with the base de caja received.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import '@/i18n';

import { BaseCajaAviso } from './BaseCajaAviso';
import { marcarBaseAviso } from '../lib/baseCajaAviso';
import type { SesionRead } from '../api/sesionActivaApi';

const SESION: SesionRead = {
  uuid: 'sesion-1',
  uuid_sucursal: 'suc-1',
  uuid_usuario: 'usr-1',
  valor_inicial_efectivo: 100_000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-10-09T13:00:00Z',
  timestamp_cierre: null,
};

beforeEach(() => {
  window.sessionStorage.clear();
});

describe('<BaseCajaAviso />', () => {
  it('muestra la base recibida y a quién consultar cuando el turno acaba de abrirse', () => {
    marcarBaseAviso(SESION.uuid);
    render(<BaseCajaAviso sesion={SESION} />);

    expect(screen.getByTestId('base-caja-aviso-texto').textContent).toContain('100.000');
    expect(screen.getByTestId('base-caja-aviso-dudas').textContent).toContain(
      'supervisor o el administrador del sistema',
    );
  });

  it('no aparece si el aviso no está pendiente para esta sesión', () => {
    marcarBaseAviso('otra-sesion');
    const { container } = render(<BaseCajaAviso sesion={SESION} />);
    expect(container.firstChild).toBeNull();
  });

  it('no aparece sin sesión', () => {
    const { container } = render(<BaseCajaAviso sesion={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('"Entendido" lo descarta y no vuelve a salir', () => {
    marcarBaseAviso(SESION.uuid);
    const { rerender } = render(<BaseCajaAviso sesion={SESION} />);

    fireEvent.click(screen.getByTestId('base-caja-aviso-cerrar'));
    expect(screen.queryByTestId('base-caja-aviso')).toBeNull();

    rerender(<BaseCajaAviso sesion={SESION} />);
    expect(screen.queryByTestId('base-caja-aviso')).toBeNull();
    expect(window.sessionStorage.getItem('parkos:turno-base-aviso')).toBeNull();
  });
});
