/**
 * `ReclamoFacturaDialog.test.tsx` — REQ-OPS-202 dialog behavior.
 * Same shape as Reimprimir/Anular tests.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const TRIGGER = vi.fn();
vi.mock('../hooks/useCrearReclamoFactura', () => ({
  useCrearReclamoFactura: () => ({ trigger: TRIGGER, isMutating: false }),
}));

import { ReclamoFacturaDialog } from './ReclamoFacturaDialog';

const UUID_FACTURA = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';

describe('ReclamoFacturaDialog', () => {
  it('rejects motivo < 10 chars with inline error, no POST', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    TRIGGER.mockReset();
    render(
      <ReclamoFacturaDialog
        uuid_factura={UUID_FACTURA}
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
    await user.type(screen.getByTestId('reclamo-motivo'), 'corto');
    await user.click(screen.getByTestId('reclamo-confirmar'));
    expect(TRIGGER).not.toHaveBeenCalled();
    expect(await screen.findByTestId('reclamo-motivo-error')).toBeInTheDocument();
  });

  it('submits with the right payload and closes on success', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    TRIGGER.mockReset();
    TRIGGER.mockResolvedValue({ uuid: '66666666-6666-6666-6666-666666666666' });
    render(
      <ReclamoFacturaDialog
        uuid_factura={UUID_FACTURA}
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
    await user.type(
      screen.getByTestId('reclamo-motivo'),
      'Monto no coincide con lo cobrado en caja',
    );
    await user.click(screen.getByTestId('reclamo-confirmar'));
    await waitFor(() => {
      expect(TRIGGER).toHaveBeenCalledWith({
        uuid_factura: UUID_FACTURA,
        motivo: 'Monto no coincide con lo cobrado en caja',
      });
    });
    expect(onSuccess).toHaveBeenCalledWith('66666666-6666-6666-6666-666666666666');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows inline error when the trigger rejects', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    TRIGGER.mockReset();
    TRIGGER.mockRejectedValue(
      Object.assign(new Error('network'), {
        status: 403,
        body: '{"error":"permission_denied"}',
      }),
    );
    render(
      <ReclamoFacturaDialog
        uuid_factura={UUID_FACTURA}
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
    await user.type(
      screen.getByTestId('reclamo-motivo'),
      'Monto no coincide con lo cobrado en caja',
    );
    await user.click(screen.getByTestId('reclamo-confirmar'));
    expect(await screen.findByTestId('reclamo-error')).toHaveTextContent(
      'permission_denied',
    );
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
