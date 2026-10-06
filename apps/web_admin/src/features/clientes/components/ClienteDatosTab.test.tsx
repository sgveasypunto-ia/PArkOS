/**
 * `ClienteDatosTab.test.tsx` — validation + submit behavior (HU-F20.1).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ClienteDatosTab } from './ClienteDatosTab';
import type { Cliente } from '../api/clientesApi';

const BASE_CLIENTE: Cliente = {
  uuid: '11111111-1111-1111-1111-111111111111',
  tipo_identificador: 'CC',
  numero_identificacion: '1000000001',
  nombre: 'Ada',
  apellido: 'Lovelace',
  telefono: '3000000000',
  email: 'ada@example.com',
  uuid_tipo_persona: null,
  registro: null,
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: null,
};

describe('<ClienteDatosTab />', () => {
  it('submits the current (unchanged) values', async () => {
    const onSubmit = vi.fn().mockResolvedValue(BASE_CLIENTE);
    const user = userEvent.setup();
    render(<ClienteDatosTab cliente={BASE_CLIENTE} onSubmit={onSubmit} />);

    await user.click(screen.getByTestId('cliente-datos-submit'));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          tipo_identificador: 'CC',
          numero_identificacion: '1000000001',
          nombre: 'Ada',
          apellido: 'Lovelace',
          telefono: '3000000000',
          email: 'ada@example.com',
        }),
      );
    });
  });

  it('rejects an invalid email and does not submit', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<ClienteDatosTab cliente={BASE_CLIENTE} onSubmit={onSubmit} />);

    const emailField = screen.getByTestId('cliente-field-email');
    await user.clear(emailField);
    await user.type(emailField, 'not-an-email');
    await user.click(screen.getByTestId('cliente-datos-submit'));

    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  it('rejects an empty numero_identificacion', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<ClienteDatosTab cliente={BASE_CLIENTE} onSubmit={onSubmit} />);

    const numeroField = screen.getByTestId('cliente-field-numero');
    await user.clear(numeroField);
    await user.click(screen.getByTestId('cliente-datos-submit'));

    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  it('shows the "duplicado" message when the submit error mentions a duplicate', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('numero_identificacion_duplicado'));
    const user = userEvent.setup();
    render(<ClienteDatosTab cliente={BASE_CLIENTE} onSubmit={onSubmit} />);

    await user.click(screen.getByTestId('cliente-datos-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('cliente-datos-submit-error')).toHaveTextContent(
        'Ya existe un cliente con ese número de identificación.',
      );
    });
  });

  it('shows the generic error message for any other submit failure', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('500 Internal Server Error'));
    const user = userEvent.setup();
    render(<ClienteDatosTab cliente={BASE_CLIENTE} onSubmit={onSubmit} />);

    await user.click(screen.getByTestId('cliente-datos-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('cliente-datos-submit-error')).toHaveTextContent(
        'No se pudo guardar. Reintentá.',
      );
    });
  });

  it('is read-only for the standard billing client "Consumidor final" (no edit, no save)', async () => {
    const onSubmit = vi.fn();
    render(
      <ClienteDatosTab
        cliente={{ ...BASE_CLIENTE, numero_identificacion: '222222222222', nombre: 'Consumidor' }}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByTestId('cliente-datos-readonly')).toBeInTheDocument();
    expect(screen.queryByTestId('cliente-datos-submit')).not.toBeInTheDocument();
    expect(screen.getByTestId('cliente-field-nombre')).toBeDisabled();
    expect(screen.getByTestId('cliente-field-numero')).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
