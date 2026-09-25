/**
 * Unit tests for `ForzarIngresoModal` (HU-F6.1, T6).
 *
 * Spec scenarios:
 *   - motivo <10 chars → submit blocked inline (button disabled), POST must NOT fire.
 *   - motivo ≥10 chars → onConfirm fires with `[FORZADO: <motivo>]` payload.
 *
 * Uses `fireEvent` (from `@testing-library/react`).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import '@/i18n';

import { ForzarIngresoModal } from './ForzarIngresoModal';

describe('ForzarIngresoModal', () => {
  it('disables the confirm button until motivo ≥10 chars', async () => {
    const onConfirm = vi.fn();
    render(
      <ForzarIngresoModal
        open
        placa="ABC123"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByRole('button', { name: /confirmar/i });
    expect(confirmBtn).toBeDisabled();
    const motivoInput = screen.getByLabelText(/motivo/i) as HTMLInputElement;
    fireEvent.change(motivoInput, { target: { value: 'corto' } });
    // 5 chars — still disabled (Zod min(10)).
    expect(confirmBtn).toBeDisabled();
    fireEvent.change(motivoInput, {
      target: { value: 'cliente VIP requiere acceso' },
    });
    // 27 chars — now enabled.
    await waitFor(() => expect(confirmBtn).toBeEnabled());
  });

  it('fires onConfirm with the [FORZADO: <motivo>] payload when valid', async () => {
    const onConfirm = vi.fn();
    render(
      <ForzarIngresoModal
        open
        placa="ABC123"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    const motivoInput = screen.getByLabelText(/motivo/i) as HTMLInputElement;
    fireEvent.change(motivoInput, {
      target: { value: 'cliente VIP requiere acceso' },
    });
    const confirmBtn = screen.getByRole('button', { name: /confirmar/i });
    // RHF's `mode: 'onChange'` + Zod resolver validates asynchronously —
    // `formState.isValid` (and therefore the button's `disabled` prop)
    // only flips after a re-render following the change event. Clicking
    // immediately hits a still-disabled button, which never submits.
    await waitFor(() => expect(confirmBtn).toBeEnabled());
    fireEvent.click(confirmBtn);
    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith({
        placa: 'ABC123',
        motivo: 'cliente VIP requiere acceso',
        observaciones: '[FORZADO: cliente VIP requiere acceso]',
      }),
    );
  });

  it('strips leading/trailing whitespace from the motivo', async () => {
    const onConfirm = vi.fn();
    render(
      <ForzarIngresoModal
        open
        placa="ABC123"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    const motivoInput = screen.getByLabelText(/motivo/i) as HTMLInputElement;
    fireEvent.change(motivoInput, {
      target: { value: '   cliente VIP   ' },
    });
    const confirmBtn = screen.getByRole('button', { name: /confirmar/i });
    await waitFor(() => expect(confirmBtn).toBeEnabled());
    fireEvent.click(confirmBtn);
    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith(
        expect.objectContaining({ motivo: 'cliente VIP' }),
      ),
    );
  });

  it('fires onCancel when the cancel button is clicked', () => {
    const onCancel = vi.fn();
    render(
      <ForzarIngresoModal
        open
        placa="ABC123"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /cancelar/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
