/**
 * `FacturaAccionesMenu.test.tsx` — role-gate + estado-gate for the
 * action menu (REQ-X-08).
 *
 * X.1b ships the menu with placeholder handlers; X.3..X.5 will wire
 * the dialogs. The role-gate is a SKIPPED check in X.1b (the
 * `useMe()` hook is added in X.7) — but the estado-gate MUST be in
 * place: when the factura is `anulada`, the "Anular" button is hidden
 * (you cannot re-void a voided factura).
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { FacturaAccionesMenu } from './FacturaAccionesMenu';

const UUID = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';

describe('FacturaAccionesMenu', () => {
  it('renders 3 buttons when estado is vigente', () => {
    render(<FacturaAccionesMenu uuid={UUID} estado="vigente" />);
    expect(screen.getByTestId('factura-acciones-menu')).toBeInTheDocument();
    expect(screen.getByTestId('factura-accion-reimprimir')).toBeInTheDocument();
    expect(screen.getByTestId('factura-accion-anular')).toBeInTheDocument();
    expect(screen.getByTestId('factura-accion-reclamo')).toBeInTheDocument();
  });

  it('hides the "Anular" button when estado is anulada (cannot re-void)', () => {
    render(<FacturaAccionesMenu uuid={UUID} estado="anulada" />);
    expect(screen.getByTestId('factura-accion-reimprimir')).toBeInTheDocument();
    expect(screen.queryByTestId('factura-accion-anular')).toBeNull();
    expect(screen.getByTestId('factura-accion-reclamo')).toBeInTheDocument();
  });
});
