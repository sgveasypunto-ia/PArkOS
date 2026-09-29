/**
 * `TopNav` — the identity bar that wraps every authed route except
 * `/login`. The test pins the contract the rest of the app relies on:
 *   - T1: email is visible and clickable as the user menu trigger.
 *   - T2: brand link points to `/`.
 *   - T3: dropdown opens to show "Mi perfil", "Configuración" (disabled),
 *         and "Cerrar sesión".
 *   - T4: "Cerrar sesión" calls the auth logout and navigates to
 *         `/login` even when the server call rejects.
 *   - T5: the item swaps to "Saliendo…" and stays disabled while the
 *         logout promise is pending.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';

const useAdminAuthMock = vi.fn();
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => useAdminAuthMock(),
}));

import { TopNav } from './TopNav';

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
    logout: vi.fn(async () => undefined),
    ...over,
  };
}

function renderTopNav(initialPath = '/') {
  // Mirrors the production layout: `<TopNav />` is a sibling of the
  // route's content, not a parent that owns an `<Outlet />`. The
  // test wraps the layout in a fragment that renders the trigger
  // plus `<Outlet />` so the navigated child becomes queryable.
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          element={
            <>
              <TopNav />
              <Outlet />
            </>
          }
        >
          <Route path="/" element={<div data-testid="outlet-home" />} />
          <Route path="/perfil" element={<div data-testid="outlet-perfil" />} />
          <Route path="/login" element={<div data-testid="outlet-login" />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('TopNav', () => {
  it('T1: shows the user email and the brand', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderTopNav();

    expect(screen.getByTestId('topnav')).toBeInTheDocument();
    expect(screen.getByTestId('topnav-email')).toHaveTextContent('admin@parkos.local');
    // Avatar falls back to the first letter of the email local part.
    expect(screen.getByTestId('topnav-avatar')).toHaveTextContent('A');
  });

  it('T2: the brand link points to /', () => {
    useAdminAuthMock.mockReturnValue(authState());
    renderTopNav();

    const brand = screen.getByTestId('topnav-brand');
    expect(brand.tagName).toBe('A');
    expect(brand).toHaveAttribute('href', '/');
  });

  it('T3: the user menu opens with profile, settings (disabled) and sign out', async () => {
    const user = userEvent.setup();
    useAdminAuthMock.mockReturnValue(authState());
    renderTopNav();

    await user.click(screen.getByTestId('topnav-user-menu'));

    const profile = await screen.findByTestId('topnav-profile');
    const settings = screen.getByTestId('topnav-settings');
    const logout = screen.getByTestId('topnav-logout');

    expect(profile).toHaveAttribute('role', 'menuitem');
    expect(profile).toHaveTextContent(/mi perfil/i);
    expect(settings).toHaveAttribute('aria-disabled', 'true');
    expect(logout).toHaveTextContent(/cerrar sesi[oó]n/i);
  });

  it('T4: Cerrar sesión calls logout and navigates to /login', async () => {
    const user = userEvent.setup();
    const logout = vi.fn(async () => undefined);
    useAdminAuthMock.mockReturnValue(authState({ logout }));
    renderTopNav();

    await user.click(screen.getByTestId('topnav-user-menu'));
    await user.click(screen.getByTestId('topnav-logout'));

    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('outlet-login')).toBeInTheDocument());
  });

  it('T5: still navigates to /login when the server logout rejects', async () => {
    const user = userEvent.setup();
    const logout = vi.fn(async () => {
      throw new Error('offline');
    });
    useAdminAuthMock.mockReturnValue(authState({ logout }));
    renderTopNav();

    await user.click(screen.getByTestId('topnav-user-menu'));
    await user.click(screen.getByTestId('topnav-logout'));

    await waitFor(() => expect(logout).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('outlet-login')).toBeInTheDocument());
  });

  it('T6: shows "Saliendo…" and disables the item while logout is pending', async () => {
    const user = userEvent.setup();
    let resolveLogout: () => void = () => undefined;
    const logout = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveLogout = resolve;
        }),
    );
    useAdminAuthMock.mockReturnValue(authState({ logout }));
    renderTopNav();

    await user.click(screen.getByTestId('topnav-user-menu'));
    await user.click(screen.getByTestId('topnav-logout'));

    // The item is still mounted (closeOnSelect={false} keeps the
    // menu open during async work) and the label has flipped to
    // the "Saliendo…" copy. The promise hasn't resolved yet, so
    // we are still mid-sign-out. The `DropdownMenuItem` uses
    // `aria-disabled` (not the native `disabled` attribute) so the
    // element stays focusable for screen readers — see the primitive
    // docblock for the rationale.
    const item = await screen.findByTestId('topnav-logout');
    expect(item).toHaveTextContent(/saliendo/i);
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(item).toHaveAttribute('tabindex', '-1');

    resolveLogout();
  });

  it('T7: Mi perfil navigates to /perfil', async () => {
    const user = userEvent.setup();
    useAdminAuthMock.mockReturnValue(authState());
    renderTopNav('/');

    await user.click(screen.getByTestId('topnav-user-menu'));
    await user.click(screen.getByTestId('topnav-profile'));

    await waitFor(() => expect(screen.getByTestId('outlet-perfil')).toBeInTheDocument());
  });
});
