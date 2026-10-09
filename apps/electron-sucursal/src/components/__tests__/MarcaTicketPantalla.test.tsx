/**
 * `<MarcaTicketPantalla />` — logo easypunto en las vistas previas de ticket en pantalla,
 * el mismo que sale en el documento impreso (`marcaTicket.ts`).
 */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { MarcaTicketPantalla } from '../MarcaTicketPantalla';
import { logoDataUri } from '../../lib/print/marcaTicket';

afterEach(() => cleanup());

describe('MarcaTicketPantalla', () => {
  it('encabezado: muestra el logo negro (el mismo data-URI del impreso) con alt easypunto', () => {
    render(<MarcaTicketPantalla posicion="encabezado" />);
    const img = screen.getByRole('img', { name: 'easypunto' });
    expect(img.getAttribute('src')).toBe(logoDataUri());
    expect(img.getAttribute('src')).toMatch(/^data:image\/svg\+xml/);
  });

  it('pie: mismo logo, más pequeño que el encabezado y decorativo (sin nombre accesible repetido)', () => {
    render(
      <>
        <MarcaTicketPantalla posicion="encabezado" />
        <MarcaTicketPantalla posicion="pie" />
      </>,
    );
    const cab = screen.getByTestId('marca-ticket-encabezado');
    const pie = screen.getByTestId('marca-ticket-pie');
    expect(pie.getAttribute('src')).toBe(logoDataUri());
    expect(pie.getAttribute('alt')).toBe('');
    expect(parseFloat(pie.style.width)).toBeLessThan(parseFloat(cab.style.width));
    // Solo el encabezado se anuncia: easypunto no se lee dos veces.
    expect(screen.getAllByRole('img', { name: 'easypunto' })).toHaveLength(1);
  });

  it('proporcional al papel de 72 mm: 60 mm de cabecera y 30 mm de pie', () => {
    render(
      <>
        <MarcaTicketPantalla posicion="encabezado" />
        <MarcaTicketPantalla posicion="pie" />
      </>,
    );
    expect(screen.getByTestId('marca-ticket-encabezado').style.width).toBe(`${(60 / 72) * 100}%`);
    expect(screen.getByTestId('marca-ticket-pie').style.width).toBe(`${(30 / 72) * 100}%`);
  });

  it('si el logo no carga, no deja un icono roto: la imagen se retira y el contenedor no rompe', () => {
    const { container } = render(<MarcaTicketPantalla posicion="encabezado" />);
    fireEvent.error(screen.getByTestId('marca-ticket-encabezado'));
    expect(screen.queryByTestId('marca-ticket-encabezado')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
  });
});
