/**
 * `<LoginForm />` â€” presentational component for `web_admin` login
 * (IT-1.10). Receives everything it needs via props; no direct
 * coupling to `useAuth` or `postLogin`.
 *
 * DEC-UI-01 (mirror of DEC-F3.1-02 Container/Presentational split):
 *   The container (`<Login />` in `pages/Login.tsx`) owns state,
 *   navigation, side effects. This component owns layout and a11y.
 *
 * Accessibility (RNF-022 WCAG 2.1 AA + DEC-LOGIN-09):
 *   - `<Form {...form}>` wraps with FormProvider (shadcn form.tsx).
 *   - `<FormLabel htmlFor>` + `<FormControl id>` associated via
 *     `useFormField()` â€” screen readers announce field label on focus.
 *   - `aria-invalid={!!error}` propagates from Zod resolver.
 *   - `<FormMessage role="alert">` renders validation errors with
 *     `text-destructive` and live-region announcement.
 *   - Server errors (401/429/network) render in `<p role="alert">`
 *     above the submit button with `aria-live="assertive"` because
 *     these are not announced by `FormMessage`.
 *
 * Lockout countdown:
 *   - When `lockoutFormatted` is non-null the submit button is
 *     disabled (and the input fields via the parent `<fieldset
 *     disabled>`).
 *   - The `<LockoutBlock />` component renders the visible countdown;
 *     this form just hides the submit button while it's locked.
 *
 * Anti-enumeration (DEC-LOGIN-08):
 *   - The form shows the SAME `t('auth.invalidCredentials')` message for
 *     401 regardless of which field was wrong.
 *   - The form NEVER says "email not found" or "wrong password".
 */
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';

import type { LoginInput } from '../api/loginSchema';
import { LockoutBlock } from './LockoutBlock';

export type LoginErrorState =
  | null
  | { kind: 'invalid_credentials' }
  | { kind: 'network' }
  | { kind: 'server'; status: number };

export interface LoginFormProps {
  form: UseFormReturn<LoginInput>;
  onSubmit: (values: LoginInput) => void;
  isSubmitting: boolean;
  isLocked: boolean;
  lockoutFormatted: string | null;
  errorState: LoginErrorState;
  /**
   * F11.4 attempt counter â€” number of failed attempts in this session
   * (client-side; backend is authoritative). Visible only when > 0.
   */
  attemptCount: number;
  maxAttempts: number;
}

export function LoginForm({
  form,
  onSubmit,
  isSubmitting,
  isLocked,
  lockoutFormatted,
  errorState,
  attemptCount,
  maxAttempts,
}: LoginFormProps): JSX.Element {
  const { t } = useTranslation();
  const errorMessage =
    errorState === null
      ? null
      : errorState.kind === 'invalid_credentials'
        ? t('auth.invalidCredentials')
        : errorState.kind === 'network'
          ? t('auth.networkError')
          : t('auth.serverError', { status: errorState.status });

  return (
    <main
      className="flex min-h-screen items-center justify-center bg-background p-4"
      data-testid="page-login"
    >
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t('app.title')}</CardTitle>
          <CardDescription>{t('app.tagline')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onSubmit)}
              className="space-y-4"
              noValidate
              aria-describedby={errorMessage ? 'login-error' : undefined}
            >
              {lockoutFormatted !== null && (
                <LockoutBlock formattedRemaining={lockoutFormatted} />
              )}

              {errorMessage !== null && (
                <p
                  id="login-error"
                  role="alert"
                  aria-live="assertive"
                  data-testid="login-error"
                  className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
                >
                  {errorMessage}
                </p>
              )}

              <fieldset disabled={isLocked || isSubmitting} className="space-y-4">
                <FormField
                  control={form.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="email">{t('auth.email')}</FormLabel>
                      <FormControl>
                        <Input
                          id="email"
                          type="email"
                          autoComplete="username"
                          inputMode="email"
                          data-testid="login-email"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="password">{t('auth.password')}</FormLabel>
                      <FormControl>
                        <Input
                          id="password"
                          type="password"
                          autoComplete="current-password"
                          data-testid="login-password"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <Button
                  type="submit"
                  className="w-full"
                  disabled={isLocked || isSubmitting}
                  data-testid="login-submit"
                >
                  {isSubmitting ? t('auth.submitting') : t('auth.submit')}
                </Button>
              </fieldset>

              {attemptCount > 0 && (
                <p
                  role="status"
                  aria-live="polite"
                  data-testid="login-attempt-counter"
                  className="text-xs text-muted-foreground"
                >
                  {t('auth.attemptCounter', { current: attemptCount, max: maxAttempts })}
                </p>
              )}
            </form>
          </Form>
        </CardContent>
      </Card>
    </main>
  );
}
