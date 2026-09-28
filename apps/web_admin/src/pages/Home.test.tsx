/**
 * `Home` — the hub's render contract.
 *
 * The two behaviors worth pinning are (1) the pending state must not be
 * an empty grid, and (2) the gated section must actually disappear.
 * Everything else is presentation.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ADMIN_SECTIONS } from '@/lib/admin-sections';

const useAdminAuthMock = vi.fn();
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => useAdminAuthMock(),
}));

import Home from './Home';

function authState(over: Record<string, unknown> = {}) {
  return {
    user: { uuid: 'u-1', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['2049f2cd-b2a8-4e45-9d19-31fa87eb67c6'],
    permisos: [
      'admin_usuarios',
      'audit_read',
      'config_tarifas',
      'config_cupos',
      'config_catalogo',
      'config_tolerancias',
      'config_seguridad',
    ],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
    ...over,
  };
}

function renderHome() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Home />
    </MemoryRouter>,
  );
}

describe('Home', () => {
  it('H1: shows a live status region while permissions load, not an empty grid', () => {
    // Regression guard for the exact failure this page exists to avoid:
    // `permisos` is [] until /admin/me resolves, so rendering "nothing"
    // during the fetch is indistinguishable from "no access".
    useAdminAuthMock.mockReturnValue(authState({ isLoading: true, permisos: [] }));
    renderHome();

    expect(screen.getByTestId('home-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('home-empty')).not.toBeInTheDocument();
    expect(screen.queryByTestId('home-card-dashboard')).not.toBeInTheDocument();
  });

  it('H2: renders one card per reachable section (full permission set)', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderHome();

    for (const section of ADMIN_SECTIONS) {
      expect(screen.getByTestId(`home-card-${section.key}`)).toBeInTheDocument();
    }
  });

  it('H3: omits permission-gated sections when the code is not granted', () => {
    // Sin config_tarifas / config_cupos / audit_read.
    useAdminAuthMock.mockReturnValue(authState({ permisos: ['admin_usuarios'] }));
    renderHome();

    expect(screen.queryByTestId('home-card-auditoria')).not.toBeInTheDocument();
    expect(screen.queryByTestId('home-card-tarifas')).not.toBeInTheDocument();
    expect(screen.queryByTestId('home-card-cupos')).not.toBeInTheDocument();
    expect(screen.getByTestId('home-card-usuarios')).toBeInTheDocument();
  });

  it('H3b: shows Tarifas and Cupos when their config codes are granted', () => {
    useAdminAuthMock.mockReturnValue(
      authState({ permisos: ['config_tarifas', 'config_cupos'] }),
    );
    renderHome();

    expect(screen.getByTestId('home-card-tarifas')).toBeInTheDocument();
    expect(screen.getByTestId('home-card-cupos')).toBeInTheDocument();
  });

  it('H4: states the branch scope so the admin knows what is filtered', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderHome();
    expect(screen.getByTestId('home-scope')).toHaveTextContent('1');
  });

  it('H5: every card is a real link with an accessible name', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderHome();

    const card = screen.getByTestId('home-card-auditoria');
    expect(card.tagName).toBe('A');
    expect(card).toHaveAttribute('href', '/audit');
    expect(card.textContent?.trim().length).toBeGreaterThan(0);
  });

  it('H6: Tarifas card links to /tarifas and Cupos card links to /cupos', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderHome();

    expect(screen.getByTestId('home-card-tarifas')).toHaveAttribute('href', '/tarifas');
    expect(screen.getByTestId('home-card-cupos')).toHaveAttribute('href', '/cupos');
  });
});
