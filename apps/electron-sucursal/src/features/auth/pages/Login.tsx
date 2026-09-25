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
 *
 * F11.4 attempt counter (UX feedback):
 *   - `attemptCount` se incrementa en cada `InvalidCredentialsError` (401).
 *   - Se resetea a 0 en login exitoso (path feliz).
 *   - Se IGNORA en `AccountLockedError` (429) porque el BE ya bloqueó la
 *     cuenta — el contador cliente-side deja de importar (el countdown
 *     del lockout toma el control visual).
 *   - El contador es CLIENTE-SIDE — el BE tiene su propio contador
 *     autoritativo (prod.login estado='fallido' en los últimos N min);
 *     si el operador abre 2 pestañas y falla en una, el contador
 *     cliente-side de la otra pestaña queda desincronizado con el BE.
 *     El BE es quien decide el lockout real; el contador FE es solo
 *     feedback visual.
 *   - `MAX_ATTEMPTS = 5` coincide con `DEFAULT_MAX_INTENTOS` en
 *     backend/.../auth.py:80. El override por sucursal via
 *     `configuracion_seguridad.max_intentos_login` queda como follow-up.
 */
import { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@parkos/ui-kit/hooks';
import { useAuthStore } from '@parkos/ui-kit/store';

import { LoginForm, type LoginErrorState } from '../components/LoginForm';
import { LockoutBlock } from '../components/LockoutBlock';
import { loginSchema, type LoginInput } from '../api/loginSchema';
import {
  postLogin,
  AccountLockedError,
  InvalidCredentialsError,
} from '../api/loginApi';

/** Coincide con `DEFAULT_MAX_INTENTOS` en backend/.../auth.py:80. */
const MAX_ATTEMPTS = 5;

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
  // F11.4 — contador de intentos cliente-side. Se resetea a 0 cuando
  // el operador logra entrar (setTokens) o cuando el BE bloqueó la
  // cuenta (AccountLockedError — el countdown del lockout es el feedback
  // visual prioritario; el contador deja de importar).
  const [attemptCount, setAttemptCount] = useState(0);

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
    // F11.4 follow-up -- el operador reportó que si falla un submit
    // mientras YA está bloqueado, el countdown se reinicia desde
    // cero en cada click (porque `setErrorState(null)` al inicio del
    // submit desmonta el `<LockoutBlock />` que ya está corriendo).
    //
    // Fix: usar el setter funcional para preservar el lockout state.
    // Si `prev.kind === 'lockout'`, mantenerlo (el countdown sigue
    // corriendo en el `<LockoutBlock />`). Si no hay lockout previo,
    // limpiar cualquier error transient (invalid_credentials o network)
    // para que el próximo error mapping se renderice limpio.
    setErrorState((prev) => {
      if (prev?.kind === 'lockout') return prev;
      return null;
    });
    try {
      const pair = await postLogin(values.email, values.password);
      // DEC-F3.1-03 + authStore invariant: setTokens es atómico (access +
      // refresh + expiresAt simultáneamente). El redirect lo dispara el
      // useEffect cuando SWR resuelve `user` post-/auth/me. Reset del
      // attempt counter (F11.4) — el operador logró entrar.
      setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
      setAttemptCount(0);
    } catch (err) {
      if (err instanceof InvalidCredentialsError) {
        // Mismo setter funcional -- preserva el lockout previo si lo
        // hubiera (improbable: un 401 solo ocurre ANTES del lockout,
        // pero defensivo).
        setErrorState((prev) => {
          if (prev?.kind === 'lockout') return prev;
          return { kind: 'invalid_credentials' };
        });
        // F11.4 — increment cliente-side. El BE tiene su propio contador
        // autoritativo (prod.login estado='fallido'); este contador es
        // SOLO feedback visual (UX — el operador sabe cuántos intentos
        // lleva antes del bloqueo automático).
        setAttemptCount((n) => n + 1);
      } else if (err instanceof AccountLockedError) {
        // F11.4 follow-up -- si ya hay un lockout activo, IGNORAR el
        // nuevo 429: el countdown del cliente ya está corriendo y el
        // operador NO debe perder el progreso al hacer click submit
        // múltiples veces durante el lockout. Si NO hay lockout
        // previo (caso normal: el operador hace 5× 401 y luego el
        // 429), montar el countdown por primera vez.
        setErrorState((prev) => {
          if (prev?.kind === 'lockout') return prev;
          return { kind: 'lockout', retryAfterSeconds: err.retryAfterSeconds };
        });
      } else {
        setErrorState((prev) => {
          if (prev?.kind === 'lockout') return prev;
          return { kind: 'network' };
        });
      }
    }
  });

  // F11.4 — el lockout block se renderiza POR FUERA del card (mismo patrón
  // que `turno-cerrado-exito` arriba) con `text-muted-foreground` + centrado.
  // El operador reportó que el texto "Cuenta bloqueada temporalmente."
  // estaba dentro del card con `text-destructive` (demasiado protagonista);
  // ahora vive como texto de apoyo al lado del card, no compite con el title.
  const lockoutKind =
    errorState?.kind === 'lockout' ? errorState : null;

  return (
    <>
      {/* F3.3 — REQ-OPS-124: feedback post-cierre turno (DEC-F3.3-09).
          role=status + aria-live=polite WCAG 2.1 AA compliant (mismo
          pattern F3.2 REQ-OPS-118 countdown). NO interrumpe screen reader.
          Renderizado FUERA del wrapper de centrado — queda como banner
          top-of-page antes del card, no afecta la estética del login.
          F31.3 rediseño: el banner no tenía NINGUNA clase (texto plano
          pegado al borde del viewport) — se agrega un chip "success"
          (token --success/--success-foreground, mismo chip suave usado
          en el resto de la app) centrado con padding responsive. */}
      {showClosedNotice && (
        <p
          role="status"
          aria-live="polite"
          data-testid="turno-cerrado-exito"
          className="mx-auto mt-4 w-fit max-w-[calc(100%-2rem)] rounded-full bg-success px-4 py-1.5 text-center text-sm font-medium text-success-foreground"
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
            attemptCount={attemptCount}
            maxAttempts={MAX_ATTEMPTS}
          />
        </div>

        {/* F11.4 — F3.2 countdown live, POR FUERA del card (DEBAJO del
            mismo, no arriba — el operador reportó que arriba se ve raro
            y poco usable, abajo es el patrón estándar para "support text
            después del action surface"). En gris menos protagonista
            (text-muted-foreground) + centrado. Mismo estilo que el
            `turno-cerrado-exito` banner y el help text del welcome card.
            El form arriba permanece disabled durante el lockout porque
            `error.kind === 'lockout'` → `isFormDisabled = true`. */}
        {lockoutKind && (
          <LockoutBlock
            retryAfterSeconds={lockoutKind.retryAfterSeconds}
            onExpired={handleLockoutExpired}
          />
        )}
      </div>
    </>
  );
}