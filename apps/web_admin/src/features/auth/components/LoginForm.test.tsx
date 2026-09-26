/**
 * `LoginForm.test.tsx` — Unit tests for the presentational
 * `<LoginForm />` component (IT-1.10).
 *
 * Uses a REAL `useForm()` instance from react-hook-form (with the
 * real `zodResolver`) so the rendered tree exercises the same
 * component path as production. Mocking `UseFormReturn` directly
 * is brittle (RHF accesses fields we don't fully understand).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { LoginForm } from './LoginForm';
import { loginSchema, type LoginInput } from '../api/loginSchema';

function Harness(props: Omit<Parameters<typeof LoginForm>[0], 'form'>): JSX.Element {
  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });
  return <LoginForm {...props} form={form} />;
}

describe('LoginForm', () => {
  it('renders the email and password fields with the submit button', () => {
    render(
      <Harness
        onSubmit={vi.fn()}
        isSubmitting={false}
        isLocked={false}
        lockoutFormatted={null}
        errorState={null}
        attemptCount={0}
        maxAttempts={5}
      />,
    );
    expect(screen.getByTestId('login-email')).toBeInTheDocument();
    expect(screen.getByTestId('login-password')).toBeInTheDocument();
    expect(screen.getByTestId('login-submit')).toBeInTheDocument();
  });

  it('does NOT render the attempt counter when attemptCount is 0', () => {
    render(
      <Harness
        onSubmit={vi.fn()}
        isSubmitting={false}
        isLocked={false}
        lockoutFormatted={null}
        errorState={null}
        attemptCount={0}
        maxAttempts={5}
      />,
    );
    expect(screen.queryByTestId('login-attempt-counter')).toBeNull();
  });

  it('renders the attempt counter when attemptCount > 0', () => {
    render(
      <Harness
        onSubmit={vi.fn()}
        isSubmitting={false}
        isLocked={false}
        lockoutFormatted={null}
        errorState={null}
        attemptCount={2}
        maxAttempts={5}
      />,
    );
    expect(screen.getByTestId('login-attempt-counter')).toBeInTheDocument();
  });

  it('renders the lockout block with the formatted countdown when locked', () => {
    render(
      <Harness
        onSubmit={vi.fn()}
        isSubmitting={false}
        isLocked
        lockoutFormatted="00:42"
        errorState={null}
        attemptCount={5}
        maxAttempts={5}
      />,
    );
    expect(screen.getByTestId('lockout-block')).toBeInTheDocument();
    expect(screen.getByTestId('lockout-block').textContent).toMatch(/00:42/);
  });

  it('renders the inline error with role=alert when errorState is set', () => {
    render(
      <Harness
        onSubmit={vi.fn()}
        isSubmitting={false}
        isLocked={false}
        lockoutFormatted={null}
        errorState={{ kind: 'invalid_credentials' }}
        attemptCount={1}
        maxAttempts={5}
      />,
    );
    const alert = screen.getByTestId('login-error');
    expect(alert).toBeInTheDocument();
    expect(alert.getAttribute('role')).toBe('alert');
  });

  it('disables inputs and submit when isLocked', () => {
    render(
      <Harness
        onSubmit={vi.fn()}
        isSubmitting={false}
        isLocked
        lockoutFormatted="00:30"
        errorState={null}
        attemptCount={5}
        maxAttempts={5}
      />,
    );
    const fieldset = screen.getByTestId('login-email').closest('fieldset');
    expect(fieldset?.disabled).toBe(true);
    expect((screen.getByTestId('login-submit') as HTMLButtonElement).disabled).toBe(true);
  });

  it('disables the submit button (but keeps inputs enabled) while submitting', () => {
    render(
      <Harness
        onSubmit={vi.fn()}
        isSubmitting
        isLocked={false}
        lockoutFormatted={null}
        errorState={null}
        attemptCount={0}
        maxAttempts={5}
      />,
    );
    expect((screen.getByTestId('login-submit') as HTMLButtonElement).disabled).toBe(true);
  });

  it('calls onSubmit when the form is submitted with valid values', async () => {
    const onSubmit = vi.fn();
    render(
      <Harness
        onSubmit={onSubmit}
        isSubmitting={false}
        isLocked={false}
        lockoutFormatted={null}
        errorState={null}
        attemptCount={0}
        maxAttempts={5}
      />,
    );
    const user = userEvent.setup();
    await user.type(screen.getByTestId('login-email'), 'admin@parkos.local');
    await user.type(screen.getByTestId('login-password'), 'Pass1234word');
    await user.click(screen.getByTestId('login-submit'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    // `toHaveBeenCalledWith` fails on the native SubmitEvent that RHF
    // passes alongside the values (it has a circular reference). Inspect
    // the first positional argument instead.
    const firstCall = onSubmit.mock.calls[0]?.[0] as Record<string, unknown> | undefined;
    expect(firstCall).toEqual({
      email: 'admin@parkos.local',
      password: 'Pass1234word',
    });
  });
});
