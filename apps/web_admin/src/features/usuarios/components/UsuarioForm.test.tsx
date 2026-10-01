/**
 * `UsuarioForm.test.tsx` — regression tests for the two HU-F16 defects
 * that made this form destructive.
 *
 * 1. `resetPassword` returned `Promise<void>` and threw away the
 *    plaintext the backend hands out exactly once. The admin had no way
 *    to learn the new password.
 * 2. `update_admin_usuario` goes through `close_and_insert`, which
 *    regenerates the PK. `GET /usuarios/{uuid}` filters
 *    `vigente_hasta IS NULL`, so staying on the old url meant the detail
 *    page 404'd forever after any edit.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { UsuarioForm } from './UsuarioForm';
import * as api from '../api/usuariosApi';
import type { Usuario } from '../api/usuariosSchema';

const UUID_A = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const UUID_B = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';

function usuario(overrides: Partial<Usuario> = {}): Usuario {
  return {
    uuid: UUID_A,
    nombre: 'Ana',
    apellido: 'Ruiz',
    cedula: '123',
    email: 'ana@parkos.local',
    rol: 'admin',
    vigente_desde: '2026-01-01T00:00:00Z',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00Z',
    created_by: null,
    sync_status: null,
    ...overrides,
  };
}

/**
 * Renders the live router path alongside the form. A sibling `path="*"`
 * route would not work: navigating to the new uuid re-matches
 * `/admin/usuarios/:uuid`, so the form would just re-render itself and
 * the assertion could never observe the move.
 */
function PathProbe() {
  const { pathname } = useLocation();
  return <div data-testid="path-probe">{pathname}</div>;
}

function montar(u = usuario()) {
  return render(
    <MemoryRouter initialEntries={[`/admin/usuarios/${u.uuid}`]}>
      <PathProbe />
      <Routes>
        <Route path="/admin/usuarios/:uuid" element={<UsuarioForm usuario={u} />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(window, 'alert').mockImplementation(() => undefined);
});

describe('UsuarioForm — reset de contraseña', () => {
  it('muestra la contraseña temporal devuelta por el backend', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(api, 'resetPassword').mockResolvedValue({
      uuid_usuario: UUID_A,
      temporary_password: 'Xk7#pQm2Zbra',
      message: 'ok',
    });

    montar();

    await userEvent.click(screen.getByTestId('reset-password-btn'));

    // The whole point: the admin can actually read the password.
    expect(await screen.findByTestId('temp-password-value')).toHaveTextContent(
      'Xk7#pQm2Zbra',
    );
    expect(api.resetPassword).toHaveBeenCalledWith(UUID_A);
  });

  it('no persiste la contraseña en storage ni en la url', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(api, 'resetPassword').mockResolvedValue({
      uuid_usuario: UUID_A,
      temporary_password: 'Secreta9',
      message: 'ok',
    });

    montar();
    await userEvent.click(screen.getByTestId('reset-password-btn'));
    await screen.findByTestId('temp-password-value');

    expect(window.localStorage.getItem('temporary_password')).toBeNull();
    expect(window.sessionStorage.getItem('temporary_password')).toBeNull();
    expect(window.location.href).not.toContain('Secreta9');
  });

  it('cierra el dialog al confirmar', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(api, 'resetPassword').mockResolvedValue({
      uuid_usuario: UUID_A,
      temporary_password: 'CierraYa1',
      message: 'ok',
    });

    montar();
    await userEvent.click(screen.getByTestId('reset-password-btn'));
    await screen.findByTestId('temp-password-dialog');

    await userEvent.click(screen.getByTestId('temp-password-close'));

    await waitFor(() => {
      expect(screen.queryByTestId('temp-password-dialog')).not.toBeInTheDocument();
    });
  });
});

describe('UsuarioForm — actualización', () => {
  it('navega al uuid nuevo cuando el backend regenera el PK', async () => {
    vi.spyOn(api, 'updateUsuario').mockResolvedValue(
      usuario({ uuid: UUID_B, nombre: 'Ana María' }),
    );

    montar();

    await userEvent.clear(screen.getByLabelText('Nombre'));
    await userEvent.type(screen.getByLabelText('Nombre'), 'Ana María');
    await userEvent.click(screen.getByRole('button', { name: /Guardar cambios/i }));

    // Staying on the stale url would 404 permanently, because the GET
    // filters `vigente_hasta IS NULL` and the new row has a new uuid.
    await waitFor(() => {
      expect(screen.getByTestId('path-probe')).toHaveTextContent(UUID_B);
    });
  });

  it('no navega cuando el uuid se mantiene', async () => {
    vi.spyOn(api, 'updateUsuario').mockResolvedValue(usuario({ nombre: 'Ana María' }));

    montar();

    await userEvent.clear(screen.getByLabelText('Nombre'));
    await userEvent.type(screen.getByLabelText('Nombre'), 'Ana María');
    await userEvent.click(screen.getByRole('button', { name: /Guardar cambios/i }));

    await waitFor(() => {
      expect(api.updateUsuario).toHaveBeenCalled();
    });
    expect(screen.getByTestId('path-probe')).toHaveTextContent(UUID_A);
    expect(screen.getByLabelText('Nombre')).toHaveValue('Ana María');
  });
});