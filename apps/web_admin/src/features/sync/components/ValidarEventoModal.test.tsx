/**
 * `ValidarEventoModal.test.tsx` — HU-F19.6 action modal over the
 * already-real `POST /api/v1/validacion-evento`.
 *
 *  - T1: approving ("validado") with blank observaciones submits fine
 *    (no such requirement for validado).
 *  - T2: rejecting ("rechazado") with blank observaciones is blocked
 *    (zodResolver's conditional superRefine).
 *  - T3: a successful "rechazado" submit calls
 *    `createValidacionEventoTransicion` with the right body shape.
 *  - T4: a 409 (`ValidacionEventoTransicionIlegalError`) shows the "ya
 *    resuelto" message and does NOT call `onResuelto`; the submit button
 *    stays disabled.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type * as ValidacionEventoApiModule from '../api/validacionEventoApi';

vi.mock('../api/validacionEventoApi', async () => {
  const actual = await vi.importActual<typeof ValidacionEventoApiModule>(
    '../api/validacionEventoApi',
  );
  return { ...actual, createValidacionEventoTransicion: vi.fn() };
});

import {
  ValidacionEventoTransicionIlegalError,
  createValidacionEventoTransicion,
} from '../api/validacionEventoApi';
import { ValidarEventoModal } from './ValidarEventoModal';

const mockedCreate = createValidacionEventoTransicion as ReturnType<typeof vi.fn>;
const UUID = '11111111-1111-1111-1111-111111111111';

describe('ValidarEventoModal', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('T1: approving ("validado") with blank observaciones submits fine', async () => {
    const user = userEvent.setup();
    const onResuelto = vi.fn();
    mockedCreate.mockResolvedValueOnce({ uuid: UUID });

    render(
      <ValidarEventoModal
        uuidValidacionPadre={UUID}
        open
        onClose={vi.fn()}
        onResuelto={onResuelto}
      />,
    );

    // "validado" is the default selection -- submit without typing anything.
    await user.click(screen.getByTestId('validar-evento-submit'));

    await waitFor(() => expect(onResuelto).toHaveBeenCalledWith(UUID));
    expect(mockedCreate).toHaveBeenCalledWith({
      uuidValidacionPadre: UUID,
      estado: 'validado',
      observaciones: '',
    });
  });

  it('T2: rejecting ("rechazado") with blank observaciones stays blocked', async () => {
    const user = userEvent.setup();

    render(
      <ValidarEventoModal uuidValidacionPadre={UUID} open onClose={vi.fn()} onResuelto={vi.fn()} />,
    );

    await user.click(screen.getByTestId('validar-evento-radio-rechazado'));
    await user.click(screen.getByTestId('validar-evento-submit'));

    expect(mockedCreate).not.toHaveBeenCalled();
    expect(await screen.findByText(/observaciones son obligatorias/i)).toBeInTheDocument();
  });

  it('T3: a successful "rechazado" submit calls the API with the right body shape', async () => {
    const user = userEvent.setup();
    const onResuelto = vi.fn();
    mockedCreate.mockResolvedValueOnce({ uuid: UUID });

    render(
      <ValidarEventoModal
        uuidValidacionPadre={UUID}
        open
        onClose={vi.fn()}
        onResuelto={onResuelto}
      />,
    );

    await user.click(screen.getByTestId('validar-evento-radio-rechazado'));
    await user.type(
      screen.getByTestId('validar-evento-observaciones'),
      'Hash no coincide con el ticket físico.',
    );
    await user.click(screen.getByTestId('validar-evento-submit'));

    await waitFor(() => expect(onResuelto).toHaveBeenCalledWith(UUID));
    expect(mockedCreate).toHaveBeenCalledWith({
      uuidValidacionPadre: UUID,
      estado: 'rechazado',
      observaciones: 'Hash no coincide con el ticket físico.',
    });
  });

  it('T4: a 409 shows the "ya resuelto" message and does not call onResuelto', async () => {
    const user = userEvent.setup();
    const onResuelto = vi.fn();
    mockedCreate.mockRejectedValueOnce(new ValidacionEventoTransicionIlegalError());

    render(
      <ValidarEventoModal
        uuidValidacionPadre={UUID}
        open
        onClose={vi.fn()}
        onResuelto={onResuelto}
      />,
    );

    await user.click(screen.getByTestId('validar-evento-submit'));

    expect(await screen.findByTestId('validar-evento-error')).toHaveTextContent(
      /ya fue validado o rechazado/i,
    );
    expect(onResuelto).not.toHaveBeenCalled();
    expect(screen.getByTestId('validar-evento-submit')).toBeDisabled();
  });
});
