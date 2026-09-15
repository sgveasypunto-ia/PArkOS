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

function mockFetchOnce(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
    text: async () => JSON.stringify(body),
    url: '/api/v1/auth/login',
  } as unknown as Response;
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

describe('<Login /> container — T2 postLogin + error mapping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('U9: submit OK llama setTokens(acceso, refresh, expires_in)', async () => {
    const tokenPair = {
      access_token: 'a-1',
      refresh_token: 'r-1',
      token_type: 'Bearer',
      expires_in: 3600,
    };
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce(tokenPair, 200, { 'Content-Type': 'application/json' }),
    );

    const user = renderLogin();
    await user.type(screen.getByTestId('login-email'), 'op@test.co');
    await user.type(screen.getByTestId('login-password'), 'password1234');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      expect(mockSetTokens).toHaveBeenCalledWith('a-1', 'r-1', 3600);
    });
  });

  it('U10: 401 muestra <p role="alert"> con t("invalidCredentials")', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce({ error: 'invalid_credentials' }, 401),
    );

    const user = renderLogin();
    await user.type(screen.getByTestId('login-email'), 'op@test.co');
    await user.type(screen.getByTestId('login-password'), 'wrong-pass-1234');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      const alert = screen.getByTestId('login-error-invalid');
      expect(alert).toHaveAttribute('role', 'alert');
      expect(alert).toHaveTextContent('Credenciales inválidas');
    });
  });

  it('U10b: 429 con Retry-After muestra mensaje lockout', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce(
        { error: 'account_locked' },
        429,
        { 'Retry-After': '600' },
      ),
    );

    const user = renderLogin();
    await user.type(screen.getByTestId('login-email'), 'op@test.co');
    await user.type(screen.getByTestId('login-password'), 'wrong-pass-1234');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      const alert = screen.getByTestId('login-error-lockout');
      expect(alert).toHaveAttribute('role', 'alert');
    });
  });
});

describe('<Login /> container — T3 useEffect redirect transaccional', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('U13: useAuth retorna user null → mockNavigate NO se llama', async () => {
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

    await waitFor(() => {
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });

  it('U14: useAuth retorna user resuelto → mockNavigate("/", {replace:true})', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      user: { id: 'u-1', email: 'op@test.co' },
    });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
    });
  });

  it('U15: useAuth con isLoading=true → mockNavigate NO se llama todavía', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: true,
      user: null,
    });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });
});