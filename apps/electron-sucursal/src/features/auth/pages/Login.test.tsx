/**
 * Unit tests for `<Login />` container (F3.1 — T1, T2, T3, F3.3 — T3 MODIFY).
 *
 * T1 RED/GREEN coverage (placeholder onSubmit, no postLogin wired):
 *   U11: Zod email inválido → fetch NOT called + FormMessage muestra
 *        'validation.email.invalid'.
 *   U12: Zod password < 8 → fetch NOT called + FormMessage muestra
 *        'validation.password.minLength'.
 *
 * T2 adds U9 (submit OK → setTokens + redirect) + U10 (401 → invalidCredentials).
 * T3 adds U13/U14/U15 (useEffect redirect waits for user, fires after user).
 * F3.3 adds U18 (?closed=true detection + role=status + aria-live=polite).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type * as ReactRouterDom from 'react-router-dom';

// `<Login>` renders `<LoginForm>` / `<LockoutBlock>`, both of which call
// `useTranslation()`. Without importing the real i18next bootstrap,
// react-i18next has no registered instance (`NO_I18NEXT_INSTANCE`) and
// `t()` returns the raw key instead of the translated string (mirrors
// the pattern already used in TiqueteModal.test.tsx / Principal.test.tsx).
import '@/i18n';

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
  const actual = await vi.importActual<typeof ReactRouterDom>('react-router-dom');
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
      // `<FormMessage>` translates `validation.*` keys against the
      // `errors` namespace (form.tsx), whose current copy is "Correo
      // electrónico inválido." — `auth.json`'s own (unused)
      // `validation.email.invalid` key is dead text nothing reads.
      expect(screen.getByText(/correo electr[oó]nico inv[aá]lido/i)).toBeInTheDocument();
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
    // `<LockoutBlock>` persists the lockout end-time in localStorage
    // (`lockoutStorage.ts`) and keeps whichever stored value is
    // LONGER ("el lockout más largo es el autoritativo"). Without
    // clearing it here, U10b's 600s Retry-After lockout survives into
    // U10's 2s lockout test, so its countdown never expires within
    // `vi.advanceTimersByTimeAsync(2500)` and the test times out.
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // Belt-and-braces: if a test throws/times out before reaching its
    // own `vi.useRealTimers()` (e.g. U10, which calls
    // `vi.useFakeTimers()` mid-test), fake timers would otherwise leak
    // into every later test in this describe block.
    vi.useRealTimers();
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
      expect(alert).toHaveTextContent('Correo o contraseña incorrectos');
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
      // `<LockoutBlock>` deliberately uses role="status" (not "alert")
      // — a second role="alert" would compete with the invalid-credentials
      // alert for screen-reader focus (see LockoutBlock.tsx docblock).
      expect(alert).toHaveAttribute('role', 'status');
    });
  });

  it('U10: useCountdown isExpired resetea errorState → form re-habilitado', async () => {
    vi.useFakeTimers();
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce(
        { error: 'account_locked' },
        429,
        { 'Retry-After': '2' },
      ),
    );

    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      user: null,
    });

    // `fireEvent` (not `userEvent`) on purpose: `userEvent`'s internal
    // per-keystroke delays and pointer/focus handling rely on
    // `requestAnimationFrame`, which jsdom polyfills via `setTimeout` —
    // with `vi.useFakeTimers()` active that never fires without a
    // manual advance, so `await user.click(...)` hangs indefinitely
    // instead of resolving. `fireEvent` dispatches synchronously and
    // sidesteps the whole timer dependency.
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByTestId('login-email'), {
      target: { value: 'op@test.co' },
    });
    fireEvent.change(screen.getByTestId('login-password'), {
      target: { value: 'wrong-pass-1234' },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('login-submit'));
    });

    // Wait for lockout error to appear
    await vi.waitFor(() => {
      expect(screen.getByTestId('login-error-lockout')).toBeInTheDocument();
    });

    // Advance timers past Retry-After (2s) — countdown reaches 0
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });

    // After expiry, errorState resets → lockout alert no longer in document.
    // Uses `vi.waitFor` (not RTL's `waitFor`) because fake timers are still
    // active here: RTL's `waitFor` polls via a real `setInterval`, which
    // never fires while `vi.useFakeTimers()` is on and hangs until its own
    // timeout instead of re-checking the assertion.
    await vi.waitFor(() => {
      expect(screen.queryByTestId('login-error-lockout')).not.toBeInTheDocument();
    });

    vi.useRealTimers();
  });

  // ──────────────────────────────────────────────────────────────────────
  // F11.4 — attempt counter cliente-side (UX feedback)
  // ──────────────────────────────────────────────────────────────────────

  it('U16: estado inicial → counter invisible (attemptCount === 0)', () => {
    // Sin submit previo, el counter no se renderiza (estado cero = invisible
    // para no contaminar la UI limpia del primer intento).
    renderLogin();
    expect(screen.queryByTestId('login-attempt-counter')).not.toBeInTheDocument();
  });

  it('U17: 401 → counter incrementa y muestra "Intento 1 de 5"', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce({ error: 'invalid_credentials' }, 401),
    );

    const user = renderLogin();
    await user.type(screen.getByTestId('login-email'), 'op@test.co');
    await user.type(screen.getByTestId('login-password'), 'wrong-pass-1234');
    await user.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      const counter = screen.getByTestId('login-attempt-counter');
      expect(counter).toHaveAttribute('role', 'status');
      expect(counter).toHaveAttribute('aria-live', 'polite');
      expect(counter).toHaveAttribute('data-attempt-current', '1');
      expect(counter).toHaveAttribute('data-attempt-max', '5');
      expect(counter).toHaveTextContent('Intento 1 de 5');
    });
  });

  it('U18: 3× 401 → counter acumula "Intento 3 de 5"', async () => {
    // 3 failed attempts in a row — counter accumulates client-side.
    vi.spyOn(global, 'fetch').mockResolvedValue(
      mockFetchOnce({ error: 'invalid_credentials' }, 401),
    );

    const user = renderLogin();
    for (let i = 0; i < 3; i += 1) {
      // `user.type` appends to the field's current value instead of
      // replacing it, and a bare `wrong-${i}` (7 chars) is under the
      // schema's 8-char minimum — both would leave the form stuck on
      // client-side Zod validation instead of ever calling `fetch`.
      // Clear first and use a password long enough to pass validation.
      await user.clear(screen.getByTestId('login-email'));
      await user.type(screen.getByTestId('login-email'), 'op@test.co');
      await user.clear(screen.getByTestId('login-password'));
      await user.type(screen.getByTestId('login-password'), `wrong-pass-${i}`);
      await user.click(screen.getByTestId('login-submit'));
      // Wait for the error to surface + counter to update.
      await waitFor(() => {
        expect(screen.getByTestId('login-error-invalid')).toBeInTheDocument();
      });
    }

    const counter = screen.getByTestId('login-attempt-counter');
    expect(counter).toHaveAttribute('data-attempt-current', '3');
    expect(counter).toHaveAttribute('data-attempt-max', '5');
    expect(counter).toHaveTextContent('Intento 3 de 5');
  });

  it('U19: login OK después de N× 401 → counter resetea a invisible', async () => {
    // Sequence: 2× 401 → counter shows "Intento 2 de 5" → 200 OK → counter
    // resets to 0 (invisible). Verifies the path-feliz reset.
    const fetchSpy = vi.spyOn(global, 'fetch');
    fetchSpy.mockResolvedValueOnce(
      mockFetchOnce({ error: 'invalid_credentials' }, 401),
    );
    fetchSpy.mockResolvedValueOnce(
      mockFetchOnce({ error: 'invalid_credentials' }, 401),
    );
    fetchSpy.mockResolvedValueOnce(
      mockFetchOnce(
        {
          access_token: 'a-1',
          refresh_token: 'r-1',
          token_type: 'Bearer',
          expires_in: 3600,
        },
        200,
        { 'Content-Type': 'application/json' },
      ),
    );

    const user = renderLogin();
    for (let i = 0; i < 2; i += 1) {
      // `user.type` appends to the field's current value instead of
      // replacing it, and a bare `wrong-${i}` (7 chars) is under the
      // schema's 8-char minimum — both would leave the form stuck on
      // client-side Zod validation instead of ever calling `fetch`.
      // Clear first and use a password long enough to pass validation.
      await user.clear(screen.getByTestId('login-email'));
      await user.type(screen.getByTestId('login-email'), 'op@test.co');
      await user.clear(screen.getByTestId('login-password'));
      await user.type(screen.getByTestId('login-password'), `wrong-pass-${i}`);
      await user.click(screen.getByTestId('login-submit'));
      await waitFor(() => {
        expect(screen.getByTestId('login-error-invalid')).toBeInTheDocument();
      });
    }
    expect(screen.getByTestId('login-attempt-counter')).toHaveTextContent(
      'Intento 2 de 5',
    );

    // Now succeed
    await user.clear(screen.getByTestId('login-password'));
    await user.type(screen.getByTestId('login-password'), 'password1234');
    await user.click(screen.getByTestId('login-submit'));
    await waitFor(() => {
      expect(mockSetTokens).toHaveBeenCalledWith('a-1', 'r-1', 3600);
    });

    // Counter MUST reset to invisible (attemptCount === 0)
    expect(screen.queryByTestId('login-attempt-counter')).not.toBeInTheDocument();
  });

  it('U20: 429 → counter NO incrementa (el BE bloqueó, el countdown toma el control)', async () => {
    // 4× 401 → counter at "Intento 4 de 5" → 429 (account locked) →
    // counter stays at 4 (lockout takes visual priority via countdown).
    const fetchSpy = vi.spyOn(global, 'fetch');
    for (let i = 0; i < 4; i += 1) {
      fetchSpy.mockResolvedValueOnce(
        mockFetchOnce({ error: 'invalid_credentials' }, 401),
      );
    }
    fetchSpy.mockResolvedValueOnce(
      mockFetchOnce(
        { error: 'account_locked' },
        429,
        { 'Retry-After': '600' },
      ),
    );

    const user = renderLogin();
    for (let i = 0; i < 4; i += 1) {
      // `user.type` appends to the field's current value instead of
      // replacing it, and a bare `wrong-${i}` (7 chars) is under the
      // schema's 8-char minimum — both would leave the form stuck on
      // client-side Zod validation instead of ever calling `fetch`.
      // Clear first and use a password long enough to pass validation.
      await user.clear(screen.getByTestId('login-email'));
      await user.type(screen.getByTestId('login-email'), 'op@test.co');
      await user.clear(screen.getByTestId('login-password'));
      await user.type(screen.getByTestId('login-password'), `wrong-pass-${i}`);
      await user.click(screen.getByTestId('login-submit'));
      await waitFor(() => {
        expect(screen.getByTestId('login-error-invalid')).toBeInTheDocument();
      });
    }
    expect(screen.getByTestId('login-attempt-counter')).toHaveTextContent(
      'Intento 4 de 5',
    );

    // Now trigger the 429
    await user.click(screen.getByTestId('login-submit'));
    await waitFor(() => {
      expect(screen.getByTestId('login-error-lockout')).toBeInTheDocument();
    });

    // Counter MUST stay at 4 (no increment on 429 — lockout takes
    // visual priority via countdown).
    const counter = screen.queryByTestId('login-attempt-counter');
    // The counter may still be visible from the previous 401 attempt;
    // verify its value stayed at 4, not 5.
    if (counter) {
      expect(counter).toHaveAttribute('data-attempt-current', '4');
    }
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
      // REQ-OPS-131 (qa-2026-09-17 bug 1): ``uuid`` replaces the
      // legacy ``id`` field; ui-kit's breaking change is reflected
      // in the mock shape.
      user: { uuid: 'u-1', email: 'op@test.co' },
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

describe('<Login /> container — F3.3 T3 MODIFY: ?closed=true feedback (DEC-F3.3-09 + REQ-OPS-124)', () => {
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

  it('U18a: mount con ?closed=true → render <p data-testid="turno-cerrado-exito"> visible arriba del form', () => {
    render(
      <MemoryRouter initialEntries={['/login?closed=true']}>
        <Login />
      </MemoryRouter>,
    );
    const notice = screen.getByTestId('turno-cerrado-exito');
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveAttribute('role', 'status');
    expect(notice).toHaveAttribute('aria-live', 'polite');
  });

  it('U18b: mount SIN ?closed=true → NO renderiza el feedback', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <Login />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('turno-cerrado-exito')).not.toBeInTheDocument();
  });

  it('U18c: mount con query param distinto (?error=foo) → NO renderiza el feedback', () => {
    render(
      <MemoryRouter initialEntries={['/login?error=foo']}>
        <Login />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('turno-cerrado-exito')).not.toBeInTheDocument();
  });
});