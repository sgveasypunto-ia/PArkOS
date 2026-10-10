import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import { LineasTicket } from '../LineasTicket';
import { MARCA_ENCABEZADO, MARCA_PIE } from '../../lib/print/marcaTicket';
import type { FacturaLinea } from '../../lib/print/facturaPrint';

const LINEAS: FacturaLinea[] = [
  MARCA_ENCABEZADO,
  { tipo: 'texto', texto: '*** REIMPRESIÓN ***', centro: true, negrita: true },
  { tipo: 'sep' },
  { tipo: 'fila', izq: 'TOTAL:', der: '$ 5.000', negrita: true },
  { tipo: 'texto', texto: 'Folio original:' },
  MARCA_PIE,
];

describe('<LineasTicket />', () => {
  it('renderiza cada linea del modelo: logo arriba y abajo, texto, separador y fila', () => {
    render(<LineasTicket lineas={LINEAS} testId="papel" etiqueta="Vista previa" />);
    const papel = screen.getByTestId('papel');
    expect(papel).toHaveAccessibleName('Vista previa');
    expect(within(papel).getByTestId('marca-ticket-encabezado')).toBeInTheDocument();
    expect(within(papel).getByTestId('marca-ticket-pie')).toBeInTheDocument();
    expect(within(papel).getByText('*** REIMPRESIÓN ***')).toHaveClass('text-center', 'font-bold');
    expect(within(papel).getByText('Folio original:')).toBeInTheDocument();
    expect(within(papel).getByText('TOTAL:')).toBeInTheDocument();
    expect(within(papel).getByText('$ 5.000')).toBeInTheDocument();
    expect(papel.querySelectorAll('hr')).toHaveLength(1);
  });
});
