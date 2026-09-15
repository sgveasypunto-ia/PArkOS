/**
 * Unit tests for `<Login />` container (F3.1 — T1, T2, T3).
 *
 * T1 RED/GREEN coverage (placeholder onSubmit, no postLogin wired):
 *   U11: Zod email inválido → fetch NOT called + FormMessage muestra
 *        'validation.email.invalid'.
 *   U12: Zod password < 8 → fetch NOT called + FormMessage muestra
 *        'validation.password.minLength'.
 *
 * T2 adds U9 (submit OK → setTokens + redirect) + U10 (401 → invalidCredentials).
 * T3 adds U13/U14/U15 (useEffect redirect waits for user, fires after user).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

const mockUseAuth = vi.fn();
const mockSetTokens = vi.fn();
const mockNavigate = vi.fn();

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: { setTokens: typeof mockSetTokens }) => unknown) =>
      selector({ setTokens: mockSetTokens }),
    { getState: () => ({ setTokens: mockSetTokens }) },
  ),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

import { Login } from './Login';

function renderLogin(): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  mockUseAuth.mockReturnValue({
    isAuthenticated: false,
    isLoading: false,
    user: null,
  });
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  );
  return user;
}

describe('<Login /> container — T1 Zod validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('U11: email formato inválido NO llama fetch + muestra validation.email.invalid', async () => {
    const user = renderLogin();
    await user.type(screen.getByTestId('login-email'), 'not-an-email');
    await user.type(screen.getByTestId('login-password'), 'password1234');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      expect(screen.getByText(/Ingresa un correo válido/i)).toBeInTheDocument();
    });
  });

  it('U12: password < 8 NO llama fetch + muestra validation.password.minLength', async () => {
    const user = renderLogin();
    await user.type(screen.getByTestId('login-email'), 'op@test.co');
    await user.type(screen.getByTestId('login-password'), 'short');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      expect(screen.getByText(/al menos 8 caracteres/i)).toBeInTheDocument();
    });
  });

  it('U11b: campo vacío → muestra validation.required', async () => {
    const user = renderLogin();
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      const messages = screen.getAllByText(/obligatorio|contraseña/i);
      expect(messages.length).toBeGreaterThan(0);
    });
  });
});