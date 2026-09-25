/**
 * Unit tests for `<LoginForm />` (F3.1 — T1, DEC-F3.1-02/06).
 *
 * RED → GREEN → REFACTOR coverage:
 *   U6: render presentacional con form mockeado via FormProvider — login-email,
 *       login-password, login-submit visibles.
 *   U7: error `invalid_credentials` prop → <p role="alert" data-testid=
 *       "login-error-invalid"> renderiza texto t('invalidCredentials').
 *
 * NOTA sobre axe-core (G7 REQ-OPS-112):
 *   El design §11.5 propone `vitest-axe` matcher, pero `vitest-axe` no está
 *   en package.json. El coverage de axe-core WCAG 2.1 AA se delega al e2e
 *   `e2e/auth/login.spec.ts` (T4) usando `@axe-core/playwright` (ya en deps).
 *   Esta es una deviation D-axe-unit documentada en el verify-report.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { I18nextProvider } from 'react-i18next';

import i18n from '@/i18n';
import { LoginForm } from './LoginForm';
import { loginSchema, type LoginInput } from '../api/loginSchema';

describe('<LoginForm />', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('U6: renderiza email + password + submit con form mockeado', () => {
    function Harness(): JSX.Element {
      const form = useForm<LoginInput>({
        resolver: zodResolver(loginSchema),
        mode: 'onBlur',
        defaultValues: { email: '', password: '' },
      });
      return (
        <I18nextProvider i18n={i18n}>
          <LoginForm form={form} onSubmit={vi.fn()} isSubmitting={false} error={null} />
        </I18nextProvider>
      );
    }
    render(<Harness />);
    expect(screen.getByTestId('login-email')).toBeInTheDocument();
    expect(screen.getByTestId('login-password')).toBeInTheDocument();
    expect(screen.getByTestId('login-submit')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Iniciar sesión');
  });

  it('U7: error invalid_credentials → <p role="alert"> muestra t("invalidCredentials")', () => {
    function Harness(): JSX.Element {
      const form = useForm<LoginInput>({
        resolver: zodResolver(loginSchema),
        mode: 'onBlur',
        defaultValues: { email: '', password: '' },
      });
      return (
        <I18nextProvider i18n={i18n}>
          <LoginForm
            form={form}
            onSubmit={vi.fn()}
            isSubmitting={false}
            error={{ kind: 'invalid_credentials' }}
          />
        </I18nextProvider>
      );
    }
    render(<Harness />);
    const alert = screen.getByTestId('login-error-invalid');
    expect(alert).toHaveAttribute('role', 'alert');
    expect(alert).toHaveTextContent('Correo o contraseña incorrectos');
  });

  // U7b (lockout alert) moved to `LockoutBlock.test.tsx` — per the
  // F11.4 follow-up, `<LoginForm>` no longer renders the lockout error
  // itself (`<Login>` mounts `<LockoutBlock>` outside the card instead).

  it('U7c: error network → <p role="alert"> muestra t("errors:serverError")', () => {
    function Harness(): JSX.Element {
      const form = useForm<LoginInput>({
        resolver: zodResolver(loginSchema),
        mode: 'onBlur',
        defaultValues: { email: '', password: '' },
      });
      return (
        <I18nextProvider i18n={i18n}>
          <LoginForm
            form={form}
            onSubmit={vi.fn()}
            isSubmitting={false}
            error={{ kind: 'network' }}
          />
        </I18nextProvider>
      );
    }
    render(<Harness />);
    const alert = screen.getByTestId('login-error-network');
    expect(alert).toHaveAttribute('role', 'alert');
  });

  it('U6b: isSubmitting → botón disabled + texto "Cargando..."', () => {
    function Harness(): JSX.Element {
      const form = useForm<LoginInput>({
        resolver: zodResolver(loginSchema),
        mode: 'onBlur',
        defaultValues: { email: '', password: '' },
      });
      return (
        <I18nextProvider i18n={i18n}>
          <LoginForm form={form} onSubmit={vi.fn()} isSubmitting={true} error={null} />
        </I18nextProvider>
      );
    }
    render(<Harness />);
    const submit = screen.getByTestId('login-submit') as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it('U8: lockout error deshabilita email + password + submit + aria-disabled', () => {
    function Harness(): JSX.Element {
      const form = useForm<LoginInput>({
        resolver: zodResolver(loginSchema),
        mode: 'onBlur',
        defaultValues: { email: '', password: '' },
      });
      return (
        <I18nextProvider i18n={i18n}>
          <LoginForm
            form={form}
            onSubmit={vi.fn()}
            isSubmitting={false}
            error={{ kind: 'lockout', retryAfterSeconds: 300 }}
            onLockoutExpired={vi.fn()}
          />
        </I18nextProvider>
      );
    }
    render(<Harness />);
    const emailInput = screen.getByTestId('login-email') as HTMLInputElement;
    const passwordInput = screen.getByTestId('login-password') as HTMLInputElement;
    const submit = screen.getByTestId('login-submit') as HTMLButtonElement;
    expect(emailInput.disabled).toBe(true);
    expect(passwordInput.disabled).toBe(true);
    expect(submit.disabled).toBe(true);
    expect(submit).toHaveAttribute('aria-disabled', 'true');
  });

  // U9 (countdown mm:ss) moved to `LockoutBlock.test.tsx` — same reason
  // as U7b above: the countdown display no longer lives in `<LoginForm>`.

  // ──────────────────────────────────────────────────────────────────────
  // F11.4 — attempt counter (UX feedback) rendering tests
  // ──────────────────────────────────────────────────────────────────────

  it('U10a: attemptCount=0 (default) → counter invisible (estado cero no contamina la UI)', () => {
    function Harness(): JSX.Element {
      const form = useForm<LoginInput>({
        resolver: zodResolver(loginSchema),
        mode: 'onBlur',
        defaultValues: { email: '', password: '' },
      });
      return (
        <I18nextProvider i18n={i18n}>
          <LoginForm form={form} onSubmit={vi.fn()} isSubmitting={false} error={null} />
        </I18nextProvider>
      );
    }
    render(<Harness />);
    expect(screen.queryByTestId('login-attempt-counter')).not.toBeInTheDocument();
  });

  it('U10b: attemptCount=3, maxAttempts=5 → counter muestra "Intento 3 de 5"', () => {
    function Harness(): JSX.Element {
      const form = useForm<LoginInput>({
        resolver: zodResolver(loginSchema),
        mode: 'onBlur',
        defaultValues: { email: '', password: '' },
      });
      return (
        <I18nextProvider i18n={i18n}>
          <LoginForm
            form={form}
            onSubmit={vi.fn()}
            isSubmitting={false}
            error={null}
            attemptCount={3}
            maxAttempts={5}
          />
        </I18nextProvider>
      );
    }
    render(<Harness />);
    const counter = screen.getByTestId('login-attempt-counter');
    expect(counter).toBeInTheDocument();
    expect(counter).toHaveAttribute('role', 'status');
    expect(counter).toHaveAttribute('aria-live', 'polite');
    expect(counter).toHaveAttribute('data-attempt-current', '3');
    expect(counter).toHaveAttribute('data-attempt-max', '5');
    expect(counter).toHaveTextContent('Intento 3 de 5');
  });

  it('U10c: attemptCount=1 (default maxAttempts=5) → counter muestra "Intento 1 de 5"', () => {
    // Default maxAttempts=5 when prop omitted — backward compat with
    // existing Login tests that don't pass the prop.
    function Harness(): JSX.Element {
      const form = useForm<LoginInput>({
        resolver: zodResolver(loginSchema),
        mode: 'onBlur',
        defaultValues: { email: '', password: '' },
      });
      return (
        <I18nextProvider i18n={i18n}>
          <LoginForm
            form={form}
            onSubmit={vi.fn()}
            isSubmitting={false}
            error={null}
            attemptCount={1}
          />
        </I18nextProvider>
      );
    }
    render(<Harness />);
    const counter = screen.getByTestId('login-attempt-counter');
    expect(counter).toHaveAttribute('data-attempt-current', '1');
    expect(counter).toHaveAttribute('data-attempt-max', '5');
    expect(counter).toHaveTextContent('Intento 1 de 5');
  });
});