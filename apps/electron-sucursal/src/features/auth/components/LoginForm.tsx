/**
 * `<LoginForm />` — presentational puro (F3.1 — DEC-F3.1-02 Container/Presentational split).
 *
 * Recibe props `{ form, onSubmit, isSubmitting, error, onLockoutExpired? }` —
 * sin acceso directo a `useAuth` ni `postLogin`. La integración con el backend
 * vive en `<Login />`.
 *
 * Accesibilidad (RNF-022 WCAG 2.1 AA — DEC-F3.1-01 → REQ-OPS-112):
 *   - `<Form {...form}>` envuelve con FormProvider de shadcn (form.tsx:33).
 *   - `FormLabel htmlFor` + `FormControl id` se asocian via `useFormField()`.
 *   - `aria-invalid={!!error}` se propaga automáticamente cuando hay error Zod.
 *   - `FormMessage` (form.tsx:160-181) renderiza error con `text-destructive`.
 *   - Errores 401/429/network se renderizan en `<p role="alert">` para live region.
 *
 * DEC-F3.2-02 + DEC-F3.2-05 + DEC-F3.2-06 (F3.2 — countdown visible):
 *   - Lockout error → form `disabled` mientras countdown > 0.
 *   - Countdown display `<p role="status" aria-live="polite">` anuncia el
 *     tiempo restante sin interrumpir (NO `aria-live="assertive"`).
 *   - `aria-label` describe contexto completo para screen readers.
 *   - Auto re-enable vía `onLockoutExpired` callback cuando countdown llega a 0.
 *
 * DEC-F3.1-08 anti-enumeración: el mensaje de credenciales inválidas es único.
 */
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Card,
  CardContent,
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

import type { LoginInput } from '../api/loginSchema';
import { useCountdown } from '../hooks/useCountdown';

/**
 * Estado de error que `<Login />` pasa a `<LoginForm />` para renderizar mensajes.
 *  - invalid_credentials → <p role="alert">{t('invalidCredentials')}</p>
 *  - lockout            → countdown <p role="status"> + form disabled
 *  - network            → <p role="alert">{t('errors:serverError')}</p>
 */
export type LoginErrorState =
  | { kind: 'invalid_credentials' }
  | { kind: 'lockout'; retryAfterSeconds: number }
  | { kind: 'network' }
  | null;

export interface LoginFormProps {
  form: UseFormReturn<LoginInput>;
  onSubmit: () => void;
  isSubmitting: boolean;
  error: LoginErrorState;
  /** Callback opcional invocado cuando countdown llega a 0 (F3.2). */
  onLockoutExpired?: () => void;
}

/** Convierte segundos a formato mm:ss. Helper inline, no librería externa. */
function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function LoginForm({
  form,
  onSubmit,
  isSubmitting,
  error,
  onLockoutExpired,
}: LoginFormProps): JSX.Element {
  const { t } = useTranslation('auth');
  const isLockout = error?.kind === 'lockout';
  const { secondsLeft, isExpired } = useCountdown(
    isLockout ? error.retryAfterSeconds : 0,
    { onComplete: onLockoutExpired },
  );

  const isFormDisabled = isSubmitting || (isLockout && !isExpired);

  return (
    <Form {...form}>
      <form
        onSubmit={onSubmit}
        noValidate
        aria-labelledby="login-title"
        data-testid="login-form"
        className="space-y-4"
      >
        <Card>
          <CardHeader>
            <CardTitle id="login-title" asChild>
              <h1>{t('loginTitle')}</h1>
            </CardTitle>
          </CardHeader>
          <CardContent>

        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('email')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="email"
                  autoComplete="username"
                  inputMode="email"
                  data-testid="login-email"
                  disabled={isFormDisabled}
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
              <FormLabel>{t('password')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="password"
                  autoComplete="current-password"
                  data-testid="login-password"
                  disabled={isFormDisabled}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {isLockout && !isExpired && (
          <div data-testid="login-lockout-block">
            <p role="alert" data-testid="login-error-lockout">
              {t('lockout')}
            </p>
            <p
              role="status"
              aria-live="polite"
              aria-label={t('lockoutLabel', { time: formatTime(secondsLeft) })}
              data-testid="login-countdown"
            >
              {t('lockoutCountdown', { time: formatTime(secondsLeft) })}
            </p>
          </div>
        )}

        <Button
          type="submit"
          disabled={isFormDisabled}
          aria-disabled={isFormDisabled}
          data-testid="login-submit"
          className="w-full mt-4"
        >
          {isSubmitting ? t('common:loading') : t('submit')}
        </Button>

        {/* Otros errores (no-lockout) */}
        {error?.kind === 'invalid_credentials' && (
          <p role="alert" data-testid="login-error-invalid">
            {t('invalidCredentials')}
          </p>
        )}
        {error?.kind === 'network' && (
          <p role="alert" data-testid="login-error-network">
            {t('errors:serverError')}
          </p>
        )}
          </CardContent>
        </Card>
      </form>
    </Form>
  );
}
