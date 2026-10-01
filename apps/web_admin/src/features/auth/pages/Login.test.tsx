/**
 * `Login.test.tsx` — Container integration tests for the `<Login />`
 * container (IT-1.10).
 *
 * Mocks `@parkos/ui-kit/hooks` (for `useAdminAuth`) and the local
 * `../api/loginApi` so we can exercise the success / 401 / 429
 * branches without a real backend.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Navigate, Route, Routes } from 'react-router-dom';

const useAuthMock = vi.fn();
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => useAuthMock(),
}));

const useAuthStoreMock = vi.fn();
vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: (selector: (s: { setTokens: unknown; clear: unknown }) => unknown) =>
    useAuthStoreMock(selector),
}));

const postLoginMock = vi.fn();
vi.mock('../api/loginApi', async () => {
  const actual = (await vi.importActual('../api/loginApi')) as Record<string, unknown>;
  return {
    ...actual,
    postLogin: (...args: unknown[]) => postLoginMock(...args),
  };
});

import { Login } from './Login';

function setup(): JSX.Element {
  return (
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Navigate to="/seleccionar-sucursal" replace />} />
      <Route
        path="/seleccionar-sucursal"
        element={<div data-testid="picker-target">picker</div>}
      />
      <Route path="/dashboard" element={<div data-testid="dashboard-target">dashboard</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('Login container', () => {
  it('renders the form on /login', () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
    });
    useAuthStoreMock.mockImplementation((selector) =>
      selector({ setTokens: vi.fn(), clear: vi.fn() }),
    );
    render(setup());
    expect(screen.getByTestId('page-login')).toBeInTheDocument();
    expect(screen.getByTestId('login-email')).toBeInTheDocument();
    expect(screen.getByTestId('login-password')).toBeInTheDocument();
  });

  it('redirects to /seleccionar-sucursal when already authenticated', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { uuid: '00000000-0000-0000-0000-0000000000ad', email: 'admin@parkos.local' },
    });
    useAuthStoreMock.mockImplementation((selector) =>
      selector({ setTokens: vi.fn(), clear: vi.fn() }),
    );
    render(setup());
    await waitFor(() => {
      expect(screen.getByTestId('picker-target')).toBeInTheDocument();
    });
  });

  it('calls postLogin with email + password on submit', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
    });
    const setTokens = vi.fn();
    useAuthStoreMock.mockImplementation((selector) =>
      selector({ setTokens, clear: vi.fn() }),
    );
    postLoginMock.mockResolvedValue({
      access_token: 'a',
      refresh_token: 'b',
      temporary_token: null,
      token_type: 'Bearer',
      expires_in: 3600,
      must_change_password: false,
    });

    render(setup());
    const user = userEvent.setup();
    await user.type(screen.getByTestId('login-email'), 'admin@parkos.local');
    await user.type(screen.getByTestId('login-password'), 'Pass1234word');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      expect(postLoginMock).toHaveBeenCalledWith('admin@parkos.local', 'Pass1234word');
    });
    expect(setTokens).toHaveBeenCalledWith('a', 'b', 3600);
  });

  it('routes to the change-password form when login returns must_change_password', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
    });
    useAuthStoreMock.mockImplementation((selector) =>
      selector({ setTokens: vi.fn(), clear: vi.fn() }),
    );
    postLoginMock.mockResolvedValue({
      access_token: null,
      refresh_token: null,
      temporary_token: 'temp-jwt-purpose-must-change',
      token_type: 'Bearer',
      expires_in: 300,
      must_change_password: true,
    });

    render(setup());
    const user = userEvent.setup();
    await user.type(screen.getByTestId('login-email'), 'operador@parkos.local');
    await user.type(screen.getByTestId('login-password'), 'TempPassword!');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('page-must-change-password')).toBeInTheDocument();
    });
    expect(screen.getByTestId('change-password-new')).toBeInTheDocument();
    expect(screen.getByTestId('change-password-confirm')).toBeInTheDocument();
    // The change form's cancel button must drop us back to the login form
    // (the cancel handler clears mustChange state).
    await user.click(screen.getByTestId('change-password-cancel'));
    await waitFor(() => {
      expect(screen.getByTestId('page-login')).toBeInTheDocument();
    });
  });

  it('shows the invalid-credentials error on 401', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
    });
    useAuthStoreMock.mockImplementation((selector) =>
      selector({ setTokens: vi.fn(), clear: vi.fn() }),
    );
    const { InvalidCredentialsError } = await import('../api/loginApi');
    postLoginMock.mockRejectedValue(new InvalidCredentialsError());

    render(setup());
    const user = userEvent.setup();
    await user.type(screen.getByTestId('login-email'), 'admin@parkos.local');
    await user.type(screen.getByTestId('login-password'), 'wrongpassword');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('login-error')).toBeInTheDocument();
    });
  });

  it('shows the lockout countdown on 429', async () => {
    useAuthMock.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
    });
    useAuthStoreMock.mockImplementation((selector) =>
      selector({ setTokens: vi.fn(), clear: vi.fn() }),
    );
    const { AccountLockedError } = await import('../api/loginApi');
    postLoginMock.mockRejectedValue(new AccountLockedError(30));

    render(setup());
    const user = userEvent.setup();
    await user.type(screen.getByTestId('login-email'), 'admin@parkos.local');
    await user.type(screen.getByTestId('login-password'), 'anypassword');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('lockout-block')).toBeInTheDocument();
    });
  });
});
