/**
 * `AdminChrome` — the persistent frame.
 *
 * Pins the three things that are easy to break silently: the nav mirrors
 * the backend gates, the active section is announced via `aria-current`,
 * and logout always navigates away even when the server call rejects.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const useAdminAuthMock = vi.fn();
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => useAdminAuthMock(),
}));

import { AdminChrome } from './AdminChrome';

function authState(over: Record<string, unknown> = {}) {
  return {
    user: { uuid: 'u-1', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['2049f2cd-b2a8-4e45-9d19-31fa87eb67c6'],
    permisos: ['admin_usuarios', 'audit_read'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: vi.fn(async () => undefined),
    ...over,
  };
}

function renderChrome(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<AdminChrome />}>
          <Route path="/" element={<div data-testid="outlet-home" />} />
          <Route path="/audit" element={<div data-testid="outlet-audit" />} />
          <Route path="/login" element={<div data-testid="outlet-login" />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('AdminChrome', () => {
  it('C1: renders a nav landmark with one link per reachable section', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderChrome();

    expect(screen.getByRole('navigation')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /auditor/i })).toHaveAttribute('href', '/audit');
    expect(screen.getByRole('link', { name: /sucursales/i })).toBeInTheDocument();
  });

  it('C2: hides a gated nav link when the permission is absent', () => {
    useAdminAuthMock.mockReturnValue(authState({ permisos: [] }));
    renderChrome();

    expect(screen.queryByRole('link', { name: /auditor/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sucursales/i })).toBeInTheDocument();
  });

  it('C3: marks the current section with aria-current', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderChrome('/audit');

    expect(screen.getByRole('link', { name: /auditor/i })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: /sucursales/i })).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('C4: logout navigates to /login', async () => {
    const logout = vi.fn(async () => undefined);
    useAdminAuthMock.mockReturnValue(authState({ logout }));
    renderChrome();

    await userEvent.click(screen.getByTestId('admin-logout'));

    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('outlet-login')).toBeInTheDocument());
  });

  it('C5: logout still navigates when the server call rejects', () => {
    // `logoutAdmin` clears local credentials in a `finally`, so it does
    // not reject in practice — but the chrome must not depend on that.
    const logout = vi.fn(async () => {
      throw new Error('offline');
    });
    useAdminAuthMock.mockReturnValue(authState({ logout }));
    renderChrome();

    return userEvent
      .click(screen.getByTestId('admin-logout'))
      .then(() => waitFor(() => expect(screen.getByTestId('outlet-login')).toBeInTheDocument()));
  });

  it('C6: surfaces the branch scope and the role', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderChrome();

    expect(screen.getByText('admin')).toBeInTheDocument();
    expect(screen.getByText(/sucursales/)).toBeInTheDocument();
  });
});
