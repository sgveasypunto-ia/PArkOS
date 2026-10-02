/**
 * `TransicionAnulacionModal.test.tsx` -- HU-F20.3 transition modal tests.
 * Mirrors `alertas/components/DescartarAlertaModal.test.tsx`.
 *
 *  - T1: submit is blocked (zodResolver) while `motivo` is blank.
 *  - T2: a successful submit calls `transicionarAnulacion` and `onTransicionada`.
 *  - T3: a 409 (`IllegalTransitionError`) shows its message and does NOT
 *    call `onTransicionada`; the submit button stays disabled.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type * as AnulacionesApiModule from '../api/anulacionesApi';

vi.mock('../api/anulacionesApi', async () => {
  const actual = await vi.importActual<typeof AnulacionesApiModule>('../api/anulacionesApi');
  return { ...actual, transicionarAnulacion: vi.fn() };
});

import { IllegalTransitionError, transicionarAnulacion } from '../api/anulacionesApi';
import { TransicionAnulacionModal } from './TransicionAnulacionModal';

const mockedTransicionar = transicionarAnulacion as ReturnType<typeof vi.fn>;
const UUID = '11111111-1111-1111-1111-111111111111';

describe('TransicionAnulacionModal', () => {
  it('T1: submit stays blocked while motivo is blank', async () => {
    const user = userEvent.setup();
    render(
      <TransicionAnulacionModal
        uuidAnulacion={UUID}
        estadoDestino="autorizada"
        open
        onClose={vi.fn()}
        onTransicionada={vi.fn()}
      />,
    );

    await user.click(screen.getByTestId('transicion-anulacion-submit'));

    expect(mockedTransicionar).not.toHaveBeenCalled();
    expect(await screen.findByText(/motivo es obligatorio/i)).toBeInTheDocument();
  });

  it('T2: a successful submit calls transicionarAnulacion and onTransicionada', async () => {
    const user = userEvent.setup();
    const onTransicionada = vi.fn();
    const updated = {
      uuid: UUID,
      estado: 'autorizada',
    } as unknown as Awaited<ReturnType<typeof transicionarAnulacion>>;
    mockedTransicionar.mockResolvedValueOnce(updated);

    render(
      <TransicionAnulacionModal
        uuidAnulacion={UUID}
        estadoDestino="autorizada"
        open
        onClose={vi.fn()}
        onTransicionada={onTransicionada}
      />,
    );

    await user.type(screen.getByTestId('transicion-anulacion-motivo'), 'Soporte físico adjunto.');
    await user.click(screen.getByTestId('transicion-anulacion-submit'));

    await waitFor(() => expect(onTransicionada).toHaveBeenCalledWith(updated));
    expect(mockedTransicionar).toHaveBeenCalledWith(UUID, 'autorizada', 'Soporte físico adjunto.');
  });

  it('T3: a 409 shows the illegal-transition message and does not call onTransicionada', async () => {
    const user = userEvent.setup();
    const onTransicionada = vi.fn();
    mockedTransicionar.mockRejectedValueOnce(
      new IllegalTransitionError(UUID, { estado_actual: 'ejecutada', estado_solicitado: 'autorizada' }),
    );

    render(
      <TransicionAnulacionModal
        uuidAnulacion={UUID}
        estadoDestino="autorizada"
        open
        onClose={vi.fn()}
        onTransicionada={onTransicionada}
      />,
    );

    await user.type(screen.getByTestId('transicion-anulacion-motivo'), 'Intento tardío.');
    await user.click(screen.getByTestId('transicion-anulacion-submit'));

    expect(await screen.findByTestId('transicion-anulacion-error')).toHaveTextContent(/no admite esa transición/i);
    expect(onTransicionada).not.toHaveBeenCalled();
    expect(screen.getByTestId('transicion-anulacion-submit')).toBeDisabled();
  });
});
