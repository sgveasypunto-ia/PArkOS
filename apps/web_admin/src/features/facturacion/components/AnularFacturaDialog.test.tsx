/**
 * `AnularFacturaDialog.test.tsx` — REQ-OPS-201 dialog behavior.
 *
 * 3 scenarios mirror ReimprimirFacturaDialog:
 *   1. motivo < 10 chars → Zod inline error, no POST.
 *   2. motivo >= 10 chars → trigger called with tipo_anulable='salida' +
 *      uuid_salida, dialog closes, onSuccess fires.
 *   3. trigger fails → inline error, dialog stays open.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const TRIGGER = vi.fn();
vi.mock('../hooks/useAnularFactura', () => ({
  useAnularFactura: () => ({ trigger: TRIGGER, isMutating: false }),
}));

import { AnularFacturaDialog } from './AnularFacturaDialog';

const UUID_SALIDA = 'e15c3918-0e1f-4a47-b127-6938c1298a79';

describe('AnularFacturaDialog', () => {
  it('rejects motivo < 10 chars with inline error, no POST', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    TRIGGER.mockReset();
    render(
      <AnularFacturaDialog
        uuid_salida={UUID_SALIDA}
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
    await user.type(screen.getByTestId('anular-motivo'), 'corto');
    await user.click(screen.getByTestId('anular-confirmar'));
    expect(TRIGGER).not.toHaveBeenCalled();
    expect(await screen.findByTestId('anular-motivo-error')).toBeInTheDocument();
  });

  it('submits with the right payload and closes on success', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    TRIGGER.mockReset();
    TRIGGER.mockResolvedValue({ uuid: '55555555-5555-5555-5555-555555555555' });
    render(
      <AnularFacturaDialog
        uuid_salida={UUID_SALIDA}
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
    await user.type(
      screen.getByTestId('anular-motivo'),
      'Error de digitacion numero de placa incorrecto',
    );
    await user.click(screen.getByTestId('anular-confirmar'));
    await waitFor(() => {
      expect(TRIGGER).toHaveBeenCalledWith({
        uuid_salida: UUID_SALIDA,
        motivo: 'Error de digitacion numero de placa incorrecto',
      });
    });
    expect(onSuccess).toHaveBeenCalledWith('55555555-5555-5555-5555-555555555555');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows inline error when the trigger rejects', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    TRIGGER.mockReset();
    TRIGGER.mockRejectedValue(
      Object.assign(new Error('network'), {
        status: 422,
        body: '{"error":"polymorphic_pair_mismatch"}',
      }),
    );
    render(
      <AnularFacturaDialog
        uuid_salida={UUID_SALIDA}
        open
        onOpenChange={onOpenChange}
        onSuccess={onSuccess}
      />,
    );
    await user.type(
      screen.getByTestId('anular-motivo'),
      'Error de digitacion numero de placa incorrecto',
    );
    await user.click(screen.getByTestId('anular-confirmar'));
    expect(await screen.findByTestId('anular-error')).toHaveTextContent(
      'polymorphic_pair_mismatch',
    );
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
