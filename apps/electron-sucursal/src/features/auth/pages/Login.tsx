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
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '@parkos/ui-kit/hooks';

import { LoginForm, type LoginErrorState } from '../components/LoginForm';
import { loginSchema, type LoginInput } from '../api/loginSchema';

export function Login(): JSX.Element {
  const navigate = useNavigate();
  const { isAuthenticated, isLoading, user } = useAuth();
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

  // T1 placeholder onSubmit: limpia errorState. T2 wirea postLogin + setTokens
  // + error mapping 401/429/5xx via `InvalidCredentialsError` / `AccountLockedError`.
  const onSubmit = form.handleSubmit(() => {
    setErrorState(null);
  });

  return (
    <LoginForm
      form={form}
      onSubmit={onSubmit}
      isSubmitting={form.formState.isSubmitting}
      error={errorState}
    />
  );
}