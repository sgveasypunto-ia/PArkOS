/**
 * `<Login />` — Container component for `web_admin` admin login
 * (IT-1.10 of `openspec/_meta/iteration-plan.md`).
 *
 * Owns: form state (RHF + Zod), submit lifecycle (postLogin), token
 * persistence (useAuthStore.setTokens), error mapping (401/429),
 * redirect on success (DEC-LOGIN-07).
 *
 * Doesn't own: layout, chrome, logo, a11y labels — those live in
 * the presentational `<LoginForm />` (DEC-F3.1-02 mirror).
 *
 * DEC-LOGIN-07 redirect:
 *   On successful login we redirect to `?next=<path>` if present,
 *   else `/` (the hub). The `next` query parameter lets a deep link
 *   like `/audit` survive the login bounce without a custom
 *   "you need to log in" screen.
 *
 *   Identity comes from `useAdminAuth`, not `useAuth`: `/auth/me` is
 *   hardcoded to the `operador-` issuer and 404s for `admin-` tokens,
 *   so `useAuth().user` is permanently null here and the
 *   already-authenticated redirect below would never fire.
 *
 * DEC-LOGIN-08 anti-enumeration:
 *   401 → `InvalidCredentialsError` → form shows the SINGLE
 *   `t('invalidCredentials')` string. The form never tells the user
 *   whether the email or the password was wrong.
 *
 * DEC-F3.2-02 + DEC-F3.2-06 (lockout countdown):
 *   429 → `AccountLockedError` with `retryAfterSeconds` → set
 *   `accountLockedUntil = now + retryAfterSeconds`, mount the
 *   countdown via `useCountdown`, disable the form. When the
 *   countdown hits zero (`onLockoutExpired`), clear the lockout
 *   state and re-enable the form.
 *
 * DEC-FETCH-03 + DEC-FETCH-06:
 *   `parkosFetch` would attach `Authorization: Bearer <jwt>` from
 *   the authStore pre-login. We use raw `fetch` (postLogin) instead
 *   — same decision as electron-sucursal's `loginApi.ts`.
 *
 * F11.4 attempt counter:
 *   `attemptCount` increments on every 401 (client-side feedback).
 *   Resets to 0 on success. The backend is authoritative for the
 *   actual lockout (429); the client-side counter is just a visual
 *   hint.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { useAuthStore } from '@parkos/ui-kit/store';

import { LockoutBlock } from '../components/LockoutBlock';
import { LoginForm, type LoginErrorState } from '../components/LoginForm';
import { useCountdown, formatCountdown } from '../hooks/useCountdown';
import { loginSchema, type LoginInput } from '../api/loginSchema';
import {
  AccountLockedError,
  InvalidCredentialsError,
  postLogin,
} from '../api/loginApi';

/** Mirrors `DEFAULT_MAX_INTENTOS` in `backend/.../auth.py`. */
const MAX_ATTEMPTS = 5;

function getNextPath(search: string): string {
  const params = new URLSearchParams(search);
  const next = params.get('next');
  if (next && next.startsWith('/') && !next.startsWith('//')) return next;
  // Post-login lands on the picker. Decision: even with a valid
  // persisted selection, we force a re-confirmation — sharing the
  // browser or operator handoff is more common than an in-tab reload.
  return '/seleccionar-sucursal';
}

export function Login(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const nextPath = useMemo(() => getNextPath(location.search), [location.search]);
  const { isAuthenticated, isLoading, user } = useAdminAuth();
  const setTokens = useAuthStore((s) => s.setTokens);

  const [errorState, setErrorState] = useState<LoginErrorState>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [attemptCount, setAttemptCount] = useState(0);
  const [accountLockedUntil, setAccountLockedUntil] = useState<Date | null>(null);

  const secondsRemaining = useCountdown(accountLockedUntil, {
    onComplete: useCallback(() => {
      setAccountLockedUntil(null);
      setErrorState(null);
    }, []),
  });
  const lockoutFormatted = accountLockedUntil !== null ? formatCountdown(secondsRemaining) : null;
  const isLocked = lockoutFormatted !== null && secondsRemaining > 0;

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    mode: 'onBlur',
    defaultValues: { email: '', password: '' },
  });

  // DEC-LOGIN-07: if the user is already authenticated, redirect to `next`.
  // We wait for `isLoading === false` so the SWR `useAuth` has had a chance
  // to hydrate (avoids the brief flash where the form renders before the
  // authStore rehydrates and the redirect fires).
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate(nextPath, { replace: true });
    }
  }, [isAuthenticated, isLoading, navigate, nextPath]);

  const onSubmit = async (values: LoginInput): Promise<void> => {
    setIsSubmitting(true);
    setErrorState(null);
    try {
      const pair = await postLogin(values.email, values.password);
      setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
      setAttemptCount(0);
      // SWR will pick up the new accessToken on its next tick and revalidate
      // /auth/me; the useEffect above catches the isAuthenticated transition.
    } catch (err) {
      if (err instanceof InvalidCredentialsError) {
        setErrorState({ kind: 'invalid_credentials' });
        setAttemptCount((c) => c + 1);
      } else if (err instanceof AccountLockedError) {
        const until = new Date(Date.now() + err.retryAfterSeconds * 1000);
        setAccountLockedUntil(until);
        // Surface the lockout via the LockoutBlock rather than the inline
        // error; the inline error remains null until the lockout expires.
      } else if (err instanceof ParkosHttpError) {
        setErrorState({ kind: 'server', status: err.status });
      } else {
        setErrorState({ kind: 'network' });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isAuthenticated && !isLoading && user !== null) {
    return <Navigate to={nextPath} replace />;
  }

  return (
    <LoginForm
      form={form}
      onSubmit={onSubmit}
      isSubmitting={isSubmitting}
      isLocked={isLocked}
      lockoutFormatted={lockoutFormatted}
      errorState={errorState}
      attemptCount={attemptCount}
      maxAttempts={MAX_ATTEMPTS}
    />
  );
}

// Used by the LockoutBlock prop above; re-exported for test isolation.
export { LockoutBlock };
