/**
 * `ReimprimirFacturaDialog.test.tsx` — REQ-OPS-200 dialog behavior.
 *
 * 3 scenarios:
 *   1. motivo < 10 chars → Zod inline error, no POST fired.
 *   2. motivo ≥ 10 chars → trigger called with the right payload, dialog
 *      closes, onSuccess fires.
 *   3. trigger fails → inline error visible, dialog stays open.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const TRIGGER = vi.fn();
vi.mock('../hooks/useReimprimirFactura', () => ({
  useReimprimirFactura: () => ({ trigger: TRIGGER, isMutating: false }),
}));

import { ReimprimirFacturaDialog } from './ReimprimirFacturaDialog';

const UUID_FACTURA = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';
const UUID_INGRESO = '923a9426-98d2-4143-93e4-5317ce21b3a1';

describe('ReimprimirFacturaDialog', () => {
  it('rejects motivo < 10 chars with inline error, no POST', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    TRIGGER.mockReset();
    render(
      <ReimprimirFacturaDialog
        uuid_factura={UUID_FACTURA}
        uuid_ingreso={UUID_INGRESO}
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
    const input = screen.getByTestId('reimprimir-motivo');
    await user.type(input, 'corto');
    await user.click(screen.getByTestId('reimprimir-confirmar'));
    expect(TRIGGER).not.toHaveBeenCalled();
    expect(await screen.findByTestId('reimprimir-motivo-error')).toBeInTheDocument();
  });

  it('submits with the right payload and closes on success', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    TRIGGER.mockReset();
    TRIGGER.mockResolvedValue({
      uuid: '44444444-4444-4444-4444-444444444444',
    });
    render(
      <ReimprimirFacturaDialog
        uuid_factura={UUID_FACTURA}
        uuid_ingreso={UUID_INGRESO}
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
    await user.type(
      screen.getByTestId('reimprimir-motivo'),
      'Cliente solicita reimpresion para archivo',
    );
    await user.click(screen.getByTestId('reimprimir-confirmar'));
    await waitFor(() => {
      expect(TRIGGER).toHaveBeenCalledWith({
        uuid_ingreso: UUID_INGRESO,
        uuid_factura: UUID_FACTURA,
        motivo: 'Cliente solicita reimpresion para archivo',
      });
    });
    expect(onSuccess).toHaveBeenCalledWith('44444444-4444-4444-4444-444444444444');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows inline error when the trigger rejects', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    TRIGGER.mockReset();
    TRIGGER.mockRejectedValue(
      Object.assign(new Error('network'), {
        status: 409,
        body: '{"error":"reimpresion_already_pending"}',
      }),
    );
    render(
      <ReimprimirFacturaDialog
        uuid_factura={UUID_FACTURA}
        uuid_ingreso={UUID_INGRESO}
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
    await user.type(
      screen.getByTestId('reimprimir-motivo'),
      'Cliente solicita reimpresion para archivo',
    );
    await user.click(screen.getByTestId('reimprimir-confirmar'));
    expect(await screen.findByTestId('reimprimir-error')).toHaveTextContent(
      'reimpresion_already_pending',
    );
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
