/**
 * `<Perfil />` — placeholder for the operator's own profile. The page
 * reads from `useAdminAuth()` and renders the immutable identity. The
 * test pins:
 *   - P1: each row is populated from the hook.
 *   - P2: the back link points at `/`.
 *   - P3: empty fields fall back to the em-dash instead of rendering
 *         an empty cell.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const useAdminAuthMock = vi.fn();
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => useAdminAuthMock(),
}));

import Perfil from './Perfil';

const ADMIN_UUID = '00000000-0000-0000-0000-0000000000ad';

function authState(over: Record<string, unknown> = {}) {
  return {
    user: { uuid: ADMIN_UUID, email: 'admin@parkos.local', nombre: null, apellido: null },
    rol: 'admin',
    sucursalUuids: ['2049f2cd-b2a8-4e45-9d19-31fa87eb67c6'],
    permisos: [],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
    ...over,
  };
}

function renderPerfil() {
  return render(
    <MemoryRouter initialEntries={['/perfil']}>
      <Perfil />
    </MemoryRouter>,
  );
}

describe('Perfil', () => {
  it('P1: renders the identity rows from useAdminAuth', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderPerfil();

    expect(screen.getByTestId('page-perfil')).toBeInTheDocument();
    expect(screen.getByTestId('perfil-row-email')).toHaveTextContent('admin@parkos.local');
    expect(screen.getByTestId('perfil-row-rol')).toHaveTextContent('admin');
    expect(screen.getByTestId('perfil-row-uuid')).toHaveTextContent(ADMIN_UUID);
    expect(screen.getByTestId('perfil-row-sucursales')).toHaveTextContent('1');
  });

  it('P2: the back link points at /', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderPerfil();

    const back = screen.getByTestId('perfil-back');
    expect(back.tagName).toBe('A');
    expect(back).toHaveAttribute('href', '/');
  });

  it('P3: missing email and rol fall back to em-dash', () => {
    useAdminAuthMock.mockReturnValue(
      authState({
        user: { uuid: ADMIN_UUID, email: null, nombre: null, apellido: null },
        rol: null,
      }),
    );
    renderPerfil();

    const email = screen.getByTestId('perfil-row-email');
    const rol = screen.getByTestId('perfil-row-rol');
    expect(email.textContent).toMatch(/—/);
    expect(rol.textContent).toMatch(/—/);
  });
});
