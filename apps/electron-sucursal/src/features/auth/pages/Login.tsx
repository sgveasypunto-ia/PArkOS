/**
 * `<Login />` — container (F3.1 — DEC-F3.1-02 Container/Presentational split).
 *
 * T1 base: RHF + Zod resolver + useTranslation + useNavigate + placeholder
 *          onSubmit (limpia errorState, NO llama fetch todavía — T2 wirea
 *          postLogin + setTokens + error mapping 401/429/5xx).
 *
 * F3.1 NO modifica main process ni preload (DEC-F3.1-04 login via HTTP
 * directo en renderer, NO IPC). Cookie httpOnly round-trip blindado por
 * `credentials:'include'` en loginApi.postLogin (DEC-F3.1-03).
 *
 * DEC-F3.1-06: Zod local en form — mensajes son KEYS i18n (validación UX inline).
 * DEC-F3.1-07: useEffect redirect espera `user` resuelto post-`/auth/me`
 *               (hidratación transaccional, sin flash).
 * DEC-F3.1-08: anti-enumeración — 401 colapsa a `t('invalidCredentials')` único.
 */
import { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@parkos/ui-kit/hooks';
import { useAuthStore } from '@parkos/ui-kit/store';

import { LoginForm, type LoginErrorState } from '../components/LoginForm';
import { loginSchema, type LoginInput } from '../api/loginSchema';
import {
  postLogin,
  AccountLockedError,
  InvalidCredentialsError,
} from '../api/loginApi';

export function Login(): JSX.Element {
  const navigate = useNavigate();
  // F3.3 — DEC-F3.3-09 + REQ-OPS-124: detecta ?closed=true para feedback
  // post-cierre de turno (operador kiosko redirigido tras cerrar turno).
  const location = useLocation();
  const showClosedNotice = location.search.includes('closed=true');
  const { isAuthenticated, isLoading, user } = useAuth();
  const setTokens = useAuthStore((s) => s.setTokens);
  const { t } = useTranslation(['auth', 'caja']);
  const [errorState, setErrorState] = useState<LoginErrorState>(null);

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    mode: 'onBlur',
    defaultValues: { email: '', password: '' },
  });

  // DEC-F3.1-07: redirect transaccional post-hidratación useAuth() (T3 wirea).
  // Espera `user` resuelto (no solo `isAuthenticated`) para evitar flash de
  // "sesión no iniciada" en el destino.
  useEffect(() => {
    if (isAuthenticated && user && !isLoading) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, user, isLoading, navigate]);

  // DEC-F3.2-02 (F3.2): reset errorState cuando countdown de lockout llega a 0.
  // El `<LoginForm>` invoca `useCountdown({retryAfterSeconds, onComplete})` y
  // cuando llega a 0 llama este callback → atomic setErrorState(null) →
  // re-render con form re-habilitado.
  const handleLockoutExpired = useCallback(() => {
    setErrorState(null);
  }, []);

  const onSubmit = form.handleSubmit(async (values) => {
    setErrorState(null);
    try {
      const pair = await postLogin(values.email, values.password);
      // DEC-F3.1-03 + authStore invariant: setTokens es atómico (access +
      // refresh + expiresAt simultáneamente). El redirect lo dispara el
      // useEffect cuando SWR resuelve `user` post-/auth/me.
      setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
    } catch (err) {
      if (err instanceof InvalidCredentialsError) {
        setErrorState({ kind: 'invalid_credentials' });
      } else if (err instanceof AccountLockedError) {
        setErrorState({ kind: 'lockout', retryAfterSeconds: err.retryAfterSeconds });
      } else {
        setErrorState({ kind: 'network' });
      }
    }
  });

  return (
    <>
      {/* F3.3 — REQ-OPS-124: feedback post-cierre turno (DEC-F3.3-09).
          role=status + aria-live=polite WCAG 2.1 AA compliant (mismo
          pattern F3.2 REQ-OPS-118 countdown). NO interrumpe screen reader.
          Renderizado FUERA del wrapper de centrado — queda como banner
          top-of-page antes del card, no afecta la estética del login. */}
      {showClosedNotice && (
        <p
          role="status"
          aria-live="polite"
          data-testid="turno-cerrado-exito"
        >
          {t('caja:turnoCerradoExito')}
        </p>
      )}

      {/* F3.1 (DEC-F3.1-02): el layout del /login vive acá (container) y
          NO en <LoginForm>. Las clases quedan SCOPED a este wrapper --
          cualquier cambio acá no se filtra a /caja/abrir-turno, /dashboard
          ni a ninguna otra ruta protegida. Features:
            - `grid place-items-center` centra vertical y horizontalmente
              sin posicionar absoluto (responsive + sin media queries).
            - `min-h-[calc(100vh-2rem)]` iguala la altura del <main> de
              App.tsx (descontando el StatusBar de ~2rem arriba).
            - `max-w-md` (28rem) impide que la tarjeta se estire en
              pantallas anchas (kioskos pueden ser 1024px+).
            - `py-8` da espacio vertical respirable; el padding horizontal
              del <main> padre (px-4) sigue sumando para pantallas chicas. */}
      <div
        className="grid min-h-[calc(100vh-2rem)] w-full place-items-center px-4 py-8"
        data-testid="login-page-wrapper"
      >
        <div className="w-full max-w-md">
          <LoginForm
            form={form}
            onSubmit={onSubmit}
            isSubmitting={form.formState.isSubmitting}
            error={errorState}
            onLockoutExpired={handleLockoutExpired}
          />
        </div>
      </div>
    </>
  );
}