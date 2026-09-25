/**
 * `<LoginForm />` — presentational puro (F3.1 — DEC-F3.1-02 Container/Presentational split).
 *
 * Recibe props `{ form, onSubmit, isSubmitting, error, onLockoutExpired?,
 * attemptCount?, maxAttempts? }` — sin acceso directo a `useAuth` ni
 * `postLogin`. La integración con el backend vive en `<Login />`.
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
 * F11.4 attempt counter (UX feedback — operador sabe cuántos intentos
 * le quedan antes del bloqueo automático del BE):
 *   - `attemptCount` (default 0) — contador cliente-side que el
 *     `<Login />` container incrementa en cada 401.
 *   - `maxAttempts` (default 5) — coincide con BE `DEFAULT_MAX_INTENTOS`
 *     (auth.py:80); el override por sucursal vive en
 *     `configuracion_seguridad.max_intentos_login` y se consulta vía
 *     `GET /configuracion-seguridad/efectiva` (no implementado en
 *     este PR; el override por sucursal queda como follow-up).
 *   - El badge `<p data-testid="login-attempt-counter">` aparece debajo
 *     del input password solo cuando `attemptCount > 0` (estado cero
 *     es invisible — no contamina la UI limpia).
 *   - `aria-live="polite"` + `role="status"` anuncian cambios sin
 *     interrumpir (WCAG RNF-022).
 *
 * DEC-F3.1-08 anti-enumeración: el mensaje de credenciales inválidas
 * es único ("Correo o contraseña incorrectos") — NUNCA revela si
 * el email existe o si la contraseña es el problema específico. El
 * contador de intentos tampoco revela información: el BE bloquea
 * después de N intentos y este contador refleja el estado cliente-side.
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

/**
 * Estado de error que `<Login />` pasa a `<LoginForm />` para renderizar mensajes.
 *  - invalid_credentials → <p role="alert">{t('invalidCredentials')}</p>
 *  - lockout            → handled OUTSIDE this component — `<Login />`
 *                        renders `<LockoutBlock>` POR FUERA del card con
 *                        `text-muted-foreground` + centrado. El form aquí
 *                        queda disabled mientras isLockout (see isFormDisabled).
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
  /**
   * Contador de intentos fallidos (F11.4 UX feedback). El `<Login />`
   * container lo incrementa en cada `InvalidCredentialsError` y lo
   * resetea a 0 en login exitoso o al recibir `AccountLockedError`
   * (el BE bloqueó → el contador cliente-side deja de importar).
   */
  attemptCount?: number;
  /**
   * Máximo de intentos antes del bloqueo automático del BE
   * (default 5 — coincide con `DEFAULT_MAX_INTENTOS` en
   * backend/.../auth.py:80). Solo se usa para renderizar el
   * texto "Intento N de M"; el BE decide el lockout real.
   */
  maxAttempts?: number;
}

/**
 * Convierte segundos a formato mm:ss. Helper inline, no librería externa.
 * Sigue siendo necesario porque el Login.tsx renderiza un
 * `<LockoutBlock>` (componente separado en
 * `components/LockoutBlock.tsx`) que también usa este helper.
 * Como `LockoutBlock` lo define localmente, podemos quitarlo de acá;
 * pero el test suite importa `formatTime` indirectamente vía
 * `data-testid="login-countdown"` matches — lo dejamos para evitar
 * churn en los tests. Si quieres eliminarlo, borra esta función
 * y los tests que dependen del atributo `aria-label` deberían
 * matchear contra `<LockoutBlock>` directamente.
 */
// (Eliminado del archivo actual -- el countdown vive en LockoutBlock.)

export function LoginForm({
  form,
  onSubmit,
  isSubmitting,
  error,
  onLockoutExpired,
  attemptCount = 0,
  maxAttempts = 5,
}: LoginFormProps): JSX.Element {
  const { t } = useTranslation('auth');
  const isLockout = error?.kind === 'lockout';
  // F11.4 follow-up -- el countdown del lockout vive en
  // `<LockoutBlock>` (renderizado por el parent `<Login />` POR FUERA
  // del card, con `text-muted-foreground`). El form queda disabled
  // mientras `isLockout` para que el operador no pueda intentar hasta
  // que el countdown expire (el parent resetea `errorState` via
  // `handleLockoutExpired` cuando `useCountdown` llega a 0).
  // `onLockoutExpired` se mantiene en `LoginFormProps` por compat con
  // `<Login />` (que lo sigue pasando), pero YA NO se invoca desde acá:
  // el wiring real vive en `<LockoutBlock onExpired={handleLockoutExpired}>`
  // (ver Login.tsx). Se referencia explícitamente para satisfacer
  // `noUnusedParameters` sin remover el prop del contrato público.
  void onLockoutExpired;

  const isFormDisabled = isSubmitting || isLockout;
  const showAttemptCounter = attemptCount > 0;

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
              {/* F11.4 — contador de intentos visible SOLO cuando el
                  operador ya falló al menos 1 vez. Estado cero = invisible
                  (no contamina la UI limpia del primer intento). */}
              {showAttemptCounter && (
                <p
                  role="status"
                  aria-live="polite"
                  data-testid="login-attempt-counter"
                  data-attempt-current={attemptCount}
                  data-attempt-max={maxAttempts}
                  className="text-xs text-muted-foreground mt-1"
                >
                  {t('attemptCounter', {
                    current: attemptCount,
                    max: maxAttempts,
                  })}
                </p>
              )}
            </FormItem>
          )}
        />

        {/* F11.4 — el countdown del lockout se renderiza POR FUERA
            del card (ver <LockoutBlock> en <Login />, líneas ~160).
            Aquí solo renderizamos los errores NO-lockout + el counter. */}

        {/* F11.4 — mensaje de "contraseña errónea" + counter badge.
            El counter se muestra ARRIBA del mensaje para que el operador
            vea primero cuántos intentos lleva antes de leer el texto
            explicativo. role="alert" announces inmediatamente (WCAG
            RNF-022 — errores críticos usan assertive/polite según
            severidad; para credenciales inválidas polite es suficiente). */}
        {error?.kind === 'invalid_credentials' && (
          <div data-testid="login-error-invalid-block">
            <p
              role="alert"
              aria-live="polite"
              data-testid="login-error-invalid"
              className="text-sm text-destructive"
            >
              {t('invalidCredentials')}
            </p>
          </div>
        )}
        {error?.kind === 'network' && (
          <p role="alert" data-testid="login-error-network">
            {t('errors:serverError')}
          </p>
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
          </CardContent>
        </Card>
      </form>
    </Form>
  );
}
