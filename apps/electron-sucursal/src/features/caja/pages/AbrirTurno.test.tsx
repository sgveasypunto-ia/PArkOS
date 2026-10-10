/**
 * `<AbrirTurno />` container — the operator is never asked for a value.
 *
 * The base de caja is a branch parameter (configured by administration). The
 * screen resolves it, opens the shift on its own and shows a notice with the
 * base and who to ask if in doubt.
 *
 *   U9:  base configured → POST once → notice marker left → navigate('/') (dashboard shows it).
 *   U10: POST 409 `sesion_already_active` → alert + "Ir al turno".
 *   U11: no base configured → blocking notice, NO POST.
 *   U12: the screen renders no input at all.
 *   U13: network failure → alert + "Reintentar", which opens the shift.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type * as ReactRouterDom from 'react-router-dom';

import '@/i18n';

const mockUseAuth = vi.fn();
const mockNavigate = vi.fn();
const mockAbrirSesion = vi.fn();
const mockUseBaseCajaEfectiva = vi.fn();
const mockSetTokens = vi.fn();

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: unknown) => unknown) => selector({}),
    { getState: () => ({ setTokens: mockSetTokens }) },
  ),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof ReactRouterDom>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../hooks/useBaseCajaEfectiva', () => ({
  useBaseCajaEfectiva: (...args: unknown[]) => mockUseBaseCajaEfectiva(...args),
}));

vi.mock('../api/sesionActivaApi', () => ({
  abrirSesion: (...args: unknown[]) => mockAbrirSesion(...args),
  SesionAlreadyActiveError: class extends Error {
    override readonly name = 'SesionAlreadyActiveError';
    constructor(
      public readonly status: number,
      public readonly body: string,
      public readonly url: string,
    ) {
      super('sesion_already_active');
    }
  },
}));

import { SesionAlreadyActiveError } from '../api/sesionActivaApi';
import { AbrirTurno } from './AbrirTurno';

const SUC = '00000000-0000-0000-0000-000000000002';
const USR = '00000000-0000-0000-0000-000000000001';

const OPENED = {
  uuid: 'new-uuid',
  uuid_sucursal: SUC,
  uuid_usuario: USR,
  valor_inicial_efectivo: 100000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-15T08:00:00Z',
  timestamp_cierre: null,
  access_token: 'mock-access-token',
  refresh_token: 'mock-refresh-token',
  expires_in: 3600,
};

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
  mockUseAuth.mockReturnValue({
    user: { uuid: USR, email: 'op@test.co' },
    sucursal: { uuid: SUC, nombre: 'Sucursal Centro' },
  });
  mockUseBaseCajaEfectiva.mockReturnValue({ base: 100000, isLoading: false, error: undefined });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('<AbrirTurno /> container — sin pedir valores', () => {
  it('U9: con base configurada abre el turno una sola vez, deja el aviso pendiente y va al dashboard', async () => {
    mockAbrirSesion.mockResolvedValueOnce(OPENED);
    render(<AbrirTurno />);

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true }));
    expect(mockAbrirSesion).toHaveBeenCalledTimes(1);
    // The dashboard shows the notice for this very session.
    expect(window.sessionStorage.getItem('parkos:turno-base-aviso')).toBe('new-uuid');
    expect(mockAbrirSesion).toHaveBeenCalledWith(
      expect.objectContaining({
        uuid_sucursal: SUC,
        uuid_usuario: USR,
        valor_inicial_efectivo: 100000,
        valor_inicial_datafono: 0,
      }),
    );
    expect(mockSetTokens).toHaveBeenCalledWith('mock-access-token', 'mock-refresh-token', 3600);
  });

  it('U10: POST 409 → alerta de turno ya abierto + botón "Ir al turno"', async () => {
    mockAbrirSesion.mockRejectedValueOnce(
      new SesionAlreadyActiveError(409, '{"error":"sesion_already_active"}', '/x'),
    );
    const user = userEvent.setup();
    render(<AbrirTurno />);

    expect(await screen.findByTestId('abrir-turno-error-sesion-ya-abierta')).not.toBeNull();
    await user.click(screen.getByTestId('abrir-turno-ir-al-turno'));
    expect(mockNavigate).toHaveBeenCalledWith('/');
  });

  it('U11: sin base configurada no abre el turno y dirige al supervisor/administrador', async () => {
    mockUseBaseCajaEfectiva.mockReturnValue({ base: null, isLoading: false, error: undefined });
    render(<AbrirTurno />);

    const aviso = await screen.findByTestId('abrir-turno-sin-base');
    expect(aviso.textContent).toContain('administrador del sistema');
    expect(mockAbrirSesion).not.toHaveBeenCalled();
  });

  it('U12: la pantalla no pide ningún valor (cero inputs)', async () => {
    mockAbrirSesion.mockResolvedValueOnce(OPENED);
    render(<AbrirTurno />);
    expect(document.querySelectorAll('input, textarea, select')).toHaveLength(0);
    await waitFor(() => expect(mockNavigate).toHaveBeenCalled());
  });

  it('U13: fallo de red → alerta + "Reintentar" vuelve a abrir el turno', async () => {
    mockAbrirSesion.mockRejectedValueOnce(new Error('network'));
    mockAbrirSesion.mockResolvedValueOnce(OPENED);
    const user = userEvent.setup();
    render(<AbrirTurno />);

    expect(await screen.findByTestId('abrir-turno-error-network')).not.toBeNull();
    await user.click(screen.getByTestId('abrir-turno-reintentar'));

    await waitFor(() => expect(mockAbrirSesion).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true }));
  });
});
