/**
 * `<LoginForm />` — presentational puro (F3.1 — DEC-F3.1-02 Container/Presentational split).
 *
 * Recibe props `{ form, onSubmit, isSubmitting, error }` — sin acceso directo a
 * `useAuth` ni `postLogin`. La integración con el backend vive en `<Login />`.
 *
 * Accesibilidad (RNF-022 WCAG 2.1 AA — DEC-F3.1-01 → REQ-OPS-112):
 *   - `<Form {...form}>` envuelve con FormProvider de shadcn (form.tsx:33).
 *   - `FormLabel htmlFor` + `FormControl id` se asocian via `useFormField()`
 *     (shadcn form.tsx:67-141).
 *   - `aria-invalid={!!error}` se propaga automáticamente cuando hay error Zod.
 *   - `FormMessage` (form.tsx:160-181) renderiza error con `text-destructive`
 *     + role implícito por destructivo styling.
 *   - Errores 401/429/network se renderizan en `<p role="alert">` para live
 *     region announcement por screen readers.
 *
 * DEC-F3.1-08 anti-enumeración: el mensaje de credenciales inválidas es único
 * (`t('invalidCredentials')`), sin distinción email vs password.
 */
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button } from '@/renderer/components/ui/button';
import { Input } from '@/renderer/components/ui/input';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/renderer/components/ui/form';

import type { LoginInput } from '../api/loginSchema';

/**
 * Estado de error que `<Login />` pasa a `<LoginForm />` para renderizar mensajes.
 *  - invalid_credentials → <p role="alert">{t('invalidCredentials')}</p>
 *  - lockout            → <p role="alert">{t('lockout')}</p>
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
}

export function LoginForm({ form, onSubmit, isSubmitting, error }: LoginFormProps): JSX.Element {
  const { t } = useTranslation('auth');

  return (
    <Form {...form}>
      <form
        onSubmit={onSubmit}
        noValidate
        aria-labelledby="login-title"
        data-testid="login-form"
      >
        <h1 id="login-title">{t('loginTitle')}</h1>

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
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <Button
          type="submit"
          disabled={isSubmitting}
          data-testid="login-submit"
        >
          {isSubmitting ? t('common:loading') : t('submit')}
        </Button>

        {error?.kind === 'invalid_credentials' && (
          <p role="alert" data-testid="login-error-invalid">
            {t('invalidCredentials')}
          </p>
        )}
        {error?.kind === 'lockout' && (
          <p role="alert" data-testid="login-error-lockout">
            {t('lockout')}
          </p>
        )}
        {error?.kind === 'network' && (
          <p role="alert" data-testid="login-error-network">
            {t('errors:serverError')}
          </p>
        )}
      </form>
    </Form>
  );
}