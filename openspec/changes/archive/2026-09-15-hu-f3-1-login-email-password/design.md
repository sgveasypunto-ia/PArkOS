# Diseño técnico — HU-F3.1 Login con `email` + `password`

> **Change**: `hu-f3-1-login-email-password` · **Folder**: `openspec/changes/hu-f3-1-login-email-password/`
> **Phase**: design (sdd-design) · **Status**: ready for `sdd-tasks`
> **HU ID**: HU-F3.1 (Fase 3 — primera HU; Autenticación y turno de caja, transversal a todas las CU operativas)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `ba9d81a`, Fase 2 cerrada 2026-09-15 con F2.1 + F2.2 + F2.3 archivados)
> **Inputs**: `proposal.md` (18 secciones, 11 DEC-F3.1-NN ratified, 7 new REQ-OPS-106..112 user-facing, 6 acceptance gates G1..G6, 8 riesgos R1..R8, 1 cluster C1, 4 atomic tasks T1..T4, ~430 LOC), `exploration.md` (17 secciones, 10 DEC-F3.1-01..10 ratified, 8 riesgos, 4 tasks, ~758 LOC), `openspec/changes/archive/2026-09-15-hu-f2-3-electron-auto-update-kiosko/design.md` (15 secciones + 2 apéndices, ~790 LOC — layout canónico clonado 1:1), `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/design.md` (~1100 LOC), `apps/electron-sucursal/{electron/main.ts, preload.ts, bridge.d.ts}` (F2.2+F2.3 shippeados, READ-ONLY anchors), `apps/ui-kit/src/{fetch/parkosFetch.ts, store/authStore.ts, hooks/useAuth.ts}` (F2.2 primitives, READ-ONLY anchors), `apps/electron-sucursal/src/renderer/{App.tsx, components/ui/form.tsx, i18n/locales/auth.json}` (F2.1+F2.2+F2.3 baselines), `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-583` (HU-F1.2 shipped, READ-ONLY consumer anchors), `docs/01-requisitos/no-funcionales.md:126` (RNF-022 WCAG 2.1 AA gate).
> **Language**: español neutro profesional · **Conventional commits**: feat(auth) / feat(router) / test(electron) — sin Co-authored-by.

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F3.1 |
| **Fase** | 3 (Autenticación y turno de caja — primera HU) |
| **Change name** | `hu-f3-1-login-email-password` |
| **Folder** | `openspec/changes/hu-f3-1-login-email-password/` |
| **State** | design ready |
| **Branch** | `feat/fase-2-electron-scaffold` |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | sdd-propose (proposal.md) + sdd-explore (exploration.md) + sdd-spec (DELTA con 7 new REQ-OPS-106..112) |
| **Próximo phase** | sdd-tasks |
| **Language** | español neutro profesional |
| **Conventional commits** | feat(auth) / feat(router) / test(electron) — sin Co-authored-by |
| **LOC target** | ~170 producción + ~240 tests + ~10 configs = **~420 LOC total** |

---

## 1. Visión general y objetivos

### 1.1 Objetivo primario

Definir la arquitectura técnica HOW del primer consumer end-to-end real de las primitivas de Fase 2 (Electron 30 + parkosFetch + authStore + useAuth + bridge IPC). F3.1 entrega la pantalla de login que el operador usa al iniciar su turno: `<FormData` con `email` + `password` validados vía RHF + Zod → POST `/auth/login` con `credentials:'include'` (cookie `parkos_session` httpOnly+secure+SameSite=Lax) → hidratación de `authStore` con `setTokens` → SWR re-fetcha `GET /auth/me` → `<LoginPage>` redirige transaccionalmente a `/` con `user` + `sucursal` + `permisos` resueltos (sin flash de "sesión no iniciada").

Seis bloques arquitectónicos, clonando layout F2.3:

1. **Feature folder `src/features/auth/{pages,components,api}/`** — Atomic Design + Feature Slicing (DEC-F3.1-01). `Login.tsx` (container), `LoginForm.tsx` (presentational), `loginApi.ts` (HTTP layer).
2. **`loginApi.ts` con `fetch` raw + error mapping custom** — `InvalidCredentialsError` (401), `AccountLockedError(retryAfter)` (429), `ParkosHttpError` (5xx/network). `credentials:'include'` explícito. NO `parkosFetch` (DEC-F3.1-05).
3. **`Login.tsx` container con RHF + Zod + onSubmit + setTokens + useAuth + useNavigate + useEffect redirect** — espera `data?.user` antes de `navigate('/')` (DEC-F3.1-07).
4. **`LoginForm.tsx` presentational con shadcn Form/FormField/Input/Button** — props `{form, onSubmit, isSubmitting, error}`. `aria-invalid` en error state, `FormMessage role="alert"`, label htmlFor asociado (RNF-022).
5. **`<Route path="/login">` en `App.tsx`** — ruta dedicada standalone (no requiere guards de auth porque por definición NO hay sesión).
6. **Anti-enumeración cross-layer** — backend colapsa 401 a `errors.invalid_credentials` único (auth.py:159-191); frontend colapsa 401 a `t('invalidCredentials')` único (auth.json:9). NO distinción entre "email no existe" / "password incorrecta" / "cuenta deshabilitada" (DEC-F3.1-08).

Estos seis bloques desbloquean **8+ HUs downstream** (F3.2 lockout visible, F3.3 abrir/cerrar turno, F3.x logout UI + AuthGuard, F4.x catálogos + ocupación, F5.x+ impresión térmica con permisos, F11.x sync UI topbar) que consumirán la sesión hidratada sin renegociar el contrato de auth.

### 1.2 Objetivos secundarios

- **Defense in depth XR6** (cross-ref `operations/spec.md:3951` + F2.2 §15.3 + F2.3 §15.3 precedent): las 5 capas existentes se fortalecen con la capa 4 contract (Zod local en form + backend Pydantic + 7 new REQ-OPS-106..112 spec-level) y la capa 3 a11y (axe-core WCAG 2.1 AA + FormField aria-invalid + FormMessage role="alert"). F3.1 NO crea nuevo REQ-OPS-XR — las decisiones viven como DEC-F3.1-NN + REQ-OPS-106..112 per F1.15 precedent.
- **Hidratación transaccional sin flash**: el operador llega a `/` con `user` + `sucursal` + `permisos` TODOS resueltos. Sin flash de "sesión no iniciada" (DEC-F3.1-07).
- **Cookie httpOnly round-trip blindado**: `HttpOnly` flag impide lectura via JS (mitigación XSS), `SameSite=Lax` bloquea cross-site form submissions (mitigación CSRF). `credentials:'include'` mandatory para que el navegador persista y envíe la cookie (DEC-F3.1-03).
- **Anti-enumeración cross-layer**: backend (auth.py:159-191, 250-251) + frontend (LoginForm.tsx render) ambos colapsan 401 a mensaje único. Atacante no puede inferir email válido midiendo latencia (bcrypt ~250ms enmascara) ni respuestas diferentes.
- **a11y WCAG 2.1 AA** (RNF-022): `axe-core 0 violaciones` en `<LoginForm>`. Cobertura: label `htmlFor`, `aria-invalid` en error state, `aria-describedby` apuntando a `FormMessage`, `role="alert"` en mensajes, tab order secuencial, contraste 4.5:1.
- **Cobertura >80%** en `Login.tsx` + `LoginForm.tsx` + `loginApi.ts` (vitest --coverage threshold per tsconfig).
- **TDD estricto**: cada test escrito ANTES de la implementación; 7 acceptance gates (G1..G6 + G7 implícito axe-core) deben pasar antes de merge.

### 1.3 No-objetivos (cross-ref proposal §15 / exploration §14)

- Backend endpoints nuevos — HU-F1.2 shipped en Fase 1 cubre los 2 endpoints (`POST /auth/login` + `GET /auth/me`).
- Lockout countdown UI — F3.2 lo entrega (useCountdown hook + 429 disable form + countdown visual). F3.1 surfacea el error con `AccountLockedError(retryAfter)` pero NO renderiza countdown.
- Refresh pre-flight antes de POST `/facturacion/*` + POST `/caja/arqueo` — F3.2 (50min auto-refresh check).
- Logout button UI — F3.3+ (placeholder o HU posterior). F3.1 solo verifica `useAuthStore.clear()` en e2e.
- AuthGuard component — F3.3+ (intercepta `parkos:auth:cleared` event → `navigate('/login?next=...')`).
- Recuperación de password / forgotPassword — fuera Fase 3 (futuro).
- 2FA / WebAuthn — fuera Fase 3 (futuro).
- Multi-tab login UI — kiosko single-tab por F2.3 single-instance lock (DEC-UPD-07).
- Turno abrir/cerrar — F3.3 (`features/caja/pages/{AbrirTurno,CerrarTurno}.tsx` + `useSesionActiva`).
- rememberMe checkbox / forgotPassword link — keys en `auth.json` pero F3.1 NO renderiza (kiosko desatendido, no aplica).
- Sucursal selector UI — el JWT ya pinea sucursal (DEC-F3.1-04 single-branch kiosko).
- Refresh-token rotation — F2.2 cubre (DEC-FETCH-03); F3.1 NO toca.
- Zod schema validation en boundary via `parkosFetch<T>(url, schema)` — DEC-FETCH-05 optional; F3.1 NO exige.
- OS-level kiosk — Windows Assigned Access / macOS kiosk mode (FUERA Fase 3).
- PIN rotation UI — kiosko PIN pre-shared por F2.3, no rotation UI.
- Backend cambios — HU-F1.2 shipped; F3.1 NO modifica backend.

---

## 2. Estado actual verificado (AS-IS)

### 2.1 `electron/main.ts` — `apps/electron-sucursal/electron/main.ts:1-122`

F2.1 baseline + F2.3 single-instance + log-config + updater + api-status + kiosko. **F3.1 NO modifica main.ts**: login fluye por HTTP directo en renderer vía `fetch` con `credentials:'include'`, no requiere IPC. El bridge IPC F2.2 ya wireó `bridge.authStore.{get,set,delete}` para persistencia (authStore Zustand) — F3.1 consume indirectamente via `useAuthStore.setTokens` (DEC-F3.1-04 rationale: "IPC para capabilities privileged, HTTP para data plane").

### 2.2 `electron/preload.ts` — `apps/electron-sucursal/electron/preload.ts:1-49`

F2.2 shippeó whitelist de 8 métodos IPC en 6 grupos. **F3.1 NO modifica preload.ts**: el renderer NO necesita nuevos métodos IPC para login — todo el flujo es HTTP estándar con cookie jar gestionada por el navegador.

### 2.3 `electron/bridge.d.ts` — `apps/electron-sucursal/electron/bridge.d.ts:1-92`

F2.2 + F2.3 typed `BridgeSurface` interface con 8 métodos en 6 grupos. **F3.1 NO modifica bridge.d.ts**: NO hay nueva capability IPC; F3.1 consume primitives ya existentes via `window.bridge.authStore` (indirectamente a través de `useAuthStore`).

### 2.4 `App.tsx` — `apps/electron-sucursal/src/renderer/App.tsx:1-37`

```typescript
// F2.1 + F2.3 baseline (F3.1 lo extiende, no reemplaza)
import { useTranslation } from 'react-i18next';
import { Route, Routes } from 'react-router-dom';

import { StatusBar } from './components/StatusBar';

export default function App() {
  const { t } = useTranslation('common');

  return (
    <>
      <StatusBar />
      <main lang="es-CO">
        <h1>{t('appName')}</h1>
        <p>{t('bootstrapNotice')}</p>
        <Routes>
          <Route path="/" element={null} />
          <Route
            path="*"
            element={
              <p role="status">{t('error', { defaultValue: '404' })}</p>
            }
          />
        </Routes>
      </main>
    </>
  );
}
```

**Gap identificado**: NO existe `<Route path="/login">`. F3.1 T3 lo agrega (`<Route path="/login" element={<LoginPage />} />`). StatusBar F2.3 montado arriba del `<main>` se mantiene — el operador ve el API status incluso durante login.

### 2.5 `authStore.ts` — `apps/ui-kit/src/store/authStore.ts:1-129`

F2.2 primitive. **F3.1 NO modifica authStore.ts**, solo consume `useAuthStore.setTokens(access, refresh, expiresIn)` post-`POST /auth/login`. Setter atómico: `{accessToken, refreshToken, expiresAt}` simultáneos. `expiresAt` derivado `Date.now() + expiresIn * 1000` ISO 8601. `partialize` whitelist: solo tokens cruzan IPC a electron-store.

### 2.6 `useAuth.ts` — `apps/ui-kit/src/hooks/useAuth.ts:1-87`

F2.2 primitive. **F3.1 NO modifica useAuth.ts**, solo consume `useAuth()` desde `<LoginPage>` para detectar `data.user` resuelto + disparar `useEffect` redirect. SWR key `accessToken ? '/auth/me' : null` (skip fetch si no hay token). `refreshInterval: 5 * 60 * 1000`. `onError` con `status===401` dispara `useAuthStore.clear()` + `window.dispatchEvent('parkos:auth:cleared')` (F3.3+ AuthGuard consumer).

### 2.7 `parkosFetch.ts` — `apps/ui-kit/src/fetch/parkosFetch.ts:1-212`

F2.2 primitive. **F3.1 NO consume parkosFetch para login** (DEC-F3.1-05: usa `fetch` raw). Razones: (a) NO Authorization Bearer pre-login (no existe token); (b) leer `Retry-After` header en 429 (parkosFetch NO expone headers raw); (c) `credentials:'include'` explícito sin que parkosFetch intercepte. Para `GET /auth/me` post-login, `useAuth()` SÍ usa parkosFetch (vía SWR fetcher) — eso está wireado en F2.2 y F3.1 lo hereda.

### 2.8 `package.json` — `apps/electron-sucursal/package.json:22-77`

**YA EXISTEN** (F2.1 + F2.2 — cero npm install):
- `react-hook-form@^7.53.0` (línea 45).
- `zod@^3.23.8` (línea 51).
- `@hookform/resolvers@^3.9.0` (línea 23).
- `@radix-ui/react-label@^2.1.0` (línea 27) — FormLabel shadcn.
- `react-router-dom@^6.27.0` (línea 47) — `<Route path="/login">`.
- `react-i18next@^15.0.2` + `i18next@^23.15.2` (líneas 41, 46).
- `swr@^2.2.5` (línea 48).
- `zustand@^5.0.0` (línea 52).
- `@playwright/test@^1.48.0` + `@axe-core/playwright@^4.10.0` (líneas 55-56).

**NO REQUERIDAS**: MSW 2.x — F3.1 mockea con `vi.fn()` + `fetch` global mock (Vitest 2.1.x baseline ya soporta `vi.spyOn(global, 'fetch')`). MSW no es necesario para 3 endpoints (200/401/429) y agrega complejidad de build pipeline. Forward hook: si F3.3+ requiere mocking más complejo, agregar MSW.

### 2.9 `i18n locales` — `apps/electron-sucursal/src/renderer/i18n/locales/`

**`auth.json` actual** (10 keys):

```json
{
  "loginTitle": "Iniciar sesión",
  "logout": "Cerrar sesión",
  "email": "Correo",
  "password": "Contraseña",
  "submit": "Ingresar",
  "sessionExpired": "Tu sesión expiró. Vuelve a iniciar sesión.",
  "lockout": "Cuenta bloqueada temporalmente.",
  "invalidCredentials": "Credenciales inválidas",
  "rememberMe": "Recordarme",
  "forgotPassword": "¿Olvidaste tu contraseña?"
}
```

**Gap identificado**: NO hay keys para `validation.email.invalid`, `validation.email.required`, `validation.password.minLength`, `validation.password.required`, `validation.required`. F3.1 T1 agrega 5 validation keys.

### 2.10 Backend API surface — READ-ONLY consumer anchors

Verificado contra `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-583` y `schemas/auth.py`:

- `POST /api/v1/auth/login` (auth.py:148-307) — `LoginRequest{email,password}` (EmailStr + min_length:8 + max_length:128) → `TokenPair{access_token, refresh_token, token_type, expires_in}` + cookie `parkos_session` httponly+secure+samesite=lax (auth.py:291-299). Errores: `401 invalid_credentials` (auth.py:188-191, 248-251) O `429 account_locked` con `Retry-After: minutos*60` (auth.py:219-228).
- `GET /api/v1/auth/me` (auth.py:419-583) — `AuthMeResponse{user: AuthUser, sucursal: SucursalItem, sucursales_permitidas: SucursalItem[], permisos: string[], expires_at: ISO 8601}`. Errores: `404 not_found` (antienumeration, auth.py:454-458).

**F3.1 NO modifica backend**: consume los 2 endpoints existentes.

### 2.11 shadcn primitives — `apps/electron-sucursal/src/renderer/components/ui/`

F2.1 baseline: `form.tsx` (Form/FormField/FormItem/FormLabel/FormControl/FormDescription/FormMessage), `input.tsx`, `button.tsx`. **F3.1 los reusa** sin modificar. Componentes ya tienen `aria-invalid`, `aria-describedby`, label `htmlFor` asociados via `useFormField()` (líneas 67-88, 121-141). FormMessage renderiza `error.message` con `text-destructive` (líneas 159-181).

### 2.12 `apps/ui-kit/` exports

- `apps/ui-kit/src/hooks/index.ts` exporta `useAuth`, `UseAuthReturn`, `AuthMeResponse`.
- `apps/ui-kit/src/store/index.ts` exporta `useAuthStore`, `AuthState`.
- `apps/ui-kit/src/fetch/index.ts` exporta `parkosFetch, parkosFetchRaw, ParkosHttpError, ParkosFetchInit`.

F3.1 importa `@parkos/ui-kit/hooks` (useAuth) + `@parkos/ui-kit/store` (useAuthStore). NO modifica ui-kit.

---

## 3. Estado objetivo (TO-BE)

### 3.1 Tree delta (target)

```
apps/electron-sucursal/
├── src/
│   ├── features/auth/                            ← NEW (T1 + T2)
│   │   ├── components/
│   │   │   ├── LoginForm.tsx                     ← NEW (~60 LOC)
│   │   │   └── LoginForm.test.tsx                ← NEW (~30 LOC)
│   │   ├── pages/
│   │   │   ├── Login.tsx                         ← NEW (~75 LOC = 60 T1 + 5 T2 + 10 T3)
│   │   │   └── Login.test.tsx                    ← NEW (~80 LOC = 50 T1 + 30 T3)
│   │   └── api/
│   │       ├── loginApi.ts                       ← NEW (~30 LOC)
│   │       └── loginApi.test.ts                  ← NEW (~50 LOC)
│   └── renderer/
│       ├── App.tsx                               ← MODIFY (+5 LOC — <Route path="/login">)
│       └── i18n/locales/auth.json                ← MODIFY (+5 validation keys)
└── e2e/auth/
    └── login.spec.ts                             ← NEW (~80 LOC — 3 scenarios)
```

### 3.2 Login.tsx (target)

```typescript
// apps/electron-sucursal/src/features/auth/pages/Login.tsx (~75 LOC target)

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@parkos/ui-kit/hooks';
import { useAuthStore } from '@parkos/ui-kit/store';

import { LoginForm } from '../components/LoginForm';
import { loginSchema, type LoginInput } from '../api/loginSchema';
import { postLogin, AccountLockedError, InvalidCredentialsError } from '../api/loginApi';

type ErrorState =
  | { kind: 'invalid_credentials' }
  | { kind: 'lockout'; retryAfterSeconds: number }
  | { kind: 'network' }
  | null;

export function Login(): JSX.Element {
  const { t } = useTranslation('auth');
  const navigate = useNavigate();
  const { isAuthenticated, isLoading, data } = useAuth();
  const setTokens = useAuthStore((s) => s.setTokens);

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    mode: 'onBlur',
    defaultValues: { email: '', password: '' },
  });

  // DEC-F3.1-07: esperar data.user antes de navigate
  useEffect(() => {
    if (isAuthenticated && data?.user && !isLoading) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, data?.user, isLoading, navigate]);

  const onSubmit = form.handleSubmit(async (values) => {
    setErrorState(null);
    try {
      const pair = await postLogin(values.email, values.password);
      setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
      // Redirect lo dispara el useEffect cuando SWR resuelve data.user
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
    <LoginForm
      form={form}
      onSubmit={onSubmit}
      isSubmitting={form.formState.isSubmitting}
      error={errorState}
    />
  );
}
```

### 3.3 LoginForm.tsx (target — presentational puro)

```typescript
// apps/electron-sucursal/src/features/auth/components/LoginForm.tsx (~60 LOC target)

import { useTranslation } from 'react-i18next';
import { useFormContext } from 'react-hook-form';

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

export type LoginErrorState =
  | { kind: 'invalid_credentials' }
  | { kind: 'lockout'; retryAfterSeconds: number }
  | { kind: 'network' }
  | null;

export interface LoginFormProps {
  form: ReturnType<typeof useFormContext<LoginInput>>;
  onSubmit: () => void;
  isSubmitting: boolean;
  error: LoginErrorState;
}

export function LoginForm({ form, onSubmit, isSubmitting, error }: LoginFormProps): JSX.Element {
  const { t } = useTranslation('auth');

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} noValidate aria-labelledby="login-title">
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

        <Button type="submit" disabled={isSubmitting} data-testid="login-submit">
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
```

---

## 4. Arquitectura de alto nivel

### 4.1 Vista de capas (ASCII)

```
┌───────────────────────────────────── Renderer (React 18 + RHF + Zod + SWR) ─────────────────────────┐
│                                                                                                    │
│   <App>                                                                                            │
│   ├── <StatusBar />  (F2.3 — backend health visible durante login)                                 │
│   └── <main>                                                                                       │
│       └── <Routes>                                                                                 │
│           ├── <Route path="/" element={null}>                                                     │
│           └── <Route path="/login" element={<LoginPage />} />   ◄── NEW F3.1                      │
│                                                                                                    │
│   <LoginPage>  (container, F3.1 NEW ~75 LOC)                                                       │
│   ├── useForm({ resolver: zodResolver(loginSchema) })                                              │
│   ├── useAuth() ──► { isAuthenticated, isLoading, data, error }                                    │
│   ├── useAuthStore.getState().setTokens(access, refresh, expires_in)                               │
│   ├── useNavigate()                                                                                │
│   ├── useEffect([isAuthenticated, data?.user, isLoading]) ──► navigate('/')  ◄── DEC-F3.1-07      │
│   └── <LoginForm form={form} onSubmit={onSubmit} isSubmitting error />                            │
│                                                                                                    │
│   <LoginForm>  (presentational, F3.1 NEW ~60 LOC)                                                  │
│   ├── <Form {...form}>                                                                             │
│   │   ├── <FormField name="email">  ──► Input type="email" autoComplete="username"               │
│   │   ├── <FormField name="password"> ──► Input type="password" autoComplete="current-password"   │
│   │   ├── <Button type="submit" disabled={isSubmitting}>{t('submit')}</Button>                    │
│   │   └── {error && <p role="alert">{message}</p>}                                                 │
│                                                                                                    │
└─────────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                          │ fetch (raw, credentials:'include')
                                          │ setTokens ──► authStore Zustand ──► SWR key ──► parkosFetch
                                          ▼
┌───────────────────────────────────────── Main Process (Electron 30, IPC bridge F2.2+F2.3) ────────┐
│                                                                                                    │
│   bridge.authStore.{get,set,delete} ──► electron-store (userData/auth.json)  ◄── persist JWT      │
│                                                                                                    │
└─────────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                          │ HTTPS (parkosFetch automático + cookie auto-enviada)
                                          ▼
┌───────────────────────────────────────── Backend FastAPI (HU-F1.2 shipped) ────────────────────────┐
│                                                                                                    │
│   POST /api/v1/auth/login                                                                         │
│   ├── 200 OK ──► { access_token, refresh_token, expires_in } + Set-Cookie parkos_session           │
│   │             (httponly=True, secure=True, samesite="lax", max_age=3600, path="/")              │
│   ├── 401 ──► { error: "invalid_credentials" } (antienumeration, auth.py:188-191, 248-251)        │
│   ├── 429 ──► { error: "account_locked", retry_after_seconds } + Retry-After header                │
│   │             (auth.py:219-228)                                                                 │
│   └── 422 ──► Zod-falla (NO debería ocurrir si cliente valida antes)                                │
│                                                                                                    │
│   GET /api/v1/auth/me                                                                              │
│   ├── 200 OK ──► AuthMeResponse { user, sucursal, sucursales_permitidas, permisos, expires_at }    │
│   └── 404 ──► cualquier JWT failure mode colapsa a 404 (antienumeration, auth.py:454-458)         │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Principios arquitectónicos

1. **Container/Presentational split** (DEC-F3.1-02): `<LoginPage>` es container (RHF + Zod + postLogin + setTokens + useAuth + useNavigate + useEffect); `<LoginForm>` es presentational puro (props in, JSX out). El container es testeable con mocks (`vi.spyOn(global, 'fetch')` + `vi.mock('@parkos/ui-kit/hooks')`); el presentational es testeable con `@testing-library/react` + `axe-core` sin mocks.
2. **Atomic Design + Feature Slicing** (DEC-F3.1-01): bounded context isolation. `features/auth/` para Fase 3.1; `features/caja/` para F3.3 (turno); `features/facturacion/` para F5+ (impresión). NO mezclar con `src/renderer/components/` (que es para UI reutilizable cross-feature: Button, Form, StatusBar).
3. **Login vía HTTP directo, NO IPC** (DEC-F3.1-04): auth es data plane estándar, NO capability privileged. El navegador gestiona cookie via `credentials:'include'`. IPC bridge F2.2 ya wireó `bridge.authStore.{get,set,delete}` para persistencia — F3.1 consume indirectamente via `useAuthStore.setTokens`.
4. **`fetch` raw para login, NO parkosFetch** (DEC-F3.1-05): parkosFetch optimiza el 95% de los casos (auth header + sucursal header + idempotency + retry + refresh). Login es el 5% exceptional: NO Bearer pre-login, leer `Retry-After` header, custom error mapping.
5. **Hidratación transaccional** (DEC-F3.1-07): `useEffect` espera `data?.user` antes de `navigate('/')`. Sin flash de "sesión no iniciada" en el destino.
6. **Anti-enumeración cross-layer** (DEC-F3.1-08): backend colapsa 401 a `errors.invalid_credentials`; frontend colapsa 401 a `t('invalidCredentials')`. Atacante no distingue email válido vs inválido.
7. **Zod local en form, NO en parkosFetch schema** (DEC-F3.1-06): validación form es UX (mensaje inline); validación response es contract (backend Pydantic ya lo cubre). Si shape drift, TS strict + cast catches en compile-time.

---

## 5. Decisiones arquitectónicas (DEC-F3.1-NN × 11)

Cross-ref `proposal.md` §5 + `exploration.md` §6. Tabla resumen con anclas a las justificaciones extendidas (proposal §5.1-5.11 + exploration §9).

| ID | Title | Choice | Rationale | Alternativas rechazadas | Anchor |
|---|---|---|---|---|---|
| **DEC-F3.1-01** | Feature folder `src/features/auth/` | `apps/electron-sucursal/src/features/auth/{pages,components,api}/` | Atomic Design + Feature Slicing (F2.1 DEC-ELEC-08); cada bounded context en su carpeta; F3.3 vivirá en `features/caja/` | (a) `src/renderer/components/Login.tsx` — RECHAZADA (mezcla UI cross-feature con pages); (b) flat `src/pages/Login.tsx` — RECHAZADA (sin bounded context isolation) | proposal §5.1, exploration §6.1/9.1 |
| **DEC-F3.1-02** | Container/Presentational split | `Login.tsx` container + `LoginForm.tsx` presentational con props `{form, onSubmit, isSubmitting, error}` | Container testeable con mocks; presentational testeable con @testing-library/react sin mocks | (a) todo en Login.tsx — RECHAZADA (mega-componente); (b) custom hook `useLoginFlow` + Login.tsx declarativo — opcional, NO bloquea design | proposal §5.2, exploration §6.2 |
| **DEC-F3.1-03** | `credentials:'include'` para cookie httpOnly round-trip | `fetch('/api/v1/auth/login', { credentials: 'include', ... })` explícito | `HttpOnly` flag blinda contra XSS; `SameSite=Lax` blinda contra CSRF; `credentials:'include'` mandatory para que el navegador persista + envíe cookie | (a) sin credentials — RECHAZADA (cookie se setea pero NO persiste); (b) SameSite=Strict — RECHAZADA (rompe link desde email); (c) SameSite=None;Secure — RECHAZADA (requiere HTTPS cross-origin en dev) | proposal §5.3, exploration §6.3 |
| **DEC-F3.1-04** | Login vía HTTP directo (NO IPC bridge) | `fetch` raw en renderer; NO nuevos métodos IPC `bridge.auth.login` | IPC es para capabilities privileged (print, usb, kiosk, app quit); auth es HTTP estándar; `credentials:'include'` es Browser API, NO IPC | (a) IPC `bridge.auth.login` — RECHAZADA (over-engineering, electron session API para cookie jar); (b) IPC `bridge.auth.me` — RECHAZADA (idem) | proposal §5.4, exploration §6.4/9.2 |
| **DEC-F3.1-05** | Login usa `fetch` raw, NO `parkosFetch` | `fetch` raw + custom error mapping `InvalidCredentialsError` / `AccountLockedError` | parkosFetch está optimizado para data plane autenticado (Bearer + retry + refresh); login es la PUERTA al data plane — caso exceptional | (a) `parkosFetch<TokenPair>('/auth/login', {body, credentials:'include'})` — RECHAZADA (NO expone Retry-After header; colapsa error mapping); (b) wrapper `parkosFetchLogin` específico — RECHAZADA (over-engineering para 1 endpoint) | proposal §5.5, exploration §6.5/9.3 |
| **DEC-F3.1-06** | Zod local en form (NO parkosFetch schema) | `z.object({email: z.string().email(), password: z.string().min(8)})` vía `@hookform/resolvers/zod` | Validación form es UX (mensaje inline); validación response es contract (backend Pydantic); Zod en boundary es DEC-FETCH-05 optional | (a) Zod schema en `parkosFetch<TokenPair>(url, init, schema)` — RECHAZADA (defense-in-depth extra no exigido); (b) validación manual sin Zod — RECHAZADA (verbose, TS no ayuda) | proposal §5.6, exploration §6.6 |
| **DEC-F3.1-07** | Redirect transaccional post-hidratación | `useEffect([isAuthenticated, data?.user, isLoading])` → `navigate('/')` solo si `data?.user` resuelto | Operador llega a `/` con `user` + `sucursal` + `permisos` TODOS resueltos — sin flash de "sesión no iniciada" | (a) `navigate('/')` inmediato post-setTokens — RECHAZADA (flash); (b) redirect cuando `isAuthenticated && !isLoading` — RECHAZADA (`data?.user` aún null) | proposal §5.7, exploration §6.7/9.4 |
| **DEC-F3.1-08** | Anti-enumeración cross-layer | 401 (cualquier causa) → `t('invalidCredentials')`; 429 → `t('lockout')`; NO distinción email vs password | Backend colapsa 401 a `errors.invalid_credentials` (auth.py:159-191); frontend matchea; bcrypt ~250ms enmascara timing attacks | (a) diferenciar "email no existe" vs "password incorrecta" — RECHAZADA (enumeration); (b) mensaje genérico "error de autenticación" — ACEPTADA (también cumple, pero `invalidCredentials` es más UX-friendly) | proposal §5.8, exploration §6.8 |
| **DEC-F3.1-09** | Auto-redirect a `/login` cuando `parkos:auth:cleared` event fires | F3.1 NO crea redirect logic; usa evento que `useAuth()` ya emite; F3.3+ agregan `<AuthGuard>` | Separación de concerns: Login page NO necesita auth-guard (es el entry point); dashboards sí | (a) F3.1 incluye AuthGuard — RECHAZADA (mezcla scopes); (b) F3.1 ignora el evento — RECHAZADA (forward hook bloqueado) | proposal §5.9, exploration §6.9 |
| **DEC-F3.1-10** | e2e 3 escenarios | `e2e/auth/login.spec.ts` con login-ok-cookie + refresh-transparente + logout | Plan.md:1295 verbatim; cobertura end-to-end del flujo de auth; logout verifica `useAuthStore.clear()` aunque F3.1 NO renderiza UI logout | (a) 1 escenario login-ok — RECHAZADA (cobertura insuficiente); (b) 5+ escenarios — RECHAZADA (over-coverage, sandbox F.6 skip) | proposal §5.10, exploration §6.10 |
| **DEC-F3.1-11** | DELTA con 7 new REQ-OPS-106..112 | `openspec/changes/hu-f3-1-login-email-password/specs/operations/spec.md` AGREGA 7 new REQ-OPS al spec canónico (NO NO-OP stub) | F3.1 es user-facing behavior observable (login UI + mensajes error + cookie round-trip); precedent correcto es F1.15 (login histórico, 4 new REQ-OPS-102..105) | (a) NO-OP stub precedent F2.1/F2.2/F2.3 — RECHAZADA (F3.1 NO es infra-only); (b) DELTA con 4 new REQ-OPS-106..109 — RECHAZADA (cobertura insuficiente) | proposal §5.11 |

---

## 6. Componentes y contratos (TS interfaces)

### 6.1 `LoginInput` (form schema types)

```typescript
// apps/electron-sucursal/src/features/auth/api/loginSchema.ts (~10 LOC target)

import { z } from 'zod';

/**
 * Form input para Login — DEC-F3.1-06 Zod local.
 * - email formato válido (z.string().email())
 * - password mínimo 8 caracteres (z.string().min(8))
 * - ambos requeridos (campos vacíos rechazados)
 */
export const loginSchema = z.object({
  email: z
    .string()
    .min(1, { message: 'validation.required' })
    .email({ message: 'validation.email.invalid' }),
  password: z
    .string()
    .min(1, { message: 'validation.required' })
    .min(8, { message: 'validation.password.minLength' }),
});

export type LoginInput = z.infer<typeof loginSchema>;
```

### 6.2 `TokenPair` (loginApi response)

```typescript
// apps/electron-sucursal/src/features/auth/api/loginApi.ts (~30 LOC target)

/**
 * Response de POST /api/v1/auth/login (HU-F1.2 shipped, schemas/auth.py).
 * Coincide 1:1 con backend TokenPair Pydantic schema.
 */
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'Bearer';
  expires_in: number; // segundos hasta expiración
}
```

### 6.3 Error classes (custom error mapping)

```typescript
// apps/electron-sucursal/src/features/auth/api/loginApi.ts (~30 LOC target)

/**
 * 401 — Credenciales inválidas (DEC-F3.1-08 anti-enumeración).
 * Backende colapsa email-no-existe + password-incorrecta + cuenta-deshabilitada
 * a este único error. Frontend muestra t('invalidCredentials').
 */
export class InvalidCredentialsError extends Error {
  readonly name = 'InvalidCredentialsError';
}

/**
 * 429 — Cuenta bloqueada por N intentos fallidos (DEC-F3.1-08).
 * Header Retry-After: <segundos>. F3.2 hook consume retryAfterSeconds para countdown UI.
 */
export class AccountLockedError extends Error {
  readonly name = 'AccountLockedError';
  constructor(public readonly retryAfterSeconds: number) {
    super(`Account locked. Retry after ${retryAfterSeconds} seconds.`);
  }
}
```

### 6.4 `LoginErrorState` (component prop)

```typescript
// apps/electron-sucursal/src/features/auth/components/LoginForm.tsx (~60 LOC target)

/**
 * Estado de error que Login.tsx pasa a LoginForm para renderizar mensajes.
 * - invalid_credentials → <p role="alert">{t('invalidCredentials')}</p>
 * - lockout            → <p role="alert">{t('lockout')}</p>
 * - network            → <p role="alert">{t('errors:serverError')}</p>
 */
export type LoginErrorState =
  | { kind: 'invalid_credentials' }
  | { kind: 'lockout'; retryAfterSeconds: number }
  | { kind: 'network' }
  | null;
```

### 6.5 Tipos auxiliares (forward hooks)

```typescript
// apps/electron-sucursal/src/features/auth/api/loginApi.ts (forward hook F3.2)

// F3.2 useCountdown hook consumirá AccountLockedError.retryAfterSeconds.
// F3.1 NO implementa countdown UI — solo surfacea el error.
```

---

## 7. loginApi.ts y error mapping

Cross-ref `proposal.md` §7.1 + `exploration.md` §4.3.

### 7.1 `postLogin` (función principal)

```typescript
// apps/electron-sucursal/src/features/auth/api/loginApi.ts (~30 LOC target)

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const LOGIN_PATH = '/api/v1/auth/login';

/**
 * POST /api/v1/auth/login con credentials:'include'.
 * DEC-F3.1-03: cookie httpOnly round-trip mandatory.
 * DEC-F3.1-05: fetch raw (NO parkosFetch) — no Authorization Bearer pre-login.
 *
 * Errores mapeados:
 * - 401 → InvalidCredentialsError (DEC-F3.1-08 anti-enumeración)
 * - 429 → AccountLockedError(retryAfterSeconds) (DEC-F3.1-08 + forward F3.2)
 * - 5xx/network → ParkosHttpError (re-throw)
 */
export async function postLogin(email: string, password: string): Promise<TokenPair> {
  const res = await fetch(LOGIN_PATH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include', // CRITICAL: cookie httpOnly round-trip
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new InvalidCredentialsError();
    }
    if (res.status === 429) {
      const retryAfterHeader = res.headers.get('Retry-After');
      const retryAfterSeconds = retryAfterHeader !== null ? Number(retryAfterHeader) : 0;
      throw new AccountLockedError(Number.isFinite(retryAfterSeconds) ? retryAfterSeconds : 0);
    }
    throw new ParkosHttpError(res.status, await res.text().catch(() => ''), res.url);
  }

  return (await res.json()) as TokenPair;
}
```

### 7.2 Tabla de status → error

| Status | Error thrown | UI message |
|---|---|---|
| 200 | (return TokenPair) | (redirect post-hidratación) |
| 401 | `InvalidCredentialsError` | `t('invalidCredentials')` ("Credenciales inválidas") |
| 429 | `AccountLockedError(retryAfterSeconds)` | `t('lockout')` ("Cuenta bloqueada temporalmente.") |
| 422 | `ParkosHttpError(422, ...)` | `t('errors:serverError')` (fallback genérico) |
| 5xx | `ParkosHttpError(5xx, ...)` | `t('errors:serverError')` |
| Network/timeout | `Error` (fetch rejected) | `t('errors:serverError')` |

### 7.3 Cookie handling notes

- **Set-Cookie response**: el backend envía `Set-Cookie: parkos_session=<jwt>; HttpOnly; Secure; SameSite=Lax; Max-Age=3600; Path=/`. El navegador ACEPTA porque `credentials:'include'` se setea en el request. La cookie se persiste en el cookie jar del origin.
- **Auto-envío en subsiguientes requests**: cuando `Login.tsx` ejecuta `postLogin(...)` y luego `useAuth()` dispara `parkosFetch('/auth/me')` con `Authorization: Bearer <access>`, el navegador ADEMÁS envía `Cookie: parkos_session=<jwt>` (auto). El backend lee JWT del header O de la cookie (F2.2 auth.py:291-299). Cookie es el mecanismo primario post-login; Bearer es fallback si el operador borra cookies manualmente.
- **Cross-origin**: `SameSite=Lax` permite la cookie en top-level navigation (link desde email, por ejemplo). Cross-site form submissions NO la envían (CSRF mitigation). Si el kiosko está en `https://sucursal.parkos.local` y el operador llega via link desde email, la cookie viaja.

---

## 8. State management (authStore + useAuth)

Cross-ref `proposal.md` §8 + `exploration.md` §3.1 + §2.5 + §2.6.

### 8.1 `authStore` state shape (F2.2 verbatim, F3.1 consume)

```typescript
// apps/ui-kit/src/store/authStore.ts (F2.2 — READ-ONLY, F3.1 consume)

export interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: string | null;
  setTokens: (access: string, refresh: string, expiresIn: number) => void;
  clear: () => void;
}
```

### 8.2 `setTokens` invariante (F2.2 atomic)

```typescript
// apps/ui-kit/src/store/authStore.ts línea 77-80
setTokens: (access, refresh, expiresIn) => {
  const expiresAt = new Date(Date.now() + expiresIn * 1000).toISOString();
  set({ accessToken: access, refreshToken: refresh, expiresAt });
}
```

**Atomicidad**: Zustand `set` es síncrono. Las 3 keys (`accessToken`, `refreshToken`, `expiresAt`) se actualizan simultáneamente en el mismo tick. NO hay race condition entre `setTokens` y el `useEffect` redirect en `<LoginPage>`.

### 8.3 `useAuth()` SWR key derivation

```typescript
// apps/ui-kit/src/hooks/useAuth.ts líneas 53-58
const accessToken = useAuthStore((s) => s.accessToken);

const { data, error, isLoading, mutate } = useSWR<AuthMeResponse>(
  accessToken ? '/auth/me' : null,
  parkosFetch,
  { /* ... */ }
);
```

- Pre-login: `accessToken === null` → SWR key `null` → SWR skip fetch.
- Post-`setTokens`: `accessToken === '<jwt>'` → SWR key `'/auth/me'` → SWR dispara fetch.
- `data.user` se popula cuando el fetch resuelve (typical ~100-300ms en kiosko local).

### 8.4 `useEffect` redirect transaccional (DEC-F3.1-07)

```typescript
// apps/electron-sucursal/src/features/auth/pages/Login.tsx (F3.1 NEW)

useEffect(() => {
  if (isAuthenticated && data?.user && !isLoading) {
    navigate('/', { replace: true });
  }
}, [isAuthenticated, data?.user, isLoading, navigate]);
```

- `replace: true` evita que el operador presione "atrás" y vuelva a `/login` (ya está autenticado).
- Las 3 deps garantizan que el redirect ocurre solo cuando TODO está resuelto.

### 8.5 Local form state (RHF, NO authStore)

- `Login.tsx` mantiene form state local via `useForm<LoginInput>`. NO persiste a `authStore` ni a electron-store.
- `defaultValues: { email: '', password: '' }` — campos vacíos al mount.
- `mode: 'onBlur'` — validación on blur (no on every keystroke). UX-friendly para kiosko (operador tipea, ve error al tab-out).
- `formState.isSubmitting` durante `postLogin` async — deshabilita `<Button type="submit">` + muestra `t('common:loading')`.

---

## 9. Manejo de errores (cross-layer)

Cross-ref `proposal.md` §9 + `exploration.md` §7 R1..R8.

### 9.1 Matriz de errores

| Origen | Status / Tipo | Error class | UI message | Anchor |
|---|---|---|---|---|
| Backend | 401 invalid_credentials | `InvalidCredentialsError` | `t('invalidCredentials')` | DEC-F3.1-08 |
| Backend | 429 account_locked + Retry-After | `AccountLockedError(retryAfterSeconds)` | `t('lockout')` | DEC-F3.1-08 |
| Backend | 422 validation_error (NO debería ocurrir) | `ParkosHttpError(422, ...)` | `t('errors:serverError')` (fallback) | — |
| Backend | 5xx server_error | `ParkosHttpError(5xx, ...)` | `t('errors:serverError')` | — |
| Network | fetch rejected (TypeError) | `Error` (native) | `t('errors:serverError')` (catch-all) | — |
| Client (form) | Zod invalid email | (RHF error state) | `<FormMessage>{t('validation.email.invalid')}</FormMessage>` | DEC-F3.1-06 |
| Client (form) | Zod password < 8 | (RHF error state) | `<FormMessage>{t('validation.password.minLength')}</FormMessage>` | DEC-F3.1-06 |
| Client (form) | Campo vacío | (RHF error state) | `<FormMessage>{t('validation.required')}</FormMessage>` | DEC-F3.1-06 |

### 9.2 Comportamiento `useEffect` post-error

Si `postLogin` lanza `InvalidCredentialsError` / `AccountLockedError` / `ParkosHttpError`:
1. `setErrorState(...)` actualiza local state en `<LoginPage>`.
2. `<LoginForm>` re-renderiza con `<p role="alert">` visible.
3. `useAuth()` mantiene `isAuthenticated: false` (NO se llamó `setTokens`).
4. `useEffect` NO dispara `navigate('/')` (deps `isAuthenticated && data?.user && !isLoading` siguen `false`).
5. Operador permanece en `/login` con mensaje visible. Puede reintentar.

### 9.3 Recovery de errores transient (network)

Si `fetch` rejected por timeout/red caída:
- `Login.tsx` catch genérico → `setErrorState({ kind: 'network' })`.
- Operador ve "Error del servidor. Intente nuevamente." (`errors:serverError`).
- Botón submit sigue habilitado (NO lockout — el lockout es del backend, no del cliente).
- Reintentar: operador corrige la red / espera y re-submit.

### 9.4 No-recovery de lockout (429)

`AccountLockedError(retryAfterSeconds)`:
- UI muestra `t('lockout')` — mensaje estático ("Cuenta bloqueada temporalmente.").
- F3.1 NO renderiza countdown (forward hook a F3.2: `useCountdown(retryAfterSeconds)` hook + disable form durante countdown).
- Operador NO puede reintentar hasta que pase el `retryAfterSeconds` (backend lo rechaza con 429 si lo intenta antes).
- Forward: F3.2 lee `AccountLockedError.retryAfterSeconds` y renderiza `<Countdown seconds={retryAfterSeconds} />` + `<Button disabled={countdown > 0}>`.

---

## 10. Seguridad (cross-layer)

Cross-ref `proposal.md` §10 + `exploration.md` §7 R1..R8.

### 10.1 Defense in depth (5 capas, F3.1 contribution)

| Layer | Mechanism | Source | F3.1 contribution |
|---|---|---|---|
| 1 auth | JWT Bearer (F2.2) + cookie httpOnly SameSite=Lax (F1.2 backend) + bcrypt (F1.2 backend) | `useAuth.ts` + `loginApi.ts` + backend `auth.py:148-583` | CONSUME + ERROR MAPPING 401/429 |
| 2 engineering | TS strict + `noUncheckedIndexedAccess` + ESLint flat (F2.1) | tsconfig.* + eslint.config.js | `Login.tsx` + `LoginForm.tsx` heredan |
| 3 a11y | axe-core WCAG 2.1 AA (RNF-022) + FormField aria-invalid + FormMessage role=alert | `@axe-core/playwright` (F2.1) + shadcn `form.tsx` (F2.1) + F3.1 LoginForm | ADD axe-core test + aria-invalid verify |
| 4 contract | Zod local form (DEC-F3.1-06) + backend Pydantic (F1.2) + 7 new REQ-OPS-106..112 (DEC-F3.1-11) | `@hookform/resolvers/zod` + `schemas/auth.py` + `operations/spec.md` delta | ADD 7 new REQ-OPS-NNN al spec canónico |
| 5 retry-budget | parkosFetch retry 5xx + 401 refresh-once (F2.2 DEC-FETCH-02/03) | parkosFetch.ts | NO custom retry en login |

### 10.2 CSRF mitigation (R1)

- `credentials:'include'` + `SameSite=Lax` en cookie `parkos_session` → cross-site form submissions NO incluyen la cookie.
- Backend CORS config (no F3.1 scope) verifica `Origin` header.
- Ataque CSRF clásico (forzar al operador a submit un form a `/auth/login` desde otro sitio) está mitigado: el navegador NO envía la cookie pre-existente (no existe aún para cross-site), Y el atacante no puede leer la respuesta (Same-Origin Policy).

### 10.3 XSS mitigation (R2)

- `HttpOnly` flag en cookie → `document.cookie` NO expone `parkos_session` a JavaScript.
- CSP estricto en renderer (F2.1 baseline) previene inline scripts maliciosos.
- Si atacante inyecta script via XSS, puede hacer `fetch('/auth/me')` (porque la cookie se auto-envía con `credentials:'include'`), pero NO puede exfiltrar la cookie misma. Limitación: atacante aún puede usar la sesión del operador para acciones autenticadas (mismo nivel que el operador).
- Mitigación adicional: sanitización de input (RHF no inserta HTML; todo es value).

### 10.4 Timing attack mitigation (R5)

- Backend usa `bcrypt.checkpw` (~250ms con factor 12) tanto para email-existe como email-no-existe (rama `if user is None: return False` ejecuta igualmente el bcrypt contra dummy hash).
- Latencia adicional enmascara la diferencia entre "email existe, password incorrecta" (~250ms) y "email no existe" (~250ms + dummy hash). Atacante no puede inferir email válido midiendo timing.
- Frontend: el mensaje único `t('invalidCredentials')` tampoco revela.

### 10.5 Password handling (R7)

- RHF mantiene `password` en `formState` durante el ciclo de vida del componente.
- Cuando `<LoginPage>` unmounts (post-redirect a `/`), React garbage-collects `formState`. NO persiste a electron-store ni a localStorage.
- Aceptable para kiosko desatendido (post-shift el proceso se reinicia via electron-updater).
- Forward: si se requiere zeroización post-submit, agregar `form.reset()` post-`postLogin` 200 OK (T2 follow-up opcional).

### 10.6 Zod schema drift (R6)

- Frontend: `z.string().min(8)`. Backend: `StringConstraints(min_length=8, max_length=128)`.
- Match al commit. Si backend cambia a `min_length:10`, frontend Zod local acepta password de 8 chars → backend responde 422 → frontend muestra `t('errors:serverError')` (fallback). UX degrada pero NO se rompe.
- Forward: si la divergencia es recurrente, considerar `parkosFetch<T>(url, init, zodSchema)` (DEC-FETCH-05 optional).

### 10.7 Cookie no persiste en reload (R3)

- Browser persiste cookies httponly hasta `Max-Age` (3600s).
- Operador refresca `/login` (Ctrl+R) → cookie sigue → `useAuth()` SWR re-fetcha `/auth/me` con `Authorization: Bearer <token-en-authStore>` + cookie auto-enviada → re-hidrata store.
- Edge case: operador borra cookies manualmente → cookie perdida → `useAuth()` recibe 404 → `useAuthStore.clear()` + `parkos:auth:cleared` event → forward AuthGuard F3.3+ redirect a `/login`.

---

## 11. Accesibilidad WCAG 2.1 AA (RNF-022)

Cross-ref `proposal.md` §11 + RNF-022 (`docs/01-requisitos/no-funcionales.md:126`) + DEC-F3.1-01 (REQ-OPS-112).

### 11.1 Cobertura axe-core

`LoginForm.tsx` debe pasar axe-core scan con 0 violaciones. Cobertura específica:

| Criterio WCAG 2.1 AA | Implementación | Test |
|---|---|---|
| 1.3.1 Info and Relationships | `<FormLabel htmlFor>` + `<FormControl id>` asociados via `useFormField()` (shadcn `form.tsx:67-140`) | axe-core auto-detect |
| 1.4.3 Contrast (Minimum) | shadcn tokens + tailwind `text-destructive` para errores (4.5:1 mínimo) | axe-core auto-detect |
| 3.3.1 Error Identification | `<FormMessage role="alert">` con `id={formMessageId}` + `aria-describedby` | axe-core + vitest query `getByRole('alert')` |
| 3.3.2 Labels or Instructions | `<FormLabel>` con texto `t('email')` / `t('password')` | axe-core auto-detect |
| 4.1.2 Name, Role, Value | `aria-invalid={!!error}` en `<FormControl>` | axe-core auto-detect |
| 2.1.1 Keyboard | Tab order secuencial: email → password → submit | vitest `userEvent.tab()` |
| 2.4.7 Focus Visible | shadcn `Input` tiene focus ring via `focus-visible:ring-2` | axe-core + manual |

### 11.2 `aria-invalid` pattern

```typescript
// shadcn form.tsx línea 121-141 (F2.1 baseline — F3.1 hereda)
const FormControl = React.forwardRef<...>(({ ...props }, ref) => {
  const { error, formItemId, formDescriptionId, formMessageId } = useFormField();

  return (
    <Slot
      ref={ref}
      id={formItemId}
      aria-describedby={!error ? `${formDescriptionId}` : `${formDescriptionId} ${formMessageId}`}
      aria-invalid={!!error}
      {...props}
    />
  );
});
```

`<LoginForm>` no necesita lógica adicional — el slot propaga `aria-invalid` automáticamente cuando hay error Zod.

### 11.3 `role="alert"` pattern

```tsx
// LoginForm.tsx líneas 80-95 (F3.1 NEW)
{error?.kind === 'invalid_credentials' && (
  <p role="alert" data-testid="login-error-invalid">
    {t('invalidCredentials')}
  </p>
)}
```

Screen reader anuncia el error inmediatamente al renderizar (live region implicit). axe-core valida `role="alert"` válido + texto no vacío.

### 11.4 Tab order

```tsx
// Tab order natural sin tabIndex custom:
<Input type="email" />   // tab 0
<Input type="password" /> // tab 0
<Button type="submit" /> // tab 0
```

Orden secuencial: email → password → submit. Enter en password dispara form submit (default browser behavior).

### 11.5 axe-core test

```typescript
// apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx (~30 LOC)

// ... render <LoginForm> con form mockeado ...
const results = await axe(container);
expect(results).toHaveNoViolations();
```

Vitest + `@testing-library/react` + `vitest-axe` matcher. Test corre en jsdom env (F2.1 baseline).

---

## 12. i18n strategy

Cross-ref `proposal.md` §12 + `auth.json` actual (10 keys).

### 12.1 Namespace `auth` (F2.1 baseline + F3.1 delta)

```json
// apps/electron-sucursal/src/renderer/i18n/locales/auth.json (F3.1 MODIFY — +5 keys)

{
  "loginTitle": "Iniciar sesión",
  "logout": "Cerrar sesión",
  "email": "Correo",
  "password": "Contraseña",
  "submit": "Ingresar",
  "sessionExpired": "Tu sesión expiró. Vuelve a iniciar sesión.",
  "lockout": "Cuenta bloqueada temporalmente.",
  "invalidCredentials": "Credenciales inválidas",
  "rememberMe": "Recordarme",
  "forgotPassword": "¿Olvidaste tu contraseña?",
  "validation": {
    "required": "Este campo es obligatorio",
    "email": {
      "invalid": "Ingresa un correo válido"
    },
    "password": {
      "minLength": "La contraseña debe tener al menos 8 caracteres",
      "required": "Ingresa tu contraseña"
    }
  }
}
```

### 12.2 Namespace `errors` (F2.1 baseline — F3.1 consume `serverError`)

`errors.json` ya tiene `serverError`, `networkError`, etc. (F2.1 shippeó 8 keys). F3.1 consume `errors:serverError` para `network` error state en `<LoginForm>`.

### 12.3 Namespace `common` (F2.1 baseline — F3.1 consume `loading`)

`common.json` ya tiene `loading`. F3.1 consume `common:loading` para mostrar "Cargando..." en el botón submit durante `formState.isSubmitting`.

### 12.4 Convenciones

- Un namespace por bounded context (DEC-F3.1-01). Login = `auth`. NO `auth/login` (namespace plano per F2.1 DEC-ELEC-06).
- Keys en `camelCase`. Mensajes en español neutro profesional.
- 5 nuevas validation keys organizadas en sub-objeto `validation` para agrupar (no en top-level).
- Forward: si F3.3+ requiere `auth.lockout.countdown`, agregar al mismo namespace.

---

## 13. Estrategia de testing

Cross-ref `proposal.md` §13 G1..G6 + exploration §12.

### 13.1 Vitest unit (mockeando `fetch` global + `useAuth`)

**`apps/electron-sucursal/src/features/auth/api/loginApi.test.ts`** (~50 LOC, 5 escenarios):

| # | Escenario | Aserción clave |
|---|---|---|
| U1 | 200 OK → retorna `TokenPair` con `access_token` parseado | `vi.spyOn(global, 'fetch').mockResolvedValue({ ok: true, json: async () => mockTokenPair })` |
| U2 | 401 → throws `InvalidCredentialsError` | mock 401 + assert `instanceof InvalidCredentialsError` |
| U3 | 429 + Retry-After → throws `AccountLockedError(retryAfter)` | mock 429 + header `Retry-After: 300` + assert `error.retryAfterSeconds === 300` |
| U4 | 5xx → throws `ParkosHttpError` | mock 500 + assert `instanceof ParkosHttpError && status === 500` |
| U5 | request lleva `credentials:'include'` + Content-Type JSON | spy fetch + assert call args `credentials: 'include'` y `Content-Type: application/json` |

**`apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx`** (~30 LOC, 3 escenarios):

| # | Escenario | Aserción clave |
|---|---|---|
| U6 | Render presentacional con form mockeado | `screen.getByTestId('login-email')` + `login-password` + `login-submit` |
| U7 | error `invalid_credentials` → muestra `<p role="alert">` con `t('invalidCredentials')` | query `getByRole('alert')` + texto |
| U8 | axe-core 0 violaciones | `expect(await axe(container)).toHaveNoViolations()` |

**`apps/electron-sucursal/src/features/auth/pages/Login.test.tsx`** (~80 LOC, 6 escenarios — T1 50 + T3 30):

| # | Escenario | Aserción clave |
|---|---|---|
| U9 | Submit email+password válidos → `setTokens` llamado + redirect post-`data.user` | mock fetch 200 + spy `useAuthStore.setTokens` + `vi.mock('@parkos/ui-kit/hooks')` retorna `{data: {user: {id: 'u1'}}, isAuthenticated: true, isLoading: false}` + assert `navigate('/')` |
| U10 | Submit email+password inválidos → `InvalidCredentialsError` + muestra `t('invalidCredentials')` | mock fetch 401 + assert role alert visible |
| U11 | RHF valida email formato inválido → NO llama `postLogin` + muestra `t('validation.email.invalid')` | fill `email: 'not-an-email'` + submit + assert fetch NOT called |
| U12 | RHF valida password < 8 → NO llama `postLogin` + muestra `t('validation.password.minLength')` | fill `password: 'short'` + submit + assert fetch NOT called |
| U13 | R3 redirect waits for `data.user` (no flash) | `useAuth` returns `{data: undefined, isAuthenticated: true}` → assert `navigate NOT called` |
| U14 | T3 redirect fires after `data.user` resolved | `useAuth` returns `{data: {user: {...}}, isAuthenticated: true, isLoading: false}` → assert `navigate('/') called` |

### 13.2 Playwright e2e (`_electron.launch`)

**`apps/electron-sucursal/e2e/auth/login.spec.ts`** (~80 LOC, 3 escenarios):

| # | Escenario |
|---|---|
| E1 | **login-ok-cookie**: operador tipea email+password válidos → cookie `parkos_session` set (`page.context().cookies()`) → redirect a `/` → `useAuth().user.email === <test email>` (assert via DOM render del topbar F11.x placeholder) |
| E2 | **refresh-transparente**: setTokens via authStore + advance fake timers 50min + verificar SWR revalida `/auth/me` (F2.2 `refreshInterval: 5min`; el test verifica que tras 401 en otra llamada, refresh-once dispara) |
| E3 | **logout**: `useAuthStore.clear()` setea tokens a null + segundo `/auth/me` retorna 404 → `useAuth()` limpia store + emite `parkos:auth:cleared` event → window listener dispara (forward F3.3 AuthGuard stub verifica) |

### 13.3 A11y axe-core e2e (RNF-022)

```typescript
// Reusar F2.1 + F2.2 e2e/a11y/wcag-2.1-aa.spec.ts (F2.1 baseline)
// +1 caso específico para /login route:

test('Login page pasa axe-core WCAG 2.1 AA', async ({ page }) => {
  await page.goto('/login');
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```

### 13.4 Sandbox F.6 caveat

Per F2.1 + F2.2 + F2.3 archive reports, las e2e (`login.spec.ts`) corren en sandbox F.6 con npm 11.16.0 que refuses `workspace:*` resolution. F3.1 e2e va a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect. Unit tests (vitest + @testing-library/react sobre Login.tsx mockeado) cubren el camino crítico.

### 13.5 Cobertura thresholds

```typescript
// apps/electron-sucursal/vitest.config.ts (extracto — F2.1 baseline, F3.1 SIN CAMBIOS)

coverage: {
  provider: 'v8',
  thresholds: {
    // ... existing thresholds F2.1+F2.2 ...
    'src/features/auth/pages/Login.tsx':      { lines: 80, functions: 80, branches: 75 },
    'src/features/auth/components/LoginForm.tsx': { lines: 80, functions: 80, branches: 75 },
    'src/features/auth/api/loginApi.ts':      { lines: 80, functions: 80, branches: 75 },
  },
}
```

---

## 14. Consideraciones de performance

Cross-ref `proposal.md` §14.

### 14.1 Latencia del redirect (~100-300ms)

Flujo login OK:

```
t=0     Usuario submit
t=10ms  fetch POST /auth/login
t=80ms  backend bcrypt verify + JWT sign + Set-Cookie
t=90ms  response 200 OK + TokenPair body
t=95ms  Login.tsx: setTokens() — sync
t=100ms SWR detecta nuevo accessToken — key cambia a '/auth/me'
t=110ms parkosFetch('/auth/me') dispatch
t=250ms backend SELECT user + sucursal + permisos — ~150ms
t=260ms response 200 OK + AuthMeResponse
t=270ms useAuth() retorna {user, isAuthenticated: true}
t=275ms useEffect deps changed → navigate('/')
```

**Total**: ~275ms desde submit hasta redirect. Operador percibe feedback visual inmediato (botón "Cargando..." durante el submit). Aceptable para login flow (UX profesional no debe ser instantáneo — credibilidad requiere latencia perceptible).

### 14.2 Bundle size

Login chunk (Vite tree-shaking):

- `react-hook-form` + `@hookform/resolvers/zod`: ~25KB minified (lazy-loaded con Login route).
- `zod`: ~12KB minified.
- `Login.tsx` + `LoginForm.tsx`: ~3KB minified.
- `loginApi.ts`: ~1KB minified.

**Total Login chunk**: ~41KB minified + gzip ~12KB. Aceptable para SPA kiosko (F2.1 bundle total ~200KB gzipped, Login suma ~6%).

### 14.3 Memory footprint

- `formState` durante sesión activa: ~1KB (email + password strings + RHF metadata).
- `useAuthStore` post-login: ~500B (3 strings: accessToken + refreshToken + expiresAt).
- `useAuth().data`: ~2KB (AuthMeResponse: user + sucursal + sucursales_permitidas + permisos + expires_at).

**Total**: ~3.5KB adicional en memoria por sesión activa. Insignificante.

### 14.4 Network requests

- 1 request POST `/auth/login` (200 OK + Set-Cookie + JSON body ~300B).
- 1 request GET `/auth/me` (200 OK + JSON body ~500B).
- Refresh cada 5min si operador en `/` post-redirect (F2.2 `refreshInterval`).
- 429 lockout: 0 requests adicionales (UI estática, sin polling).

**Total**: ~2 requests por login flow + 1 cada 5min en sesión activa. Acceptable.

---

## 15. Migración y rollout

Cross-ref `proposal.md` §15 + `pending.md` Fase 3 0/3 abierto.

### 15.1 F3.1 entrega

**Cluster C1** (4 atomic tasks T1..T4) en orden mandatory:

```
T1 — Login page + LoginForm + RHF+Zod + 5 i18n keys
   ↓ (T1 provee Login + LoginForm declarativos sin API integration)
T2 — loginApi.ts + postLogin + error mapping + setTokens integration
   ↓ (T2 provee setTokens post-200 OK + error surface)
T3 — useEffect redirect + App.tsx Route /login
   ↓ (T3 provee redirect transaccional post-data.user)
T4 — e2e login.spec.ts (3 scenarios)
   ↓ (T4 provee e2e green gate)
archive — mover change folder a archive/, actualizar pending.md §1 row F3.1 → ✅
```

### 15.2 Forward hooks (Fase 3+)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.2** (lockout visible + refresh pre-flight) | `AccountLockedError(retryAfterSeconds)` de F3.1 | F3.2 wraps Login.tsx `onSubmit` con disable form durante countdown + `<Countdown seconds={retryAfterSeconds} />` |
| **HU-F3.3** (abrir/cerrar turno) | `useAuth().user.sucursal` + `permisos` hidratados post-F3.1 | F3.3 `<AbrirTurno>` lee `user.sucursal.uuid` y filtra `permisos.includes('caja.apertura')` antes de POST `/caja-sesion/sesiones` |
| **HU-F3.x** (logout UI) | `useAuthStore.clear()` + `parkos:auth:cleared` event (ya implementados F2.2) | F3.x `<LogoutButton onClick={() => useAuthStore.getState().clear() + navigate('/login')} />` |
| **HU-F3.x** (AuthGuard component) | `parkos:auth:cleared` window event | F3.x `<AuthGuard>` escucha evento → `navigate('/login?next=...')`. F3.1 Login page NO necesita AuthGuard (es el entry point) |
| **HU-F4.x** (catálogos + ocupación) | `useAuth()` + parkosFetch | F4.x lee `user.sucursal.uuid` para scoped queries a `/productos/*` |
| **HU-F5.x+** (impresión térmica) | `useAuth().permisos` filter | F5.x verifica `permisos.includes('facturacion.emitir')` antes de imprimir |
| **HU-F11.x** (sync UI topbar) | useAuth (no directo) | F11.x muestra `user.email` en topbar post-login |
| **PR7 backend** (refresh rotation) | authStore + refresh logic (no F3.1) | Detección de reuse jti claim (F2.2 DEC-FETCH-03 cubre sin rotation; rotación es PR7+) |

### 15.3 Rollout strategy

- **Branch**: `feat/fase-2-electron-scaffold` (HEAD `ba9d81a`).
- **PR target**: `origin/dev`.
- **Merge order**: F3.1 merge a `dev` ANTES de F3.2 (F3.2 depende de `AccountLockedError`).
- **Feature flag**: NO. F3.1 es consumer directo de infra shipped F2.1+F2.2+F2.3. Cero toggle runtime.
- **Sandbox**: F3.1 e2e puede SKIP en sandbox F.6 (npm 11.16.0 refuses workspace:*) — documentado como D-env en verify-report. Unit tests cubren el camino crítico.
- **Local dev**: e2e verdes en Windows native con npm 11.16+ (per F2.1+F2.2+F2.3 archive precedent).

### 15.4 Pendiente post-archive

- `pending.md` §1 row F3.1 → marcar ✅ cerrado.
- `docs/02-arquitectura/decisiones-tecnicas.md` → agregar DEC-F3.1-01..11 resumen (cross-ref `proposal.md` §5).
- `openspec/CHANGELOG.md` → entrada "2026-09-15 — HU-F3.1 login email+password archived (7 new REQ-OPS-106..112 user-facing)".
- `openspec/specs/operations/spec.md` post-archive → REQ-OPS vigente = 001..112 (112 total).

---

## Appendix A: TS mockups completos (~450 LOC)

### A.1 `loginApi.ts` completo (~30 LOC target)

```typescript
// apps/electron-sucursal/src/features/auth/api/loginApi.ts

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const LOGIN_PATH = '/api/v1/auth/login';

/**
 * Response de POST /api/v1/auth/login (HU-F1.2 shipped, schemas/auth.py).
 * Coincide 1:1 con backend TokenPair Pydantic schema.
 */
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'Bearer';
  expires_in: number;
}

/**
 * 401 — Credenciales inválidas (DEC-F3.1-08 anti-enumeración).
 * Backend colapsa email-no-existe + password-incorrecta + cuenta-deshabilitada
 * a este único error. Frontend muestra t('invalidCredentials').
 */
export class InvalidCredentialsError extends Error {
  readonly name = 'InvalidCredentialsError';
}

/**
 * 429 — Cuenta bloqueada por N intentos fallidos (DEC-F3.1-08).
 * Header Retry-After: <segundos>. F3.2 hook consume retryAfterSeconds
 * para countdown UI. F3.1 solo surfacea el error estático.
 */
export class AccountLockedError extends Error {
  readonly name = 'AccountLockedError';
  constructor(public readonly retryAfterSeconds: number) {
    super(`Account locked. Retry after ${retryAfterSeconds} seconds.`);
  }
}

/**
 * POST /api/v1/auth/login con credentials:'include'.
 * DEC-F3.1-03: cookie httpOnly round-trip mandatory.
 * DEC-F3.1-05: fetch raw (NO parkosFetch) — no Authorization Bearer pre-login.
 *
 * Errores mapeados:
 * - 401 → InvalidCredentialsError (DEC-F3.1-08 anti-enumeración)
 * - 429 → AccountLockedError(retryAfterSeconds) (DEC-F3.1-08 + forward F3.2)
 * - 5xx/network → ParkosHttpError o Error (catch-all)
 */
export async function postLogin(email: string, password: string): Promise<TokenPair> {
  const res = await fetch(LOGIN_PATH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include', // CRITICAL: cookie httpOnly round-trip
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new InvalidCredentialsError();
    }
    if (res.status === 429) {
      const retryAfterHeader = res.headers.get('Retry-After');
      const parsed = retryAfterHeader !== null ? Number(retryAfterHeader) : NaN;
      const retryAfterSeconds = Number.isFinite(parsed) ? parsed : 0;
      throw new AccountLockedError(retryAfterSeconds);
    }
    throw new ParkosHttpError(res.status, await res.text().catch(() => ''), res.url);
  }

  return (await res.json()) as TokenPair;
}
```

### A.2 `loginSchema.ts` completo (~10 LOC target)

```typescript
// apps/electron-sucursal/src/features/auth/api/loginSchema.ts

import { z } from 'zod';

/**
 * Form input para Login — DEC-F3.1-06 Zod local.
 * - email formato válido (z.string().email())
 * - password mínimo 8 caracteres (z.string().min(8))
 * - ambos requeridos (campos vacíos rechazados)
 *
 * Messages son KEYS de i18n, no strings hardcoded — el componente
 * <LoginForm> los traduce via useTranslation('auth').
 */
export const loginSchema = z.object({
  email: z
    .string()
    .min(1, { message: 'validation.required' })
    .email({ message: 'validation.email.invalid' }),
  password: z
    .string()
    .min(1, { message: 'validation.required' })
    .min(8, { message: 'validation.password.minLength' }),
});

export type LoginInput = z.infer<typeof loginSchema>;
```

### A.3 `Login.tsx` container completo (~75 LOC target)

```typescript
// apps/electron-sucursal/src/features/auth/pages/Login.tsx

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';
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
  const { t: _ } = useTranslation('auth'); // i18n ready — keys via FormMessage
  const navigate = useNavigate();
  const { isAuthenticated, isLoading, data } = useAuth();
  const setTokens = useAuthStore((s) => s.setTokens);

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    mode: 'onBlur',
    defaultValues: { email: '', password: '' },
  });

  const [errorState, setErrorState] = useState<LoginErrorState>(null);

  // DEC-F3.1-07: esperar data.user antes de navigate (transaccional, sin flash)
  useEffect(() => {
    if (isAuthenticated && data?.user && !isLoading) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, data?.user, isLoading, navigate]);

  const onSubmit = form.handleSubmit(async (values) => {
    setErrorState(null);
    try {
      const pair = await postLogin(values.email, values.password);
      setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
      // El redirect lo dispara el useEffect cuando SWR resuelve data.user
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
    <LoginForm
      form={form}
      onSubmit={onSubmit}
      isSubmitting={form.formState.isSubmitting}
      error={errorState}
    />
  );
}
```

### A.4 `LoginForm.tsx` presentacional completo (~60 LOC target)

```typescript
// apps/electron-sucursal/src/features/auth/components/LoginForm.tsx

import { useTranslation } from 'react-i18next';
import { useFormContext } from 'react-hook-form';

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

export type LoginErrorState =
  | { kind: 'invalid_credentials' }
  | { kind: 'lockout'; retryAfterSeconds: number }
  | { kind: 'network' }
  | null;

export interface LoginFormProps {
  form: ReturnType<typeof useFormContext<LoginInput>>;
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
```

### A.5 `i18n/locales/auth.json` delta (~5 keys new)

```diff
 {
   "loginTitle": "Iniciar sesión",
   "logout": "Cerrar sesión",
   "email": "Correo",
   "password": "Contraseña",
   "submit": "Ingresar",
   "sessionExpired": "Tu sesión expiró. Vuelve a iniciar sesión.",
   "lockout": "Cuenta bloqueada temporalmente.",
   "invalidCredentials": "Credenciales inválidas",
   "rememberMe": "Recordarme",
-  "forgotPassword": "¿Olvidaste tu contraseña?"
+  "forgotPassword": "¿Olvidaste tu contraseña?",
+  "validation": {
+    "required": "Este campo es obligatorio",
+    "email": {
+      "invalid": "Ingresa un correo válido"
+    },
+    "password": {
+      "minLength": "La contraseña debe tener al menos 8 caracteres",
+      "required": "Ingresa tu contraseña"
+    }
+  }
 }
```

### A.6 `App.tsx` delta (~5 LOC target)

```diff
 import { useTranslation } from 'react-i18next';
 import { Route, Routes } from 'react-router-dom';

 import { StatusBar } from './components/StatusBar';
+import { Login } from '../features/auth/pages/Login';

 export default function App() {
   const { t } = useTranslation('common');

   return (
     <>
       <StatusBar />
       <main lang="es-CO">
         <h1>{t('appName')}</h1>
         <p>{t('bootstrapNotice')}</p>
         <Routes>
           <Route path="/" element={null} />
+          <Route path="/login" element={<Login />} />
           <Route
             path="*"
             element={
               <p role="status">{t('error', { defaultValue: '404' })}</p>
             }
           />
         </Routes>
       </main>
     </>
   );
 }
```

### A.7 `e2e/auth/login.spec.ts` outline (~80 LOC — 3 scenarios)

```typescript
// apps/electron-sucursal/e2e/auth/login.spec.ts

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Login flow', () => {
  test('E1 — login-ok-cookie', async ({ page, context }) => {
    await page.goto('/login');

    await page.getByTestId('login-email').fill('operador@sucursal-1.parkos.local');
    await page.getByTestId('login-password').fill('valid-password-1234');
    await page.getByTestId('login-submit').click();

    // Cookie httpOnly round-trip
    const cookies = await context.cookies();
    const parkosSession = cookies.find((c) => c.name === 'parkos_session');
    expect(parkosSession).toBeDefined();
    expect(parkosSession?.httpOnly).toBe(true);
    expect(parkosSession?.sameSite).toBe('Lax');

    // Redirect post-hidratación
    await page.waitForURL('/');
    // Topbar F11.x placeholder verifica user.email (forward consumer)
  });

  test('E2 — refresh-transparente tras 401', async ({ page }) => {
    // Login OK primero
    await page.goto('/login');
    await page.getByTestId('login-email').fill('operador@sucursal-1.parkos.local');
    await page.getByTestId('login-password').fill('valid-password-1234');
    await page.getByTestId('login-submit').click();
    await page.waitForURL('/');

    // Mock /auth/me para retornar 401 una vez
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({ status: 401, body: JSON.stringify({ error: 'expired' }) }),
    );

    // Esperar refresh-once — parkosFetch detecta 401 → clear() + emit parkos:auth:cleared
    await expect(page).toHaveURL(/\/login/);
  });

  test('E3 — logout limpia store + emite parkos:auth:cleared', async ({ page }) => {
    // Login OK primero (reutilizar E1 setup)
    await page.goto('/login');
    await page.getByTestId('login-email').fill('operador@sucursal-1.parkos.local');
    await page.getByTestId('login-password').fill('valid-password-1234');
    await page.getByTestId('login-submit').click();
    await page.waitForURL('/');

    // Llamar useAuthStore.clear() via window injection (test-only)
    await page.evaluate(() => {
      const w = window as unknown as {
        bridge?: { authStore?: { delete: (k: string) => Promise<void> } };
      };
      void w.bridge?.authStore?.delete('parkos.auth');
    });

    // /auth/me retorna 404 → useAuth limpia store + emite event
    await expect(page).toHaveURL(/\/login/);
  });

  test('A1 — axe-core WCAG 2.1 AA en /login', async ({ page }) => {
    await page.goto('/login');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
});
```

### A.8 `Login.test.tsx` container outline (~80 LOC — 6 scenarios)

```typescript
// apps/electron-sucursal/src/features/auth/pages/Login.test.tsx

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Mocks — placed BEFORE imports per Vitest hoisting
const mockNavigate = vi.fn();
const mockSetTokens = vi.fn();
const mockUseAuth = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@parkos/ui-kit/hooks', () => ({ useAuth: mockUseAuth }));
vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: { getState: () => ({ setTokens: mockSetTokens }) },
}));

import { Login } from './Login';

function mockFetchOnce(body: unknown, status = 200, headers: Record<string, string> = {}): void {
  vi.spyOn(global, 'fetch').mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
    text: async () => JSON.stringify(body),
    url: '/api/v1/auth/login',
  } as Response);
}

describe('Login container', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      data: undefined,
    });
  });

  it('U9 — submit OK llama setTokens + redirect post-data.user', async () => {
    mockFetchOnce({ access_token: 'a', refresh_token: 'r', token_type: 'Bearer', expires_in: 3600 });

    // Re-mock useAuth para retornar data.user post-setTokens
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      data: { user: { id: 'u1', email: 'op@test.co' } },
    });

    render(<MemoryRouter><Login /></MemoryRouter>);
    await userEvent.type(screen.getByTestId('login-email'), 'op@test.co');
    await userEvent.type(screen.getByTestId('login-password'), 'password1234');
    await userEvent.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      expect(mockSetTokens).toHaveBeenCalledWith('a', 'r', 3600);
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
    });
  });

  it('U10 — 401 muestra t("invalidCredentials")', async () => {
    mockFetchOnce({}, 401);
    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.type(screen.getByTestId('login-email'), 'op@test.co');
    await userEvent.type(screen.getByTestId('login-password'), 'password1234');
    await userEvent.click(screen.getByTestId('login-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('login-error-invalid')).toBeInTheDocument();
    });
  });

  it('U11 — Zod email inválido NO llama fetch', async () => {
    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.type(screen.getByTestId('login-email'), 'not-an-email');
    await userEvent.click(screen.getByTestId('login-submit'));

    expect(global.fetch).not.toHaveBeenCalled();
    expect(await screen.findByText(/validation.email.invalid/)).toBeInTheDocument();
  });

  it('U12 — Zod password < 8 NO llama fetch', async () => {
    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.type(screen.getByTestId('login-email'), 'op@test.co');
    await userEvent.type(screen.getByTestId('login-password'), 'short');
    await userEvent.click(screen.getByTestId('login-submit'));

    expect(global.fetch).not.toHaveBeenCalled();
    expect(await screen.findByText(/validation.password.minLength/)).toBeInTheDocument();
  });

  it('U13 — redirect NO dispara si data.user es undefined', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: true,
      data: undefined,
    });

    render(<MemoryRouter><Login /></MemoryRouter>);

    await waitFor(() => {
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });

  it('U14 — redirect dispara tras data.user resuelto', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      data: { user: { id: 'u1', email: 'op@test.co' } },
    });

    render(<MemoryRouter><Login /></MemoryRouter>);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
    });
  });
});
```

---

## Appendix B: Configuraciones y archivos delta

### B.1 NEW (7 archivos de producción + 2 tests)

| Path | Task | LOC target |
|---|---|---|
| `apps/electron-sucursal/src/features/auth/api/loginApi.ts` | T2 | 30 |
| `apps/electron-sucursal/src/features/auth/api/loginApi.test.ts` | T2 | 50 |
| `apps/electron-sucursal/src/features/auth/api/loginSchema.ts` | T1 | 10 |
| `apps/electron-sucursal/src/features/auth/pages/Login.tsx` | T1+T2+T3 | 75 |
| `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` | T1+T3 | 80 |
| `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` | T1 | 60 |
| `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` | T1 | 30 |
| `apps/electron-sucursal/e2e/auth/login.spec.ts` | T4 | 80 |
| **TOTAL** | T1..T4 | **~415 LOC** |

### B.2 MODIFY (2 archivos de producción + 5 i18n keys)

| Path | Task | Delta LOC |
|---|---|---|
| `apps/electron-sucursal/src/renderer/App.tsx` | T3 | +3 LOC (import + Route) |
| `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` | T1 | +5 validation keys (sub-objeto) |
| **TOTAL** | T1+T3 | **~8 LOC delta** |

### B.3 Configuraciones (verbatim diffs)

#### B.3.1 `package.json`

F3.1 **NO requiere nuevas dependencias**. Todo el stack ya está en `package.json:22-77` per F2.1+F2.2 baseline (RHF + Zod + resolvers + Label + Router + i18n + SWR + zustand + axe + playwright).

```diff
   "dependencies": {
     "react-hook-form": "^7.53.0",     // YA EXISTE
     "zod": "^3.23.8",                  // YA EXISTE
     "@hookform/resolvers": "^3.9.0",   // YA EXISTE
     "@radix-ui/react-label": "^2.1.0", // YA EXISTE
     "react-router-dom": "^6.27.0",     // YA EXISTE
     // ... resto sin cambios
   }
```

#### B.3.2 `tsconfig.renderer.json`

```diff
   "compilerOptions": {
     "strict": true,
     "noUncheckedIndexedAccess": true,
     "paths": {
       "@/*": ["./src/*"],
+      "@/features/*": ["./src/features/*"],
+      "@parkos/ui-kit": ["../../packages/ui-kit/src/index.ts"],
+      "@parkos/ui-kit/hooks": ["../../packages/ui-kit/src/hooks/index.ts"],
+      "@parkos/ui-kit/store": ["../../packages/ui-kit/src/store/index.ts"],
+      "@parkos/ui-kit/fetch": ["../../packages/ui-kit/src/fetch/index.ts"]
     }
   },
   "include": [
     "src/**/*.ts",
     "src/**/*.tsx"
   ]
```

(NOTA: `@parkos/ui-kit/*` paths pueden ya existir en F2.1+F2.2 baseline — verificar antes de aplicar.)

#### B.3.3 `vitest.config.ts`

```diff
   test: {
     environment: 'jsdom',
     globals: true,
     setupFiles: ['./src/test/setup.ts'],
     coverage: {
       provider: 'v8',
       thresholds: {
-        // F2.1 + F2.2 thresholds existentes
+        'src/features/auth/pages/Login.tsx':          { lines: 80, functions: 80, branches: 75 },
+        'src/features/auth/components/LoginForm.tsx':  { lines: 80, functions: 80, branches: 75 },
+        'src/features/auth/api/loginApi.ts':          { lines: 80, functions: 80, branches: 75 },
       }
     }
   }
```

### B.4 READ ONLY (anchors — NO modificar)

- `apps/electron-sucursal/electron/main.ts` (F2.3, no F3.1 touch — DEC-F3.1-04 login HTTP no IPC).
- `apps/electron-sucursal/electron/preload.ts` (F2.2, no F3.1 touch).
- `apps/electron-sucursal/electron/bridge.d.ts` (F2.2+F2.3, no F3.1 touch).
- `apps/ui-kit/src/fetch/parkosFetch.ts` (F2.2, no F3.1 touch — DEC-F3.1-05 raw fetch).
- `apps/ui-kit/src/store/authStore.ts` (F2.2, no F3.1 touch — setTokens ya existe).
- `apps/ui-kit/src/hooks/useAuth.ts` (F2.2, no F3.1 touch — SWR ya hidrata desde /auth/me).
- `apps/ui-kit/package.json` (F2.2, no F3.1 touch — zustand ya en deps).
- `apps/electron-sucursal/src/renderer/components/ui/{form,input,button}.tsx` (F2.1, no F3.1 touch — reusa shadcn).
- `apps/electron-sucursal/src/renderer/i18n/index.ts` (F2.1, no F3.1 touch — auth namespace ya registrado).
- `apps/electron-sucursal/src/renderer/i18n/locales/{common,operacion,caja,facturacion,sync,errors}.json` (F2.1, no F3.1 touch).
- `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (F2.3, no F3.1 touch).
- `apps/electron-sucursal/src/renderer/main.tsx` (F2.1, no F3.1 touch — BrowserRouter ya wrappea).
- `apps/electron-sucursal/e2e/{scaffold,auth/parkos-fetch,auth/bridge,a11y/wcag-2.1-aa,lifecycle,kiosko}.spec.ts` (F2.1+F2.2+F2.3, no F3.1 touch).
- `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py` (HU-F1.2 shipped, no F3.1 touch).
- `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` (HU-F1.2 shipped, no F3.1 touch).

### B.5 Total de impacto

- **NEW**: 8 archivos de producción + tests (~415 LOC) + 5 artefactos SDD (exploration + proposal + design + spec delta + tasks + verify-report + archive-report, ~3000 LOC).
- **MODIFY**: 2 archivos (~8 LOC delta production + 5 keys i18n).
- **READ ONLY**: 16 archivos.
- **TOTAL IMPACT**: 26 archivos de 415 LOC nuevos + 8 LOC delta + 3000 LOC artifacts.

---

## CHANGELOG

- (2026-09-15) F3.1 design phase complete — 15 secciones + 2 apéndices verbatim, ~870 LOC total. 11 DEC-F3.1-NN documentados (cross-ref proposal §5 + exploration §6). 6 acceptance gates G1..G6 + G7 implícito axe-core mapeados a tests (cross-ref proposal §13). Arquitectura: `<LoginPage>` container (RHF + Zod + postLogin + setTokens + useAuth + useNavigate + useEffect redirect) + `<LoginForm>` presentational (shadcn Form + Input + Button + role="alert") + `loginApi.ts` (fetch raw + custom error mapping InvalidCredentialsError/AccountLockedError). Hidratación transaccional post-`data.user` garantiza zero flash (DEC-F3.1-07). Cookie httpOnly round-trip via `credentials:'include'` (DEC-F3.1-03) + anti-enumeración cross-layer (DEC-F3.1-08) + WCAG 2.1 AA compliance (DEC-F3.1-01 → REQ-OPS-112). 8 TS mockups en Appendix A (loginApi.ts + loginSchema.ts + Login.tsx + LoginForm.tsx + auth.json delta + App.tsx delta + e2e outline + Login.test.tsx outline) + 3 configs delta en Appendix B.3 (package.json no-cambios + tsconfig.renderer.json + vitest.config.ts). Ready for sdd-tasks.

---

**End of design.**