/**
 * `DescartarAlertaModal.test.tsx` -- HU-F19.5 confirmation modal over
 * the already-real HU-F19.4 descartar endpoint.
 *
 *  - T1: submit is blocked (zodResolver) while `observaciones` is blank.
 *  - T2: a successful submit calls `descartarAlerta` and `onDescartada`.
 *  - T3: a 409 (`AlertaYaResueltaError`) shows the "ya resuelta" message
 *    and does NOT call `onDescartada`; the submit button stays disabled.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type * as AlertasApiModule from '../api/alertasApi';

vi.mock('../api/alertasApi', async () => {
  const actual = await vi.importActual<typeof AlertasApiModule>('../api/alertasApi');
  return { ...actual, descartarAlerta: vi.fn() };
});

import { AlertaYaResueltaError, descartarAlerta } from '../api/alertasApi';
import { DescartarAlertaModal } from './DescartarAlertaModal';

const mockedDescartar = descartarAlerta as ReturnType<typeof vi.fn>;
const UUID = '11111111-1111-1111-1111-111111111111';

describe('DescartarAlertaModal', () => {
  it('T1: submit stays blocked while observaciones is blank', async () => {
    const user = userEvent.setup();
    render(
      <DescartarAlertaModal uuidAlerta={UUID} open onClose={vi.fn()} onDescartada={vi.fn()} />,
    );

    await user.click(screen.getByTestId('descartar-alerta-submit'));

    expect(mockedDescartar).not.toHaveBeenCalled();
    expect(await screen.findByText(/observaciones son obligatorias/i)).toBeInTheDocument();
  });

  it('T2: a successful submit calls descartarAlerta and onDescartada', async () => {
    const user = userEvent.setup();
    const onDescartada = vi.fn();
    const updated = { uuid: UUID, estado: 'resuelta' } as unknown as Awaited<ReturnType<typeof descartarAlerta>>;
    mockedDescartar.mockResolvedValueOnce(updated);

    render(
      <DescartarAlertaModal uuidAlerta={UUID} open onClose={vi.fn()} onDescartada={onDescartada} />,
    );

    await user.type(screen.getByTestId('descartar-alerta-observaciones'), 'Diferencia justificada con soporte.');
    await user.click(screen.getByTestId('descartar-alerta-submit'));

    await waitFor(() => expect(onDescartada).toHaveBeenCalledWith(updated));
    expect(mockedDescartar).toHaveBeenCalledWith(UUID, 'Diferencia justificada con soporte.');
  });

  it('T3: a 409 shows the "ya resuelta" message and does not call onDescartada', async () => {
    const user = userEvent.setup();
    const onDescartada = vi.fn();
    mockedDescartar.mockRejectedValueOnce(new AlertaYaResueltaError(UUID));

    render(
      <DescartarAlertaModal uuidAlerta={UUID} open onClose={vi.fn()} onDescartada={onDescartada} />,
    );

    await user.type(screen.getByTestId('descartar-alerta-observaciones'), 'Intento tardío.');
    await user.click(screen.getByTestId('descartar-alerta-submit'));

    expect(await screen.findByTestId('descartar-alerta-error')).toHaveTextContent(/ya estaba resuelta/i);
    expect(onDescartada).not.toHaveBeenCalled();
    expect(screen.getByTestId('descartar-alerta-submit')).toBeDisabled();
  });
});
