/**
 * `TransicionReclamoModal.test.tsx` -- HU-F20.3 transition modal tests.
 * Mirrors `TransicionAnulacionModal.test.tsx`.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type * as ReclamosApiModule from '../api/reclamosApi';

vi.mock('../api/reclamosApi', async () => {
  const actual = await vi.importActual<typeof ReclamosApiModule>('../api/reclamosApi');
  return { ...actual, transicionarReclamo: vi.fn() };
});

import { IllegalTransitionError, transicionarReclamo } from '../api/reclamosApi';
import { TransicionReclamoModal } from './TransicionReclamoModal';

const mockedTransicionar = transicionarReclamo as ReturnType<typeof vi.fn>;
const UUID = '11111111-1111-1111-1111-111111111111';

describe('TransicionReclamoModal', () => {
  it('T1: submit stays blocked while motivo is blank', async () => {
    const user = userEvent.setup();
    render(
      <TransicionReclamoModal
        uuidReclamo={UUID}
        estadoDestino="en_investigacion"
        open
        onClose={vi.fn()}
        onTransicionada={vi.fn()}
      />,
    );

    await user.click(screen.getByTestId('transicion-reclamo-submit'));

    expect(mockedTransicionar).not.toHaveBeenCalled();
    expect(await screen.findByText(/motivo es obligatorio/i)).toBeInTheDocument();
  });

  it('T2: a successful submit calls transicionarReclamo and onTransicionada', async () => {
    const user = userEvent.setup();
    const onTransicionada = vi.fn();
    const updated = {
      uuid: UUID,
      estado: 'en_investigacion',
    } as unknown as Awaited<ReturnType<typeof transicionarReclamo>>;
    mockedTransicionar.mockResolvedValueOnce(updated);

    render(
      <TransicionReclamoModal
        uuidReclamo={UUID}
        estadoDestino="en_investigacion"
        open
        onClose={vi.fn()}
        onTransicionada={onTransicionada}
      />,
    );

    await user.type(screen.getByTestId('transicion-reclamo-motivo'), 'Evidencia adjunta.');
    await user.click(screen.getByTestId('transicion-reclamo-submit'));

    await waitFor(() => expect(onTransicionada).toHaveBeenCalledWith(updated));
    expect(mockedTransicionar).toHaveBeenCalledWith(UUID, 'en_investigacion', 'Evidencia adjunta.');
  });

  it('T3: a 409 shows the illegal-transition message and does not call onTransicionada', async () => {
    const user = userEvent.setup();
    const onTransicionada = vi.fn();
    mockedTransicionar.mockRejectedValueOnce(
      new IllegalTransitionError(UUID, {
        estado_actual: 'resuelto',
        estado_solicitado: 'en_investigacion',
      }),
    );

    render(
      <TransicionReclamoModal
        uuidReclamo={UUID}
        estadoDestino="en_investigacion"
        open
        onClose={vi.fn()}
        onTransicionada={onTransicionada}
      />,
    );

    await user.type(screen.getByTestId('transicion-reclamo-motivo'), 'Intento tardío.');
    await user.click(screen.getByTestId('transicion-reclamo-submit'));

    expect(await screen.findByTestId('transicion-reclamo-error')).toHaveTextContent(/no admite esa transición/i);
    expect(onTransicionada).not.toHaveBeenCalled();
    expect(screen.getByTestId('transicion-reclamo-submit')).toBeDisabled();
  });
});
