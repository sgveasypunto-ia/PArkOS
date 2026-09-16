# Design — HU-F3.2 Lockout visible (countdown) + refresh transparente

> **Change**: `hu-f3-2-lockout-refresh-pre-flight` · **Folder**: `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/`
> **Phase**: design (sdd-design) · **Status**: ready for `sdd-tasks`
> **HU ID**: HU-F3.2 (Fase 3 — segunda HU; Autenticación y turno de caja, hardening UX + lifecycle del `access_token`)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `bcfe2ed`, F3.1 archivado 2026-09-15 con 7 REQ-OPS-106..112; F3.2 se commitea sobre la misma rama hasta migrar a `feat/fase-3-auth-turno` per `pending.md:6`)
> **Inputs**: `exploration.md` (~580 LOC, 18 secciones, 10 DEC-F3.2-01..10, 8 riesgos R1..R8, 6 gates G1..G6, 4 tasks T1..T4, pre-flight 10/10 PASS), `proposal.md` (~870 LOC, 16 secciones, 11 DEC-F3.2-01..11, DEC-F3.2-08 + DEC-F3.2-11 verdict DELTA, 6 new REQ-OPS-113..118), `specs/operations/spec.md` (paralelo — materializado con 6 REQ-OPS-113..118), `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/design.md` (~870 LOC, 15 secciones + 2 apéndices, 8 TS mockups — layout canónico clonado 1:1), `apps/electron-sucursal/src/features/auth/{api/loginApi.ts:1-93 (AccountLockedError.retryAfterSeconds + parseRetryAfter F3.1), components/LoginForm.tsx:1-133 (LoginErrorState kind:'lockout' + countdown placeholder 120-124 F3.1), pages/Login.tsx:1-81 (container con errorState wiring F3.1)}`, `apps/ui-kit/src/{fetch/parkosFetch.ts:1-212 (refresh-once 401 via handle401 + Mutex singleton + isLoginEndpoint skip), store/authStore.ts:1-129 (setTokens + clear + refreshAccessToken Mutex + expiresAt ISO 8601), hooks/useAuth.ts:1-87 (SWR refreshInterval 5*60*1000 — F3.2 CAMBIO a 50min + REFRESH_INTERVAL_MS export)}`, `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:21,71-72,279,285,297,306,343,348 (ACCESS_TOKEN_TTL=3600, REFRESH_TOKEN_TTL=7d, Retry-After header line 219-228)`, `docs/01-requisitos/no-funcionales.md:126 (RNF-022 WCAG 2.1 AA)`.
> **Language**: español neutro profesional · **Conventional commits**: `feat(auth)` / `feat(refresh)` / `test(electron)` — sin Co-authored-by.

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F3.2 |
| **Fase** | 3 (Autenticación y turno de caja — segunda HU) |
| **Change name** | `hu-f3-2-lockout-refresh-pre-flight` |
| **Folder** | `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/` |
| **State** | design ready |
| **Branch** | `feat/fase-2-electron-scaffold` |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | sdd-explore + sdd-propose + sdd-spec (paralelo) |
| **Próximo phase** | sdd-tasks |
| **DEC ratified** | 11 DEC-F3.2-01..11 (DEC-F3.2-08 + DEC-F3.2-11 verdict DELTA — F3.2 ES user-facing) |
| **REQ-OPS range** | REQ-OPS-113..118 (6 new requirements, continuación monotónica post F3.1 REQ-OPS-112) |
| **LOC target** | ~110 producción + ~240 tests + ~20 configs/JSDoc = **~370 LOC total** |
| **Conventional commits** | `feat(auth)` / `feat(refresh)` / `test(electron)` — sin Co-authored-by |

---

## 1. Visión general y objetivos

### 1.1 Objetivo primario

Definir la arquitectura técnica HOW del hardening de UX + lifecycle del `access_token` que F3.1 dejó abiertos. F3.2 entrega cuatro deliverables end-to-end verificables:

1. **`useCountdown(retryAfterSeconds)` hook reusable** (~40 LOC production) con `Date.now()` baseline (NO accumulator — drift-resistant), `setInterval(1000)` decrementando `secondsLeft`, cleanup en unmount via `useEffect` return, y `onComplete` callback cuando llega a 0. Primer hook genuinely reusable del feature `auth` para consumo cross-feature (forward F4.x retry buttons + F11.x reintentos de sync).
2. **Countdown visible en `LoginForm`** — `<p role="status" aria-live="polite" data-testid="login-countdown">{formatTime(secondsLeft)}</p>` debajo del mensaje `t('lockout')`. Form fields (`<Input>` + `<Button type="submit">`) con `disabled={true}` mientras `secondsLeft > 0`. Auto re-enable al llegar a 0 vía `Login.tsx` cuando `useCountdown().isExpired === true` dispara reset a `null` del `errorState`.
3. **Refresh transparente 50min SWR** — `useAuth.refreshInterval: 5 * 60 * 1000 → 50 * 60 * 1000` (constante `REFRESH_INTERVAL_MS` exportada). 10min safety margin vs `ACCESS_TOKEN_TTL = 3600` (`auth.py:71`). Per `DEC-SUC-03` (plan.md:418 verbatim).
4. **Pre-flight gate antes de POST críticos** — `parkosFetch.ts` agrega `refreshIfExpiringSoon()` ANTES de `POST /facturacion/*` + `POST /caja/arqueo` cuando `expiresAt - now < PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000`. Reusa el `refreshAccessToken` Mutex de F2.2 (`DEC-FETCH-03` invariant preserved) — cero doble refresh race.

Estos cuatro bloques blindan el lifecycle del `access_token` y desbloquean **8+ HUs downstream** (F3.3 abrir/cerrar turno con pre-flight automático, F4.x catálogos con retry buttons visuales, F5.x facturación con pre-flight ya cubierto, F11.x sync UI con countdown reusado) que heredan la infraestructura transversal sin renegociar el contrato de auth.

### 1.2 Objetivos secundarios

- **Defense in depth XR6** (cross-ref `operations/spec.md:3951`): las 5 capas existentes se fortalecen con la capa 5 retry-budget (pre-flight gate proactivo F3.2 + handle401 reactivo F2.2) y la capa 3 a11y (countdown WCAG 2.1 AA con `role="status"` + `aria-live="polite"` + axe-core A1 test). F3.2 NO crea nuevo REQ-OPS-XR — las decisiones viven como DEC-F3.2-NN + REQ-OPS-113..118 per F1.15 + F3.1 precedent.
- **Countdown drift resistance**: `Date.now()` baseline + recalc en cada tick (NO accumulator) garantiza countdown correcto aunque tab inactive + system sleep pausen `setInterval` (browser throttle). R1 mitigation.
- **Mutex singleton preserved** (DEC-FETCH-03 invariant): pre-flight gate REUSA `refreshAccessToken()` Mutex de F2.2. N concurrentes pre-flight + 401 callers comparten UNA promesa. Cero riesgo de doble refresh race (R2 mitigation).
- **WCAG 2.1 AA countdown accessibility** (RNF-022): `<p role="status" aria-live="polite">` anuncia cambios sin interrumpir (NO `aria-live="assertive"`); `aria-label={t('lockoutLabel')}` describe countdown para screen readers. axe-core A1 test verifica 0 violaciones con `withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])`.
- **Configurabilidad via constante exportada**: `REFRESH_INTERVAL_MS`, `PRE_FLIGHT_THRESHOLD_MS`, `PRE_FLIGHT_PATHS` — constantes módulo-level permiten tests deterministas sin magic numbers + forward extensibility via DEC-F3.2-10.
- **Cobertura >80%** en `useCountdown.ts` + `Login.tsx` + `LoginForm.tsx` + `parkosFetch.ts` (pre-flight gate). Vitest threshold per tsconfig.
- **TDD estricto**: cada test escrito ANTES de la implementación; 6 acceptance gates (G1..G6) deben pasar antes de merge.

### 1.3 No-objetivos (cross-ref proposal §3.2 / exploration §17)

- Backend cambios — `configuracion_seguridad.max_intentos_login` + `minutos_bloqueo_login` ya shipped Fase 1 (HU-F1.2); `Retry-After` header ya implementado `auth.py:219-228`. F3.2 consume vía `parseRetryAfter` (F3.1, loginApi.ts:59-63).
- Refresh-token rotation con `jti` reuse detection — PR7 backend (forward hook `pending.md §5`); F3.2 consume Mutex F2.2 sin modification.
- AuthGuard component — F3.3+ (intercepta `parkos:auth:cleared` event → `navigate('/login?next=...')`).
- Logout button UI — F3.3+ placeholder o HU posterior.
- Recuperación de password / 2FA / WebAuthn / biometric — fuera Fase 3 (futuro).
- Multi-tab login UI — kiosko single-tab por F2.3 single-instance lock (DEC-UPD-07).
- Turno abrir/cerrar — F3.3 (`features/caja/pages/{AbrirTurno,CerrarTurno}.tsx` + `useSesionActiva`).
- Countdown styling library externa — `formatTime` helper inline (~5 LOC), NO librería externa (mantener bundle size small — kiosko desatendido, RAM limitada).
- Toast notifications — out of scope Fase 3 (forward a F11.x sync UI).
- `REFRESH_INTERVAL_MS` configurable via UI — hardcoded a 50min per DEC-SUC-03; configurabilidad via env (`PARKOS_REFRESH_INTERVAL_MS`) es forward hook F3.x.
- Pre-flight para otros endpoints — T3 cubre solo `/facturacion/*` + `/caja/arqueo*` per `plan.md:1311` + DEC-SUC-03. Otros POST críticos futuros se agregan via DEC-F3.2-10.
- Pre-flight para GET requests — 401 retry cubre (handle401 F2.2). Pre-flight solo mutacionales POST.
- Per-account countdown state persistence — countdown es ephemeral (vive solo durante lockout active). Post-unmount, state GC'd. NO persist a electron-store.
- i18n plurals para countdown — `mm:ss` suficiente (max 99:59 = 2h, suficiente para `minutos_bloqueo_login` default 10min × max configurable 60min per `auth.py`).

---

## 2. Estado actual verificado (AS-IS)

### 2.1 `loginApi.ts` — `apps/electron-sucursal/src/features/auth/api/loginApi.ts:1-93`

F3.1 shippeó `AccountLockedError(retryAfterSeconds)` + `parseRetryAfter`. **F3.2 NO modifica loginApi.ts**: el 429 mapping + `Retry-After` header consumption ya está wireado. F3.2 consume `err.retryAfterSeconds` desde el `Login.tsx` catch block y lo pasa a `useCountdown`.

```typescript
// apps/electron-sucursal/src/features/auth/api/loginApi.ts:47-63 (F3.1 shippeó — F3.2 consume as-is)

/**
 * 429 — Cuenta bloqueada por N intentos fallidos (DEC-F3.1-08).
 * Header Retry-After: <segundos>. F3.2 useCountdown hook consume
 * retryAfterSeconds para countdown UI + form disable.
 */
export class AccountLockedError extends Error {
  readonly name = 'AccountLockedError';
  constructor(public readonly retryAfterSeconds: number) {
    super(`Account locked. Retry after ${retryAfterSeconds} seconds.`);
  }
}
```

### 2.2 `LoginForm.tsx` — `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx:1-133`

F3.1 shippeó `LoginErrorState kind:'lockout'` con display estático `<p role="alert">{t('lockout')}</p>` y `data-testid="login-error-lockout"` (line 120-124). **F3.2 T2 MODIFICA LoginForm.tsx** para: (a) consumir `useCountdown(retryAfterSeconds)` cuando `error.kind === 'lockout'`; (b) renderizar `<p role="status" aria-live="polite" data-testid="login-countdown">`; (c) aplicar `disabled={true}` a inputs + submit mientras `secondsLeft > 0`.

```typescript
// apps/electron-sucursal/src/features/auth/components/LoginForm.tsx:42-46 (F3.1 — F3.2 extienda in-place)

export type LoginErrorState =
  | { kind: 'invalid_credentials' }
  | { kind: 'lockout'; retryAfterSeconds: number }  // ← F3.2 consume
  | { kind: 'network' }
  | null;
```

### 2.3 `Login.tsx` — `apps/electron-sucursal/src/features/auth/pages/Login.tsx:1-81`

F3.1 shippeó container con RHF + Zod + postLogin + setTokens + useAuth + useNavigate + useEffect redirect transaccional (DEC-F3.1-07). **F3.2 T2 MODIFICA Login.tsx** para: (a) pasar `retryAfterSeconds` al state; (b) wire `useCountdown.isExpired` para reset `errorState` a `null` cuando countdown llega a 0.

### 2.4 `useAuth.ts` — `apps/ui-kit/src/hooks/useAuth.ts:1-87`

F2.2 primitive. **F3.2 T3 MODIFICA useAuth.ts:60** para cambiar `refreshInterval: 5 * 60 * 1000` → `REFRESH_INTERVAL_MS = 50 * 60 * 1000` (constante exportada para testabilidad). Update JSDoc para reflejar nuevo intervalo.

```typescript
// apps/ui-kit/src/hooks/useAuth.ts:60 (F2.2 baseline — F3.2 CAMBIO)

useSWR<AuthMeResponse>(
  accessToken ? '/auth/me' : null,
  parkosFetch,
  {
    refreshInterval: 5 * 60 * 1000,  // ← F3.2: refreshInterval: REFRESH_INTERVAL_MS
    revalidateOnFocus: true,
    dedupingInterval: 2000,
    // ...
  }
);
```

### 2.5 `parkosFetch.ts` — `apps/ui-kit/src/fetch/parkosFetch.ts:1-212`

F2.2 primitive con `handle401` Mutex refresh-once (DEC-FETCH-03). **F3.2 T3 MODIFICA parkosFetch.ts** para agregar pre-flight gate `refreshIfExpiringSoon()` invocado ANTES del `fetch` en `parkosFetchRaw` cuando `method === 'POST'` AND `url.match(PRE_FLIGHT_PATHS)` AND `useAuthStore.expiresAt !== null` AND `Date.parse(expiresAt) - Date.now() < PRE_FLIGHT_THRESHOLD_MS`.

```typescript
// apps/ui-kit/src/fetch/parkosFetch.ts:119-140 (F2.2 baseline — F3.2 preserve Mutex invariant)
//
// F3.2 agrega pre-flight gate en línea ~154-165 antes de fetch().
// Constante módulo-level PRE_FLIGHT_PATHS regex compilada una vez.
// Constante PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000.
// refreshIfExpiringSoon() await refreshAccessToken() (Mutex shared con handle401).
```

### 2.6 `authStore.ts` — `apps/ui-kit/src/store/authStore.ts:1-129`

F2.2 primitive con `setTokens` atómico + `clear` + `refreshAccessToken` Mutex singleton + `expiresAt` ISO 8601. **F3.2 NO modifica authStore.ts**: pre-flight gate CONSUME `useAuthStore.getState().refreshAccessToken()` (mismo Mutex que `handle401`). `expiresAt` derivable via `Date.parse(expiresAt)` para proximity check.

### 2.7 `package.json` — `apps/electron-sucursal/package.json:22-77` y `apps/ui-kit/package.json`

**YA EXISTEN** (F2.1 + F2.2 baseline — cero npm install):
- `react@^18.3.1` — provee `useState`, `useEffect`, `setInterval` (vanilla JS).
- `@testing-library/react@^16.0.1` + `vitest@^2.1.x` — unit tests T1 + T2 + T3.
- `@axe-core/playwright@^4.10.0` — e2e axe-core A1 test.
- `i18next@^23.15.2` + `react-i18next@^15.0.2` — `t('lockoutCountdown', { time })` interpolation.

**NO REQUERIDAS**: countdown library externa. `formatTime` helper inline (`mm:ss`). Vanilla JS `setInterval` + `Date.now()` suficiente.

### 2.8 `i18n locales` — `apps/electron-sucursal/src/renderer/i18n/locales/`

**`auth.json` actual** (post-F3.1, 15 keys + 5 validation sub-keys):

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
  "forgotPassword": "¿Olvidaste tu contraseña?",
  "validation": {
    "required": "Este campo es obligatorio",
    "email": { "invalid": "Ingresa un correo válido" },
    "password": {
      "minLength": "La contraseña debe tener al menos 8 caracteres",
      "required": "Ingresa tu contraseña"
    }
  }
}
```

**Gap identificado**: NO hay keys para countdown UI (`lockoutCountdown`, `lockoutReEnable`, `lockoutLabel`). F3.2 T2 agrega 3 keys en namespace `auth` (DEC-F3.2-06).

### 2.9 Backend API surface — READ-ONLY consumer anchors

Verificado contra `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-583`:

- `POST /api/v1/auth/login` (auth.py:148-307) — error 429 retorna `Retry-After: <segundos>` header (auth.py:219-228). `minutos_bloqueo_login` default 10min, configurable via `configuracion_seguridad` per `auth.py:225`. Consumido por `parseRetryAfter` (F3.1 loginApi.ts:59-63).
- `POST /api/v1/auth/refresh` (auth.py:310-349) — rota tokens. Consumido por `refreshAccessToken` Mutex (F2.2).
- `POST /api/v1/facturacion/*` (HU-F1.8 shipped, REQ-OPS-030) — pre-flight gate F3.2 matchea este path.
- `POST /api/v1/caja/arqueo` (Fase 10 forward, no existe aún) — pre-flight gate F3.2 matchea este path (forward extensibility, DEC-F3.2-10).

**F3.2 NO modifica backend**: consume los endpoints existentes + sus headers.

### 2.10 shadcn primitives — `apps/electron-sucursal/src/renderer/components/ui/`

F2.1 baseline: `form.tsx`, `input.tsx`, `button.tsx`. **F3.2 los reusa** sin modificar. Aplica `disabled` prop dinámicamente según lockout state. `<Input disabled>` y `<Button type="submit" disabled>` se renderizan via shadcn pattern (prop forwarded a `<slot>`).

### 2.11 `apps/ui-kit/` exports

- `apps/ui-kit/src/hooks/index.ts` exporta `useAuth`, `UseAuthReturn`, `AuthMeResponse`.
- `apps/ui-kit/src/store/index.ts` exporta `useAuthStore`, `AuthState`, `setTokens`, `clear`, `refreshAccessToken`.
- `apps/ui-kit/src/fetch/index.ts` exporta `parkosFetch`, `parkosFetchRaw`, `ParkosHttpError`, `ParkosFetchInit`.

F3.2 importa `@parkos/ui-kit/hooks` (useAuth) + `@parkos/ui-kit/store` (useAuthStore) + `@parkos/ui-kit/fetch` (parkosFetch wrapper). NO modifica ui-kit exports (solo MODIFY `useAuth.ts` + `parkosFetch.ts` per T3).

---

## 3. Estado objetivo (TO-BE)

### 3.1 Tree delta (target)

```
apps/electron-sucursal/
├── src/
│   ├── features/auth/                            ← F3.1 baseline + F3.2 extienda in-place
│   │   ├── components/
│   │   │   ├── LoginForm.tsx                     ← MODIFY (+25 LOC — countdown display + form disabled)
│   │   │   └── LoginForm.test.tsx                ← MODIFY (+25 LOC — U8 + U9)
│   │   ├── hooks/                                ← NEW (T1)
│   │   │   ├── useCountdown.ts                   ← NEW (~40 LOC — Date.now baseline + setInterval + cleanup)
│   │   │   └── useCountdown.test.ts              ← NEW (~50 LOC — U1 + U2 + U3 + U4)
│   │   ├── pages/
│   │   │   ├── Login.tsx                         ← MODIFY (+10 LOC — useCountdown.isExpired reset errorState)
│   │   │   └── Login.test.tsx                    ← MODIFY (+15 LOC — U10)
│   │   └── api/                                  ← F3.1 baseline, no F3.2 touch
│   └── renderer/
│       └── i18n/locales/auth.json                ← MODIFY (+3 keys — lockoutCountdown + lockoutReEnable + lockoutLabel)
└── e2e/auth/
    └── lockout.spec.ts                           ← NEW (~80 LOC — E1 + E2 + E3 + A1)

apps/ui-kit/
├── src/
│   ├── fetch/
│   │   ├── parkosFetch.ts                        ← MODIFY (+20 LOC — pre-flight gate + PRE_FLIGHT_PATHS + PRE_FLIGHT_THRESHOLD_MS)
│   │   └── parkosFetch.test.ts                   ← MODIFY (+60 LOC — U5 + U6 + U7 + U8 + U9)
│   └── hooks/
│       ├── useAuth.ts                            ← MODIFY (line 60 — refreshInterval: 50min + REFRESH_INTERVAL_MS export)
│       └── useAuth.test.ts                       ← MODIFY (+10 LOC — REFRESH_INTERVAL_MS assertion)
```

### 3.2 useCountdown hook (target — NEW T1)

```typescript
// apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts (~40 LOC target)

import { useEffect, useState } from 'react';

export interface UseCountdownOptions {
  onComplete?: () => void;
}

export interface UseCountdownReturn {
  secondsLeft: number;
  isExpired: boolean;
}

/**
 * Hook countdown drift-resistant con Date.now() baseline (DEC-F3.2-01).
 *
 * NUNCA accumulator (`secondsLeft--`) — recalcula desde wall clock en cada
 * tick para resistir tab inactive + system sleep pauses que pausen setInterval.
 *
 * @param retryAfterSeconds  Segundos hasta re-habilitación (0 = expirado inmediato).
 * @param options.onComplete Callback opcional cuando secondsLeft llega a 0.
 */
export function useCountdown(
  retryAfterSeconds: number,
  options?: UseCountdownOptions,
): UseCountdownReturn {
  const endTime = Date.now() + retryAfterSeconds * 1000;
  const [secondsLeft, setSecondsLeft] = useState(() =>
    Math.max(0, Math.ceil((endTime - Date.now()) / 1000)),
  );
  const [isExpired, setIsExpired] = useState(secondsLeft === 0);

  useEffect(() => {
    if (isExpired) return;
    const id = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((endTime - Date.now()) / 1000));
      setSecondsLeft(remaining);
      if (remaining === 0) {
        setIsExpired(true);
        options?.onComplete?.();
        clearInterval(id);
      }
    }, 1000);
    return () => clearInterval(id);
  }, [endTime, isExpired, options]);

  return { secondsLeft, isExpired };
}
```

### 3.3 LoginForm countdown integration (target — MODIFY T2)

```typescript
// apps/electron-sucursal/src/features/auth/components/LoginForm.tsx (+25 LOC delta — solo countdown block)

import { useTranslation } from 'react-i18next';
import { useCountdown } from '../hooks/useCountdown';

export function LoginForm({ form, onSubmit, isSubmitting, error }: LoginFormProps): JSX.Element {
  const { t } = useTranslation('auth');
  const isLockout = error?.kind === 'lockout';
  const { secondsLeft, isExpired } = useCountdown(
    isLockout ? error.retryAfterSeconds : 0,
    { onComplete: undefined }, // parent handles reset via isExpired prop
  );

  const isFormDisabled = isSubmitting || (isLockout && !isExpired);

  // formatTime helper inline (~5 LOC)
  const formatTime = (sec: number): string => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

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
          data-testid="login-submit"
          aria-disabled={isFormDisabled}
        >
          {isSubmitting ? t('common:loading') : t('submit')}
        </Button>

        {/* Otros errores (invalid_credentials, network) */}
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
      </form>
    </Form>
  );
}
```

### 3.4 Login.tsx wiring (target — MODIFY T2)

```typescript
// apps/electron-sucursal/src/features/auth/pages/Login.tsx (+10 LOC delta — solo reset errorState)

import { useState } from 'react';
// ... F3.1 imports existentes ...

export function Login(): JSX.Element {
  // ... F3.1 state existente ...
  const [errorState, setErrorState] = useState<LoginErrorState>(null);

  // DEC-F3.1-07: esperar data.user antes de navigate (F3.1 verbatim)
  useEffect(() => {
    if (isAuthenticated && data?.user && !isLoading) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, data?.user, isLoading, navigate]);

  // F3.2 NUEVO: reset errorState cuando countdown llega a 0
  // Patrón: useEffect con side-effect externo vía callback en LoginForm.
  // Alternativa evaluada: pasar onCountdownExpired al LoginForm. DECIDIDA
  // la primera vía re-render del LoginForm con isExpired + useEffect local.
  // (Ver A.3 mockup completo para detalle.)

  // ... F3.1 onSubmit verbatim ...
}
```

---

## 4. Arquitectura de alto nivel

### 4.1 Vista de capas (ASCII)

```
┌───────────────────────────────────── Renderer (React 18 + SWR + Zustand + RHF + Zod) ──────────────────┐
│                                                                                                    │
│   <App> (F3.1, no F3.2 touch)                                                                      │
│   ├── <StatusBar />                                                                                │
│   └── <main>                                                                                       │
│       └── <Routes>                                                                                 │
│           └── <Route path="/login" element={<LoginPage />} />   (F3.1)                              │
│                                                                                                    │
│   <LoginPage>  (container, F3.1 + 10 LOC F3.2 T2)                                                   │
│   ├── useAuth() → { isAuthenticated, isLoading, data }                                             │
│   ├── useForm({ resolver: zodResolver(loginSchema) })                                              │
│   ├── useAuthStore.getState().setTokens(access, refresh, expires_in)                                │
│   ├── useEffect([isAuthenticated, data?.user, isLoading]) → navigate('/')                          │
│   ├── useEffect([errorState]) → reset cuando lockout expira ◄── NEW F3.2                            │
│   └── <LoginForm form={form} onSubmit error />                                                    │
│                                                                                                    │
│   <LoginForm>  (presentational, F3.1 + 25 LOC F3.2 T2)                                              │
│   ├── useCountdown(error.retryAfterSeconds) ◄── NEW F3.2 T1                                        │
│   │   → { secondsLeft, isExpired }                                                                 │
│   ├── formatTime(secondsLeft) → "mm:ss"                                                            │
│   ├── <Form>                                                                                       │
│   │   ├── <FormField name="email">  ──► Input disabled={isFormDisabled} ◄── F3.2                   │
│   │   ├── <FormField name="password"> ──► Input disabled={isFormDisabled} ◄── F3.2                │
│   │   ├── {isLockout && !isExpired &&                                                             │
│   │   │     <p role="status" aria-live="polite" data-testid="login-countdown">}   ◄── NEW F3.2     │
│   │   └── <Button type="submit" disabled={isFormDisabled} aria-disabled={isFormDisabled}>          │
│   └── {error.kind !== 'lockout' && <p role="alert">}                                               │
│                                                                                                    │
└─────────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                          │ POST /auth/login (HTTP, credentials:'include' F3.1)
                                          │ setTokens → useAuthStore.expiresAt (ISO 8601) → SWR key
                                          ▼
┌──────────────────────────────────── Main Process (Electron 30, IPC bridge F2.2+F2.3) ────────────────┐
│                                                                                                    │
│   bridge.authStore.{get,set,delete} ──► electron-store (persist JWT)                              │
│                                                                                                    │
└─────────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                          │ HTTPS (parkosFetch + pre-flight F3.2 + cookie auto-enviada)
                                          ▼
┌──────────────────────────────────── Backend FastAPI (HU-F1.2 + HU-F1.8 shipped) ─────────────────────┐
│                                                                                                    │
│   POST /api/v1/auth/login                                                                         │
│   ├── 200 OK ──► TokenPair + Set-Cookie parkos_session                                              │
│   ├── 401 ──► invalid_credentials (antienumeration, auth.py:188-191)                               │
│   └── 429 ──► Retry-After: <segundos> header (auth.py:219-228)                                     │
│                                                                                                    │
│   POST /api/v1/auth/refresh                                                                       │
│   └── 200 OK ──► TokenPair rotado (consumido por Mutex F2.2)                                       │
│                                                                                                    │
│   POST /api/v1/facturacion/*  ◄── PRE-FLIGHT GATE F3.2                                              │
│   POST /api/v1/caja/arqueo*   ◄── PRE-FLIGHT GATE F3.2                                              │
│                                                                                                    │
└─────────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                          │ parkosFetch pre-flight F3.2 si expiresAt < 5min
                                          ▼
┌──────────────────────────── ui-kit (apps/ui-kit/src/) ─────────────────────────────────────────────┐
│                                                                                                    │
│   parkosFetch.ts  (F2.2 + 20 LOC F3.2 T3)                                                          │
│   ├── PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/  ◄── NEW F3.2                        │
│   ├── PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000  ◄── NEW F3.2                                        │
│   ├── refreshIfExpiringSoon() ◄── NEW F3.2                                                         │
│   │   ├── check useAuthStore.expiresAt                                                             │
│   │   └── if (Date.parse(expiresAt) - Date.now() < 5min)                                           │
│   │         → await refreshAccessToken() (Mutex shared con handle401)                              │
│   └── parkosFetchRaw(url, init)                                                                    │
│       → [NEW] if (POST && matchPreFlight) await refreshIfExpiringSoon()                            │
│       → fetch(url, init)                                                                           │
│       → on 401 → handle401 → refreshAccessToken (Mutex)                                            │
│                                                                                                    │
│   useAuth.ts  (F2.2 + line 60 F3.2 T3)                                                              │
│   └── useSWR('/auth/me', parkosFetch, {                                                            │
│         refreshInterval: REFRESH_INTERVAL_MS = 50 * 60 * 1000  ◄── F3.2 CAMBIO 5min → 50min      │
│         revalidateOnFocus: true,                                                                   │
│         dedupingInterval: 2000,                                                                    │
│       })                                                                                           │
│                                                                                                    │
│   authStore.ts  (F2.2 READ-ONLY, F3.2 consume)                                                     │
│   ├── accessToken / refreshToken / expiresAt (ISO 8601)                                           │
│   ├── setTokens(access, refresh, expiresIn) → atomic update                                        │
│   ├── clear() → all 3 → null                                                                       │
│   └── refreshAccessToken() ──► Mutex singleton (F2.2 DEC-FETCH-03)                                │
│                                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Principios arquitectónicos

1. **Hook reusable primero** (DEC-F3.2-01): `useCountdown(retryAfterSeconds, options?)` retorna `{ secondsLeft, isExpired }`. Drift-resistant via `Date.now()` baseline + recalc per tick. NO accumulator. Cleanup en `useEffect` return. `onComplete` callback fires at 0. Exportable cross-feature.
2. **Container/Presentational split preservado** (F3.1 DEC-F3.1-02): `<LoginPage>` container agrega useEffect para reset `errorState` cuando lockout expira; `<LoginForm>` presentational consume `useCountdown` y renderiza UI. Side-effects en container, presentación pura en form.
3. **`Date.now()` baseline + recalc per tick** (DEC-F3.2-01, R1 mitigation): `endTime = Date.now() + retryAfterSeconds * 1000`. Cada tick recalcula `secondsLeft` desde wall clock. NO accumulator (`secondsLeft--`) porque browser throttle puede pausar `setInterval` cuando tab inactive.
4. **Mutex singleton preserved** (F2.2 DEC-FETCH-03 invariant): pre-flight gate REUSA `refreshAccessToken()` Mutex compartido con `handle401`. N concurrentes callers (pre-flight + 401) comparten UNA promesa. Cero doble refresh race (R2 mitigation).
5. **Pre-flight condicional on path** (DEC-F3.2-03, R5 mitigation): regex `PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/` compila módulo-level. Pre-flight solo POST críticos (latency budget ≤200ms — DEC-F3.2-07). GET requests NO triggerean pre-flight (handle401 cubre).
6. **`role="status"` + `aria-live="polite"`** (DEC-F3.2-05, R6 mitigation): countdown accesible WCAG 2.1 AA. NO `aria-live="assertive"` (interruptivo). `aria-label={t('lockoutLabel')}` describe el countdown para screen readers.
7. **Constants exportadas para testabilidad** (DEC-F3.2-04 + DEC-F3.2-07): `REFRESH_INTERVAL_MS = 50 * 60 * 1000`, `PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000`, `PRE_FLIGHT_PATHS` regex módulo-level. Tests deterministas sin magic numbers.
8. **Forward extensibility** (DEC-F3.2-10): `PRE_FLIGHT_PATHS` permite extender via nueva constante o env var. F3.3+ (turno) puede agregar `/caja-sesion/*` si lo requiere. Cero cambios a callers.

---

## 5. Decisiones arquitectónicas (DEC-F3.2-NN × 11)

Cross-ref `proposal.md` §4 + `exploration.md` §7. Tabla resumen con anclas a las justificaciones extendidas.

| ID | Title | Choice | Rationale | Alternativas rechazadas | Anchor |
|---|---|---|---|---|---|
| **DEC-F3.2-01** | `useCountdown` signature: `Date.now()` baseline (NO accumulator) | `useCountdown(retryAfterSeconds, options?): { secondsLeft, isExpired }`. `endTime = Date.now() + retryAfterSeconds * 1000` + recalc per tick. | Drift-resistant: browser throttle `setInterval` aggressively cuando tab inactive → accumulator queda atrasado. `Date.now()` siempre recomputa desde wall clock. R1 mitigation. | (a) Accumulator `secondsLeft--` — RECHAZADA (drift risk); (b) `requestAnimationFrame` — RECHAZADA (over-engineering, no benefit vs setInterval) | proposal §4.1, exploration §7 |
| **DEC-F3.2-02** | Countdown UX: form `disabled` (NOT readonly) | `<Input>` + `<Button type="submit">` con `disabled={true}` + `aria-disabled="true"` mientras `secondsLeft > 0`. Countdown display ARRIBA del form. | `disabled` previene submit + typing. `readonly` permite typing pero no submit — UX confuso. `aria-disabled` anuncia estado a screen readers. R6 mitigation. | (a) `readonly` — RECHAZADA (UX inconsistente); (b) sin disable — RECHAZADA (operador puede reintentar y recibir 429 inmediato) | proposal §4.2, exploration §7 |
| **DEC-F3.2-03** | Pre-flight trigger: conditional on path (regex match) | Pre-flight solo si `method === 'POST'` AND `url.match(PRE_FLIGHT_PATHS)` AND `expiresAt !== null` AND `Date.parse(expiresAt) - Date.now() < PRE_FLIGHT_THRESHOLD_MS`. Constante módulo-level `PRE_FLIGHT_PATHS = /\/facturacion(\/\|$)\|\/caja\/arqueo/`. | Pre-flight tiene latency cost (~50-150ms). Aplicarlo a TODOS los POST degrada UX. Solo críticos DEC-SUC-03 (pago + arqueo). Regex single source of truth. R5 mitigation. | (a) Pre-flight en TODOS los POST — RECHAZADA (latency overhead innecesario); (b) per-endpoint config (decorator) — RECHAZADA (boilerplate + drift risk); (c) env var — RECHAZADA (regex simple > configurability para 2 paths) | proposal §4.3, exploration §7 |
| **DEC-F3.2-04** | SWR refresh interval: 50min hardcoded (constante exportada) | `useAuth.ts:60` `refreshInterval: 5 * 60 * 1000 → REFRESH_INTERVAL_MS = 50 * 60 * 1000`. Constante módulo-level exportada para testabilidad. | DEC-SUC-03 verbatim (plan.md:418). 50min deja 10min safety margin vs `ACCESS_TOKEN_TTL=3600` (auth.py:71). 5min baseline (F2.2) es 12x/hora bandwidth waste. | (a) Mantener 5min — RECHAZADA (12x bandwidth waste vs DEC-SUC-03); (b) Hardcoded 50min sin constante — RECHAZADA (magic number + tests brittle) | proposal §4.4, exploration §7 |
| **DEC-F3.2-05** | e2e axe-core scope: countdown state WCAG check | `e2e/auth/lockout.spec.ts` A1 test verifica axe-core 0 violaciones durante countdown state (form disabled + `<p role="status" aria-live="polite">`). `withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])` mismo F3.1 pattern. | REQ-OPS-112 (F3.1) + RNF-022 WCAG 2.1 AA. Countdown display debe pasar axe-core scan. A1 corre post-countdown-render (mock 429 + Retry-After). R6 mitigation. | (a) Axe-core check solo en form (sin countdown) — RECHAZADA (RNF-022 cubre TODO state); (b) Axe-core check pre-countdown — RECHAZADA (estado menos crítico) | proposal §4.5, exploration §7 |
| **DEC-F3.2-06** | Countdown i18n keys: 3 keys en `auth.json` | `lockoutCountdown` ("Reintento disponible en {{time}}"), `lockoutReEnable` ("El formulario se ha reactivado..."), `lockoutLabel` ("Tiempo restante: {{time}}" aria-label). Namespace `auth` existente, NO nuevo namespace. | F2.1 DEC-ELEC-06 — un namespace por bounded context. `lockout` key ya en `auth.json` line 8 — countdown keys son extensión natural. `{{time}}` i18next interpolation XSS-safe. | (a) Nuevo namespace `auth.countdown` — RECHAZADA (DEC-ELEC-06 verbatim + boilerplate); (b) countdown numérico hardcoded — RECHAZADA (no i18n) | proposal §4.6, exploration §7 |
| **DEC-F3.2-07** | Pre-flight latency budget: ≤200ms con graceful degradation | `refreshIfExpiringSoon` budget ≤200ms p95. Si refresh falla o tarda, request continúa con token existente. `handle401` retry cubre 401 post-refresh. | UX crítica para kiosko desatendido. POST `/facturacion` esperando >200ms degrada perceived performance. Soft target + fallback reactivo. R5 mitigation. | (a) Sin budget — RECHAZADA (UX risk si refresh cuelga); (b) Hard fail si >200ms — RECHAZADA (rompe UX innecesariamente, handle401 cubre) | proposal §4.7, exploration §7 |
| **DEC-F3.2-08** | DELTA verdict (NOT NO-OP) — F3.2 IS user-facing | F3.2 emite DELTA spec con 6 new REQ-OPS-113..118 (numbered post-F3.1 REQ-OPS-106..112). Spec delta materializes en `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md`. | F3.2 ES user-facing: (a) countdown visual decreciente cada 1000ms; (b) form disabled durante lockout; (c) pre-flight evita 401 mid-write; (d) refresh 50min observable. Per F1.15 + F3.1 precedent, user-facing ⇒ spec delta. | (a) NO-OP stub precedent F2.x (DEC-ELEC-10/FETCH-10/UPD-13) — RECHAZADA (F2.x infra-only); (b) DELTA con 4 new REQ-OPS — RECHAZADA (cobertura insuficiente, 6 balancean audit + overload) | proposal §4.8, exploration §7 |
| **DEC-F3.2-09** | e2e lockout attempts: configurable via env (default 4) | `e2e/auth/lockout.spec.ts` E1 hace `max_intentos_login - 1` intentos fallidos + 1 que recibe 429. Default e2e usa `MAX_INTENTOS_LOGIN = 4` (rápido). Backend configurable via `configuracion_seguridad.max_intentos_login` (default 5 per `auth.py:225`). | Test rápido (4 vs 5) sin sacrificar coverage. Verifica FLOW (intentos → 429 → countdown), no número EXACTO. MSW/page.route mockea 429 después de N intentos. Resuelve I1 (plan.md:1309 "5 intentos" vs orchestrator "4 attempts"). | (a) Hardcoded 5 — RECHAZADA (test lento + brittle); (b) Hardcoded 4 — RECHAZADA (no respeta backend config en CI) | proposal §4.9, exploration §7 |
| **DEC-F3.2-10** | Forward hook: pre-flight paths extensibilidad | `PRE_FLIGHT_PATHS` constante módulo-level permite extensión future via `PRE_FLIGHT_PATHS_EXTENDED` o env var. F3.2 cubre `/facturacion/*` + `/caja/arqueo*` per DEC-SUC-03. F3.3+ puede extender a `/caja-sesion/*`. | YAGNI — F3.2 NO incluye `/caja-sesion/*` (F3.3 decidirá). Constante extensibility-friendly. Resuelve I3 (`/caja/arqueo` no existe todavía — Fase 10 introduce arqueos). | (a) Paths hardcoded en sitio — RECHAZADA (forward compatibility viola DRY); (b) Múltiples regex por endpoint — RECHAZADA (boilerplate) | proposal §4.10, exploration §7 |
| **DEC-F3.2-11** | Spec delta a `operations/spec.md` con 6 new REQ-OPS-113..118 (DELTA, NO NO-OP) | `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md` AGREGA 6 new REQ-OPS-113..118 al spec canónico. Given/When/Then/And RFC 2119 format. | F3.2 ES user-facing behavior observable. Precedent F1.15 (4 new REQ-OPS-102..105) + F3.1 (7 new REQ-OPS-106..112). F2.x NO-OP precedent NO aplica. Numeración monotónica: 112 → 113..118 (0 gaps). | (a) NO-OP stub — RECHAZADA tras re-evaluación (F2.x infra-only; F3.2 user-facing); (b) DELTA con 4 REQ-OPS — RECHAZADA (cobertura insuficiente) | proposal §4.11, exploration §12.1 |

---

## 6. Componentes y contratos (TS interfaces)

### 6.1 `UseCountdownOptions` + `UseCountdownReturn` (hook types)

```typescript
// apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts (~40 LOC)

export interface UseCountdownOptions {
  /**
   * Callback opcional invocado cuando secondsLeft llega a 0.
   * Útil para reset external state (e.g., errorState en LoginPage).
   */
  onComplete?: () => void;
}

export interface UseCountdownReturn {
  /** Segundos restantes hasta expiración. 0 = expirado. */
  secondsLeft: number;
  /** True si countdown llegó a 0 (form puede re-habilitarse). */
  isExpired: boolean;
}
```

### 6.2 `LoginErrorState` (extensión F3.1 — sin cambios)

```typescript
// apps/electron-sucursal/src/features/auth/components/LoginForm.tsx (F3.1 verbatim, F3.2 consume)

export type LoginErrorState =
  | { kind: 'invalid_credentials' }
  | { kind: 'lockout'; retryAfterSeconds: number }  // F3.2 useCountdown consume retryAfterSeconds
  | { kind: 'network' }
  | null;
```

### 6.3 `formatTime` helper (NEW inline, ~5 LOC)

```typescript
// apps/electron-sucursal/src/features/auth/components/LoginForm.tsx (NEW F3.2, helper inline)

/**
 * Convierte segundos a formato mm:ss.
 * 600s → "10:00". 47s → "00:47". 3600s → "60:00" (1h display).
 */
function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
```

### 6.4 Constantes módulo-level (exportadas para testabilidad)

```typescript
// apps/ui-kit/src/fetch/parkosFetch.ts (NEW F3.2)

/** Paths críticos que triggerean pre-flight refresh gate. */
export const PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/;

/** Umbral de expiración en ms para invocar pre-flight (5min antes de TTL). */
export const PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000;
```

```typescript
// apps/ui-kit/src/hooks/useAuth.ts (NEW F3.2, exportada)

/** Intervalo SWR refresh en ms (50min). DEC-SUC-03 verbatim. */
export const REFRESH_INTERVAL_MS = 50 * 60 * 1000;
```

---

## 7. parkosFetch.ts pre-flight gate

Cross-ref `proposal.md` §6.4 + `exploration.md` §2.1.

### 7.1 `refreshIfExpiringSoon` (internal function)

```typescript
// apps/ui-kit/src/fetch/parkosFetch.ts (NEW F3.2, internal)

import { useAuthStore } from '@parkos/ui-kit/store';

/**
 * Refresh proactivo del access_token si está por expirar (<5min).
 * Reusa refreshAccessToken Mutex (F2.2 DEC-FETCH-03 invariant).
 * No-op si expiresAt es null (pre-login).
 */
async function refreshIfExpiringSoon(): Promise<void> {
  const { expiresAt, refreshAccessToken } = useAuthStore.getState();
  if (expiresAt === null) return;
  const msUntilExpiry = Date.parse(expiresAt) - Date.now();
  if (msUntilExpiry < PRE_FLIGHT_THRESHOLD_MS) {
    // Mutex shared con handle401 — si 401 caller también triggerea,
    // ambos comparten UNA promesa (R2 mitigation).
    await refreshAccessToken();
  }
}
```

### 7.2 Integración en `parkosFetchRaw` (modificación pre-fetch)

```typescript
// apps/ui-kit/src/fetch/parkosFetch.ts (MODIFY F3.2, +20 LOC delta)

export async function parkosFetchRaw<T = unknown>(
  url: string,
  init: ParkosFetchInit = {},
): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const isPreFlightCandidate = method === 'POST' && PRE_FLIGHT_PATHS.test(url);

  // DEC-F3.2-03: pre-flight gate solo para POST críticos.
  if (isPreFlightCandidate) {
    await refreshIfExpiringSoon();
  }

  const res = await fetch(url, { ...init, credentials: 'include' });

  if (res.status === 401) {
    // F2.2 handle401 Mutex preserved (DEC-FETCH-03)
    return handle401<T>(url, init);
  }

  if (!res.ok) {
    throw new ParkosHttpError(res.status, await res.text().catch(() => ''), res.url);
  }

  return (await res.json()) as T;
}
```

### 7.3 Constante regex compilación

- `PRE_FLIGHT_PATHS` se compila UNA VEZ en módulo-level (NO recompilada per request).
- Pattern match: `/facturacion` seguido de `/` o end-of-string, O `/caja/arqueo` en cualquier posición.
- Test: `/\/facturacion(\/|$)|\/caja\/arqueo/.test('/api/v1/facturacion/pagos')` → `true`.
- Negative test: `/\/facturacion(\/|$)|\/caja\/arqueo/.test('/api/v1/catalogos')` → `false`.

---

## 8. State management

Cross-ref `proposal.md` §8 + `exploration.md` §2.4 + F3.1 §8.

### 8.1 `useAuthStore` state shape (F2.2 verbatim, F3.2 consume)

```typescript
// apps/ui-kit/src/store/authStore.ts (F2.2 READ-ONLY, F3.2 consume expiresAt)

export interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: string | null;  // ISO 8601 UTC
  setTokens: (access: string, refresh: string, expiresIn: number) => void;
  clear: () => void;
  refreshAccessToken: () => Promise<void>;  // Mutex singleton
}
```

### 8.2 Pre-flight proximity check (F3.2 nuevo)

```typescript
// Pseudocódigo del gate (F3.2 implementación §7.1)
const expiresAt = useAuthStore.getState().expiresAt;
if (expiresAt === null) return; // pre-login, no refresh
const msUntilExpiry = Date.parse(expiresAt) - Date.now();
if (msUntilExpiry < PRE_FLIGHT_THRESHOLD_MS) {
  await useAuthStore.getState().refreshAccessToken(); // Mutex shared
}
```

- `Date.parse(expiresAt)` retorna timestamp en ms (ISO 8601 UTC es parseable nativamente).
- `PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000` = 300_000ms = 5min.
- Refresh solo se triggerea si faltan <5min para expirar. Si faltan >5min, request viaja con token actual (sin overhead).

### 8.3 `useCountdown` local state (NEW F3.2)

```typescript
// apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts (NEW F3.2 T1)

const endTime = Date.now() + retryAfterSeconds * 1000;
const [secondsLeft, setSecondsLeft] = useState(() =>
  Math.max(0, Math.ceil((endTime - Date.now()) / 1000)),
);
const [isExpired, setIsExpired] = useState(secondsLeft === 0);
```

- `endTime` se calcula UNA VEZ en mount (baseline wall clock).
- `secondsLeft` se inicializa con el valor correcto al primer render.
- `isExpired` se inicializa como `true` si `retryAfterSeconds === 0` (R7 mitigation: `parseRetryAfter` fallback a 0 → form re-enabled inmediato).
- `useEffect` setInterval cleanup en unmount (R4 mitigation).

### 8.4 `useAuth` SWR refresh interval (F3.2 MODIFY line 60)

```typescript
// apps/ui-kit/src/hooks/useAuth.ts (MODIFY F3.2 T3, line 60)

useSWR<AuthMeResponse>(
  accessToken ? '/auth/me' : null,
  parkosFetch,
  {
    refreshInterval: REFRESH_INTERVAL_MS,  // F3.2: 5min → 50min (DEC-F3.2-04)
    revalidateOnFocus: true,
    dedupingInterval: 2000,
    onError: (err) => {
      if (err instanceof ParkosHttpError && err.status === 401) {
        useAuthStore.getState().clear();
        window.dispatchEvent(new Event('parkos:auth:cleared'));
      }
    },
  }
);
```

- `REFRESH_INTERVAL_MS = 50 * 60 * 1000` constante exportada.
- SWR revalida `/auth/me` cada 50min post-login. 10min safety margin vs TTL 3600s.
- `onError` 401 preserved (F2.2 invariant — `parkos:auth:cleared` event).

### 8.5 Local form state (RHF, NO authStore)

- `Login.tsx` mantiene form state local via `useForm<LoginInput>`. NO persiste a `authStore`.
- `errorState` local (`useState<LoginErrorState | null>`) — se resetea cuando `useCountdown.isExpired === true` (F3.2).
- Form state ephemeral (vive solo durante lockout active). Post-unmount, state GC'd.

---

## 9. Manejo de errores (cross-layer)

Cross-ref `proposal.md` §9 + `exploration.md` §7 R1..R8.

### 9.1 Matriz de errores F3.2

| Origen | Status / Tipo | Error class | UI behavior | Anchor |
|---|---|---|---|---|
| Backend | 429 account_locked + Retry-After | `AccountLockedError(retryAfterSeconds)` | `<p role="status">` countdown + form disabled + auto re-enable | DEC-F3.2-02 |
| Backend | 429 sin Retry-After (anomaly) | `AccountLockedError(0)` | `useCountdown(0)` → isExpired inmediato → form re-enabled, sin countdown display | R7 mitigation |
| Pre-flight | Refresh failure (network) | (Promise rejects silently — no error thrown al caller) | Request continúa con token existente; handle401 cubre 401 post | DEC-F3.2-07 graceful degradation |
| Pre-flight | Refresh timeout (>200ms) | (NO hard fail — soft budget) | Request continúa con token existente | DEC-F3.2-07 |
| useCountdown | Unmount mid-countdown | (cleanup `clearInterval`) | Sin late callback; no memory leak | R4 mitigation |
| useCountdown | Tab inactive + sleep (drift) | (recalc per tick via Date.now) | Countdown siempre correcto vs wall clock | R1 mitigation |

### 9.2 Comportamiento `useEffect` reset errorState

```typescript
// apps/electron-sucursal/src/features/auth/pages/Login.tsx (F3.2 NUEVO useEffect)

useEffect(() => {
  if (errorState?.kind === 'lockout' && /* useCountdown.isExpired signal */) {
    setErrorState(null);
  }
}, [errorState]);
```

El signal de `isExpired` se pasa vía callback prop del `LoginForm` al container. Patrón:

1. `<LoginForm>` invoca `useCountdown(retryAfterSeconds, { onComplete: () => onLockoutExpired?.() })`.
2. `onLockoutExpired` callback prop se pasa desde `<LoginPage>`.
3. `<LoginPage>` setea `errorState` a `null` cuando callback fires.

Alternativa evaluada: `useCountdown` con `isExpired` retornado al `<LoginForm>` y propagado al container via `forwardRef` o props de lectura. DECIDIDA callback prop (más directo, sin re-render cross-component).

### 9.3 Comportamiento `handle401` Mutex shared con pre-flight

```
t=0    POST /facturacion dispatched
t=10ms Pre-flight check: expiresAt - now = 4min (<5min)
t=15ms refreshAccessToken() initiated (Mutex acquired, promise P1)
t=20ms POST /facturacion fetch awaits
t=170ms refreshAccessToken() resolves (P1 resolved)
t=175ms POST /facturacion fetch proceeds with fresh token
t=225ms Backend returns 200 OK

Alternative scenario (concurrent 401):
t=0    POST /catalogos dispatched (no pre-flight)
t=10ms fetch returns 401
t=15ms handle401 calls refreshAccessToken() → Mutex sees P1 already in-flight
t=15ms handle401 awaits P1 (same promise)
t=170ms P1 resolved
t=175ms handle401 retries POST /catalogos with fresh token
```

**Invariant**: N concurrentes callers (pre-flight + 401) comparten UNA promesa Mutex. Cero doble refresh (R2 mitigation).

### 9.4 429 sin Retry-After fallback

`parseRetryAfter` (F3.1 loginApi.ts:59-63) retorna `0` si header falta:

```typescript
const parsed = retryAfterHeader !== null ? Number(retryAfterHeader) : NaN;
const retryAfterSeconds = Number.isFinite(parsed) ? parsed : 0;
throw new AccountLockedError(retryAfterSeconds);
```

`useCountdown(0)` retorna `{ secondsLeft: 0, isExpired: true }` → form re-enabled inmediato sin countdown display. UX: operador ve `t('lockout')` ("Cuenta bloqueada temporalmente.") sin tiempo numérico (R7 mitigation).

---

## 10. Seguridad (cross-layer)

Cross-ref `proposal.md` §10 + `exploration.md` §13.

### 10.1 Defense in depth (5 capas, F3.2 contribution)

| Layer | Mechanism | Source | F3.2 contribution |
|---|---|---|---|
| 1 auth | JWT Bearer (F2.2) + cookie httpOnly SameSite=Lax (F1.2) + bcrypt (F1.2) | `useAuth.ts` + `loginApi.ts` + backend `auth.py` | NO custom auth (heredado) |
| 2 engineering | TS strict + noUncheckedIndexedAccess + ESLint flat (F2.1) | tsconfig.* + eslint.config.js | `useCountdown.ts` + `useAuth.ts` (50min) + `parkosFetch.ts` (pre-flight) heredan |
| 3 a11y | axe-core WCAG 2.1 AA (RNF-022) + FormField aria-invalid + FormMessage role=alert + `<p role="status" aria-live="polite">` countdown | `@axe-core/playwright` + shadcn `form.tsx` + F3.2 countdown | ADD axe-core A1 test countdown state |
| 4 contract | Zod local form (F3.1) + backend Pydantic (F1.2) + 6 new REQ-OPS-113..118 (DEC-F3.2-11) | `@hookform/resolvers/zod` + `schemas/auth.py` + `operations/spec.md` delta | ADD 6 new REQ-OPS-113..118 al spec canónico |
| 5 retry-budget | parkosFetch retry 5xx + 401 refresh-once (F2.2) + pre-flight gate (F3.2) | parkosFetch.ts + DEC-FETCH-02/03 | ADD pre-flight gate proactivo |

### 10.2 Mutex singleton preserved (R2 mitigation)

- Pre-flight gate REUSA `refreshAccessToken()` Mutex (F2.2 authStore.ts:100-128).
- Si 401 caller llega mid-pre-flight, ambos comparten UNA promesa.
- Cero riesgo de doble refresh race.
- Si refresh HTTP falla (network/5xx), Mutex rejects una vez — todos los awaiters reciben el mismo rejection. handle401 caller ya tiene su propio retry logic.

### 10.3 Cookie round-trip preservado (F3.1 invariant)

- `credentials:'include'` (F3.1 DEC-F3.1-03) en login + `parkosFetch` auto-envía cookie en subsecuentes requests.
- `HttpOnly` flag blinda cookie vs XSS (`document.cookie` no expone `parkos_session`).
- `SameSite=Lax` bloquea cross-site form submissions (CSRF mitigation).
- F3.2 NO modifica cookie handling — pre-flight triggerea refresh HTTP puro (NO IPC, NO cookie manipulation).

### 10.4 i18n template interpolation XSS-safe (R10 mitigation)

```typescript
t('lockoutCountdown', { time: formatTime(secondsLeft) })
// → "Reintento disponible en 09:47"
```

`i18next` interpola `{{time}}` con valores sanitizados automáticamente. `formatTime` retorna string numérico (`mm:ss`) — sin user input. XSS-safe por construcción.

### 10.5 No exposure de retryAfter en URL params (R11)

- `retryAfterSeconds` se pasa vía state local (`useState<LoginErrorState>`), NO URL query param.
- Evita history leak (browser history, server logs) del tiempo de bloqueo.
- Atacante no puede inferir política de `minutos_bloqueo_login` observando URLs.

### 10.6 Atomic state updates (F2.2 invariant preserved)

`setTokens(access, refresh, expiresIn)` actualiza 3 keys simultáneamente en Zustand `set` síncrono. NO race condition entre `setTokens` y pre-flight gate (que lee `expiresAt`). Pre-flight gate SIEMPRE lee el último `expiresAt` consistente.

---

## 11. Accesibilidad WCAG 2.1 AA (RNF-022)

Cross-ref `proposal.md` §4.5 + RNF-022 (`docs/01-requisitos/no-funcionales.md:126`) + DEC-F3.2-05.

### 11.1 Cobertura axe-core countdown state

`LoginForm.tsx` durante countdown debe pasar axe-core scan con 0 violaciones. Cobertura específica:

| Criterio WCAG 2.1 AA | Implementación | Test |
|---|---|---|
| 1.3.1 Info and Relationships | `<FormLabel htmlFor>` + `<FormControl id>` asociados via `useFormField()` (shadcn `form.tsx`) | axe-core auto-detect |
| 1.4.3 Contrast (Minimum) | shadcn tokens + countdown display color (NO `text-destructive` durante countdown — mensaje neutral) | axe-core auto-detect |
| 3.3.1 Error Identification | `<FormMessage role="alert">` con Zod errors + `<p role="status" aria-live="polite">` countdown | axe-core + vitest `getByRole('alert')` + `getByRole('status')` |
| 3.3.2 Labels or Instructions | `<FormLabel>` con texto `t('email')` / `t('password')` | axe-core auto-detect |
| 4.1.2 Name, Role, Value | `aria-invalid={!!error}` en `<FormControl>` + `aria-disabled={isFormDisabled}` en `<Button>` | axe-core auto-detect |
| 4.1.3 Status Messages | `<p role="status" aria-live="polite">` countdown anuncia cambios sin interrumpir | axe-core auto-detect + e2e A1 |
| 2.1.1 Keyboard | Tab order secuencial: email → password → submit. Form disabled: tab focus skips disabled inputs | vitest `userEvent.tab()` |
| 2.4.7 Focus Visible | shadcn `Input` tiene focus ring via `focus-visible:ring-2` | axe-core + manual |

### 11.2 `aria-live="polite"` pattern (R6 mitigation)

```tsx
<p
  role="status"
  aria-live="polite"
  aria-label={t('lockoutLabel', { time: formatTime(secondsLeft) })}
  data-testid="login-countdown"
>
  {t('lockoutCountdown', { time: formatTime(secondsLeft) })}
</p>
```

- `aria-live="polite"` anuncia cambios cuando el screen reader idle (NO interruptivo).
- NO `aria-live="assertive"` — countdown NO debe interrumpir al operador en otra tarea.
- Frecuencia de actualización visual: cada 1000ms (UX). Frecuencia de anuncio: SR anuncia al inicio + al final (~30s si display es estable, más rápido si display cambia).
- `aria-label` describe contexto completo ("Tiempo restante para reintentar: 09:47") — SR anuncia el tiempo restante explícitamente.

### 11.3 `aria-disabled` pattern

```tsx
<Button
  type="submit"
  disabled={isFormDisabled}
  aria-disabled={isFormDisabled}
  data-testid="login-submit"
>
```

- `disabled` HTML attr previene submit + visual greyed-out.
- `aria-disabled` anuncia estado a screen readers (algunos SR no leen `disabled` consistentemente).
- axe-core valida `aria-disabled` válido + `disabled` prop coherente.

### 11.4 axe-core e2e test

```typescript
// apps/electron-sucursal/e2e/auth/lockout.spec.ts (NEW F3.2 T4, A1 test)

test('A1 — axe-core WCAG 2.1 AA en countdown state', async ({ page }) => {
  // Setup: mock 429 + Retry-After después de 1 intento
  await page.route('**/api/v1/auth/login', (route) =>
    route.fulfill({
      status: 429,
      headers: { 'Retry-After': '300' },
      body: JSON.stringify({ error: 'account_locked' }),
    }),
  );

  await page.goto('/login');
  await page.getByTestId('login-email').fill('op@sucursal.parkos.local');
  await page.getByTestId('login-password').fill('valid-password-1234');
  await page.getByTestId('login-submit').click();

  // Esperar countdown display
  await expect(page.getByTestId('login-countdown')).toBeVisible();

  // Axe-core scan
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
```

---

## 12. i18n strategy

Cross-ref `proposal.md` §4.6 + DEC-F3.2-06.

### 12.1 Namespace `auth` (F2.1 baseline + F3.1 + F3.2 delta)

```json
// apps/electron-sucursal/src/renderer/i18n/locales/auth.json (F3.2 MODIFY — +3 keys)

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
  "lockoutCountdown": "Reintento disponible en {{time}}",
  "lockoutReEnable": "El formulario se ha reactivado. Puedes intentar de nuevo.",
  "lockoutLabel": "Tiempo restante para reintentar: {{time}}",
  "validation": {
    "required": "Este campo es obligatorio",
    "email": { "invalid": "Ingresa un correo válido" },
    "password": {
      "minLength": "La contraseña debe tener al menos 8 caracteres",
      "required": "Ingresa tu contraseña"
    }
  }
}
```

### 12.2 Convenciones

- Un namespace por bounded context (DEC-F3.2-06, F2.1 DEC-ELEC-06). Login = `auth`. NO `auth.countdown` (namespace plano).
- Keys en `camelCase`. Mensajes en español neutro profesional.
- `{{time}}` i18next interpolation XSS-safe (R10 mitigation).
- 3 keys countdown: `lockoutCountdown` (visible text), `lockoutReEnable` (notice post-countdown), `lockoutLabel` (aria-label descriptivo).
- Forward: si F4.x retry buttons consumen `useCountdown`, agregar keys al namespace relevante (`facturacion`, `catalogos`).

---

## 13. Estrategia de testing

Cross-ref `proposal.md` §9 G1..G6 + exploration §10.

### 13.1 Vitest unit (mockeando fetch global + timers)

**`apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts`** (NEW F3.2 T1, ~50 LOC, 4 tests):

| # | Escenario | Aserción clave |
|---|---|---|
| U1 | Baseline `Date.now()` retorna `retryAfterSeconds` inmediatamente | `renderHook(() => useCountdown(60))` → `expect(secondsLeft).toBe(60); expect(isExpired).toBe(false)` |
| U2 | Cleanup on unmount — no callback fires post-unmount | `vi.useFakeTimers() + onComplete=vi.fn() + unmount() + advanceTimersByTime(3000)` → `expect(onComplete).not.toHaveBeenCalled()` |
| U3 | `onComplete` fires cuando llega a 0 | `vi.advanceTimersByTime(2000)` con `retryAfterSeconds=2` → `expect(isExpired).toBe(true); expect(onComplete).toHaveBeenCalledOnce()` |
| U4 | Drift resistance via `Date.now()` baseline | `vi.advanceTimersByTime(2000)` con `retryAfterSeconds=60` → `expect(secondsLeft).toBe(58)` (decrementa 2, no 1) |

**`apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx`** (MODIFY F3.2 T2, +25 LOC, 2 tests nuevos):

| # | Escenario | Aserción clave |
|---|---|---|
| U8 | Lockout deshabilita form (mock useCountdown con secondsLeft=300, isExpired=false) | `expect(inputEmail).toBeDisabled(); expect(inputPassword).toBeDisabled(); expect(buttonSubmit).toBeDisabled(); expect(buttonSubmit).toHaveAttribute('aria-disabled', 'true')` |
| U9 | Countdown display visible durante lockout | `expect(screen.getByTestId('login-countdown')).toBeVisible(); expect(text).toMatch(/\d{2}:\d{2}/)` |

**`apps/electron-sucursal/src/features/auth/pages/Login.test.tsx`** (MODIFY F3.2 T2, +15 LOC, 1 test nuevo):

| # | Escenario | Aserción clave |
|---|---|---|
| U10 | `useCountdown.isExpired` resetea `errorState` | mock 429 con `Retry-After: 2` + `vi.useFakeTimers() + vi.advanceTimersByTime(3000)` → `expect(errorState).toBeNull()` post-isExpired |

**`apps/ui-kit/src/hooks/useAuth.test.ts`** (MODIFY F3.2 T3, +10 LOC, 1 test nuevo):

| # | Escenario | Aserción clave |
|---|---|---|
| U11 | `REFRESH_INTERVAL_MS === 50 * 60 * 1000` constante exportada | `import { REFRESH_INTERVAL_MS } from './useAuth'; expect(REFRESH_INTERVAL_MS).toBe(3_000_000)` |

**`apps/ui-kit/src/fetch/parkosFetch.test.ts`** (MODIFY F3.2 T3, +60 LOC, 5 tests nuevos):

| # | Escenario | Aserción clave |
|---|---|---|
| U12 | Pre-flight fires cuando `expiresAt < 5min` + POST `/facturacion/*` | mock expiresAt ISO 8601 con offset -4min + mock fetch POST + spy `useAuthStore.refreshAccessToken` → `expect(refreshAccessToken).toHaveBeenCalledOnce()` |
| U13 | Pre-flight skips cuando `expiresAt > 5min` | mock expiresAt con offset -10min + POST `/facturacion/*` → `expect(refreshAccessToken).not.toHaveBeenCalled()` |
| U14 | GET request no triggerea pre-flight | mock expiresAt -4min + GET `/catalogos` → `expect(refreshAccessToken).not.toHaveBeenCalled()` |
| U15 | Pre-flight failure NO bloquea request (graceful degradation) | mock `refreshAccessToken` reject + POST `/facturacion/*` → fetch called + request succeeds |
| U16 | Pre-flight Mutex shared con 401 path | concurrent pre-flight + 401 caller → UNA sola llamada a `refreshAccessToken` (spy count = 1) |

### 13.2 Playwright e2e (`_electron.launch`)

**`apps/electron-sucursal/e2e/auth/lockout.spec.ts`** (NEW F3.2 T4, ~80 LOC, 4 scenarios):

| # | Escenario |
|---|---|
| E1 | **countdown-display**: 4 intentos fallidos (mock 429 después de N) → assert `data-testid="login-countdown"` visible + texto `/\d{2}:\d{2}/` + form disabled |
| E2 | **countdown-decrements**: countdown display decrece cada ~1000ms vía polling assertion |
| E3 | **countdown-re-enable**: mock countdown 2s + advance fake timers + assert form re-enabled (submit button NOT disabled) |
| A1 | **axe-core**: countdown state pasa axe-core WCAG 2.1 AA 0 violaciones (ver §11.4 mockup) |

### 13.3 Sandbox F.6 caveat

Per F2.1 + F2.2 + F2.3 archive + F3.1 archive precedent, las e2e (`lockout.spec.ts`) corren en sandbox F.6 con npm 11.16.0 que refuses `workspace:*` resolution. F3.2 e2e va a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect. Unit tests (vitest sobre `useCountdown.ts` + `Login.tsx` mockeado + `parkosFetch.ts` pre-flight gate) cubren el camino crítico.

### 13.4 Cobertura thresholds

```typescript
// apps/electron-sucursal/vitest.config.ts (extracto — F2.1 baseline, F3.2 agrega thresholds)

coverage: {
  provider: 'v8',
  thresholds: {
    // ... existing thresholds F2.1+F2.2+F3.1 ...
    'src/features/auth/hooks/useCountdown.ts':  { lines: 90, functions: 90, branches: 85 },
    'src/features/auth/components/LoginForm.tsx': { lines: 80, functions: 80, branches: 75 },
    'src/features/auth/pages/Login.tsx':        { lines: 80, functions: 80, branches: 75 },
  }
}
```

```typescript
// apps/ui-kit/vitest.config.ts (extracto — F2.2 baseline, F3.2 agrega threshold)

coverage: {
  provider: 'v8',
  thresholds: {
    'src/fetch/parkosFetch.ts': { lines: 85, functions: 85, branches: 80 }, // F3.2 pre-flight gate
    'src/hooks/useAuth.ts':      { lines: 80, functions: 80, branches: 75 }, // F3.2 refresh interval
  }
}
```

---

## 14. Consideraciones de performance

Cross-ref `proposal.md` §4.7 (DEC-F3.2-07) + §14.

### 14.1 Pre-flight latency budget ≤200ms p95

- `refreshIfExpiringSoon` regex match + `Date.parse` + Mutex acquisition check: ~1-5ms (módulo-level compilation).
- `refreshAccessToken` HTTP POST `/auth/refresh`: ~50-150ms p95 (F2.2 benchmark post-Mutex + cookie round-trip).
- Total budget: ~200ms p95. Soft target — si >200ms, request continúa con token existente (graceful degradation, R5 mitigation).

### 14.2 Countdown `setInterval(1000)` overhead

- Single active countdown per LoginPage (1 component instance per session).
- `setInterval(1000)` callback recalcula `secondsLeft` desde wall clock — ~0.1ms CPU cost per tick.
- Cleanup en unmount via `useEffect` return → 0 idle cuando countdown no activo.
- Browser throttle cuando tab inactive → setInterval pausado. Date.now() baseline garantiza countdown correcto al volver (R1 mitigation).

### 14.3 SWR refresh 50min vs 5min

- Baseline F2.2 5min: 12 refreshes/hora por sesión activa. ~30KB bandwidth/refresh = ~360KB/hora.
- F3.2 50min: ~1.2 refreshes/hora por sesión activa. ~30KB bandwidth/refresh = ~36KB/hora.
- **Ahorro**: ~324KB/hora bandwidth por sesión activa. ~90% menos requests a `/auth/me`.
- Latency SWR negligible (~100-200ms revalidation non-blocking).

### 14.4 Memory footprint

- `useCountdown` local state: ~16B (2 numbers + 2 booleans).
- `useAuthStore.expiresAt` ISO 8601 string: ~24B.
- Pre-flight regex compilation: ~50B módulo-level (one-time).
- **Total**: ~90B adicional en memoria por sesión activa. Insignificante.

### 14.5 Network requests

- Pre-login: 0 requests pre-flight (expiresAt null).
- Post-login active session: 1 refresh cada 50min (vs 12 cada 5min baseline).
- Pre-flight gate: 1 refresh cada vez que POST crítico triggerea con expiresAt <5min. Typical: ~0-1/turno (operador no submitea muchos POST críticos).
- **Total**: 1-2 refreshes/turno vs 12-30 baseline. ~95% menos requests.

---

## 15. Migración y rollout

Cross-ref `proposal.md` §15 + `pending.md` Fase 3 1/3 cerrado (F3.1 ✅), F3.2 row 2 con budget 130 LOC.

### 15.1 F3.2 entrega

**Cluster C1** (4 atomic tasks T1..T4) en orden mandatory:

```
T1 — useCountdown hook + 4 unit tests (U1-U4)
   ↓ (T1 provee hook reusable)
(T2 || T3) — countdown integration en LoginForm/Login (T2) || pre-flight gate + 50min refresh (T3)
   ↓ (T2+T3 proveen UI lockout + infra refresh)
T4 — e2e lockout.spec.ts (E1+E2+E3+A1)
   ↓ (T4 provee e2e green gate)
archive — mover change folder a archive/, actualizar pending.md §1 row F3.2 → ✅
```

T2 y T3 son independientes (T2 frontend UI, T3 infra ui-kit) — pueden ejecutarse en paralelo si el executor lo permite.

### 15.2 Forward hooks (Fase 3+)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.3** (Abrir/Cerrar turno) | pre-flight gate automático para `POST /caja-sesion/*` si F3.3 decide agregar al path match | DEC-F3.2-10: extender `PRE_FLIGHT_PATHS` regex |
| **HU-F3.3** | `useAuth().user.sucursal` + `permisos[]` hidratados post-F3.1 | F3.3 consume via SWR data |
| **HU-F3.x** (logout button UI) | `useAuthStore.clear()` + `parkos:auth:cleared` event (F2.2) | F3.3+ logout button dispatch `clear()` + `navigate('/login')` |
| **HU-F3.x** (AuthGuard component) | `parkos:auth:cleared` window event | F3.3+ `<AuthGuard>` envuelve `<Routes>` excepto `/login` |
| **HU-F4.x** (catálogos + ocupación) | `useCountdown` para retry buttons con countdown visual | F4.x export `useRetryWithCountdown` pattern |
| **HU-F4.x** | `parkosFetch` pre-flight gate — F4.x hereda automáticamente | Cero cambios F4.x |
| **HU-F5.x** (facturación) | pre-flight gate automático (`/facturacion/*` ya cubierto) + `useAuth.refreshInterval: 50min` | Cero cambios F5.x |
| **HU-F5.x** | `useCountdown` para retry buttons post-409 conflicto | F5.x export `useRetryWithCountdown` |
| **HU-F11.x** (sync UI + alertas CU-07/14) | `useCountdown` para reintentos de sync con countdown visual | F11.x export `useSyncRetryCountdown` que envuelve `useCountdown` con exponential backoff |
| **HU-F11.x** | `useAuth` 50min refresh — F11.x hereda automáticamente | Cero cambios F11.x |
| **PR7 backend** (refresh-token rotation) | `refreshAccessToken` Mutex F2.2 + pre-flight F3.2 → rotación con `jti` reuse detection | PR7 backend: detectar reuse de `jti` claim y revocar cadena |

### 15.3 Rollout strategy

- **Branch**: `feat/fase-2-electron-scaffold` (HEAD `bcfe2ed`).
- **PR target**: `origin/dev`.
- **Merge order**: F3.2 merge a `dev` ANTES de F3.3 (F3.3 consume `useCountdown` + pre-flight gate). F3.1 ya mergeado.
- **Feature flag**: NO. F3.2 es consumer directo de infra shipped F2.1+F2.2+F3.1. Cero toggle runtime.
- **Sandbox**: F3.2 e2e puede SKIP en sandbox F.6 (npm 11.16.0 refuses workspace:*) — documentado como D-env en verify-report. Unit tests cubren el camino crítico.
- **Local dev**: e2e verdes en Windows native con npm 11.16+ (per F2.1+F2.2+F2.3+F3.1 archive precedent).

### 15.4 Pendiente post-archive

- `pending.md` §1 row F3.2 → marcar ✅ cerrado.
- `docs/02-arquitectura/decisiones-tecnicas.md` → agregar DEC-F3.2-01..11 resumen (cross-ref `proposal.md` §4).
- `openspec/CHANGELOG.md` → entrada "2026-09-15 — HU-F3.2 lockout countdown + refresh pre-flight archived (6 new REQ-OPS-113..118 user-facing)".
- `openspec/specs/operations/spec.md` post-archive → REQ-OPS vigente = 001..118 (118 total).

### 15.5 Resoluciones de open questions (verificación cruzada)

Las 3 inconsistencies detectadas en `exploration.md` §1 están cerradas en `proposal.md` §16:

- **I1** (max_intentos 4 vs 5): DEC-F3.2-09 — e2e configurable via env (default 4). Sin cambio backend.
- **I2** (refreshInterval 5min vs 50min): DEC-F3.2-04 — T3 MODIFY `useAuth.ts:60` → `REFRESH_INTERVAL_MS = 50 * 60 * 1000`. Constante exportada para testabilidad.
- **I3** (`/caja/arqueo` no existe): DEC-F3.2-10 — pre-flight gate genérico matchea regex `/\/facturacion(\/|$)|\/caja\/arqueo/`. F3.2 cubre `/facturacion/*` que existe post-F1.8 (REQ-OPS-030). `/caja/arqueo*` se incluye en la regex aunque el endpoint aún no exista — forward extensibility cuando Fase 10 introduzca arqueos.

0 KNOWN-MISSING. F3.2 ready for `sdd-tasks`.

---

## Appendix A: TS mockups completos (~550 LOC)

### A.1 `useCountdown.ts` completo (~40 LOC target — T1)

```typescript
// apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts (NEW F3.2 T1)

import { useEffect, useState } from 'react';

export interface UseCountdownOptions {
  onComplete?: () => void;
}

export interface UseCountdownReturn {
  secondsLeft: number;
  isExpired: boolean;
}

/**
 * Hook countdown drift-resistant con Date.now() baseline (DEC-F3.2-01).
 *
 * NUNCA accumulator (`secondsLeft--`) — recalcula desde wall clock en cada
 * tick para resistir tab inactive + system sleep pauses que pausen setInterval
 * (browser throttle). R1 mitigation.
 *
 * @param retryAfterSeconds  Segundos hasta re-habilitación (0 = expirado inmediato).
 * @param options.onComplete Callback opcional cuando secondsLeft llega a 0.
 * @returns { secondsLeft, isExpired }
 */
export function useCountdown(
  retryAfterSeconds: number,
  options?: UseCountdownOptions,
): UseCountdownReturn {
  const endTime = Date.now() + retryAfterSeconds * 1000;
  const [secondsLeft, setSecondsLeft] = useState(() =>
    Math.max(0, Math.ceil((endTime - Date.now()) / 1000)),
  );
  const [isExpired, setIsExpired] = useState(secondsLeft === 0);

  useEffect(() => {
    if (isExpired) return;
    const id = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((endTime - Date.now()) / 1000));
      setSecondsLeft(remaining);
      if (remaining === 0) {
        setIsExpired(true);
        options?.onComplete?.();
        clearInterval(id);
      }
    }, 1000);
    return () => clearInterval(id);
  }, [endTime, isExpired, options]);

  return { secondsLeft, isExpired };
}
```

### A.2 `useCountdown.test.ts` completo (~50 LOC target — T1)

```typescript
// apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts (NEW F3.2 T1)

import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useCountdown } from './useCountdown';

describe('useCountdown', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('U1: baseline Date.now() returns retryAfterSeconds immediately', () => {
    const { result } = renderHook(() => useCountdown(60));
    expect(result.current.secondsLeft).toBe(60);
    expect(result.current.isExpired).toBe(false);
  });

  it('U2: cleanup on unmount — no callback fires post-unmount', () => {
    const onComplete = vi.fn();
    const { unmount } = renderHook(() => useCountdown(2, { onComplete }));
    act(() => vi.advanceTimersByTime(3000));
    unmount();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('U3: onComplete fires at 0', () => {
    const onComplete = vi.fn();
    const { result } = renderHook(() => useCountdown(2, { onComplete }));
    act(() => vi.advanceTimersByTime(2000));
    expect(result.current.secondsLeft).toBe(0);
    expect(result.current.isExpired).toBe(true);
    expect(onComplete).toHaveBeenCalledOnce();
  });

  it('U4: drift resistance via Date.now() baseline (decrementa 2, no 1)', () => {
    const { result, rerender } = renderHook(() => useCountdown(60));
    act(() => vi.advanceTimersByTime(2000));
    expect(result.current.secondsLeft).toBe(58);
    rerender();
    expect(result.current.secondsLeft).toBe(58);
  });
});
```

### A.3 `LoginForm.tsx` countdown delta (+25 LOC target — T2)

```diff
 // apps/electron-sucursal/src/features/auth/components/LoginForm.tsx (F3.1 baseline, F3.2 MODIFY)

 import { useTranslation } from 'react-i18next';
+import { useCountdown } from '../hooks/useCountdown';

 export interface LoginFormProps {
   form: ReturnType<typeof useFormContext<LoginInput>>;
   onSubmit: () => void;
   isSubmitting: boolean;
   error: LoginErrorState;
+  /** Callback opcional invocado cuando countdown llega a 0 (F3.2). */
+  onLockoutExpired?: () => void;
 }

+/** Convierte segundos a formato mm:ss. Inline helper, no librería externa. */
+function formatTime(seconds: number): string {
+  const m = Math.floor(seconds / 60);
+  const s = seconds % 60;
+  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
+}

 export function LoginForm({
   form,
   onSubmit,
   isSubmitting,
   error,
+  onLockoutExpired,
 }: LoginFormProps): JSX.Element {
   const { t } = useTranslation('auth');
+  const isLockout = error?.kind === 'lockout';
+  const { secondsLeft, isExpired } = useCountdown(
+    isLockout ? error.retryAfterSeconds : 0,
+    { onComplete: onLockoutExpired },
+  );
+
+  const isFormDisabled = isSubmitting || (isLockout && !isExpired);

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
+                  disabled={isFormDisabled}
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
+                  disabled={isFormDisabled}
                 />
               </FormControl>
               <FormMessage />
             </FormItem>
           )}
         />

+        {isLockout && !isExpired && (
+          <div data-testid="login-lockout-block">
+            <p role="alert" data-testid="login-error-lockout">
+              {t('lockout')}
+            </p>
+            <p
+              role="status"
+              aria-live="polite"
+              aria-label={t('lockoutLabel', { time: formatTime(secondsLeft) })}
+              data-testid="login-countdown"
+            >
+              {t('lockoutCountdown', { time: formatTime(secondsLeft) })}
+            </p>
+          </div>
+        )}

         <Button
           type="submit"
-          disabled={isSubmitting}
+          disabled={isFormDisabled}
+          aria-disabled={isFormDisabled}
           data-testid="login-submit"
         >
           {isSubmitting ? t('common:loading') : t('submit')}
         </Button>

+        {/* Otros errores (no-lockout) */}
         {error?.kind === 'invalid_credentials' && (
           <p role="alert" data-testid="login-error-invalid">
             {t('invalidCredentials')}
           </p>
         )}
-        {error?.kind === 'lockout' && (
-          <p role="alert" data-testid="login-error-lockout">
-            {t('lockout')}
-          </p>
-        )}
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

### A.4 `Login.tsx` wiring delta (+10 LOC target — T2)

```diff
 // apps/electron-sucursal/src/features/auth/pages/Login.tsx (F3.1 baseline, F3.2 MODIFY)

 // ... F3.1 imports verbatim ...

 export function Login(): JSX.Element {
   // ... F3.1 state verbatim ...
+  const [errorState, setErrorState] = useState<LoginErrorState>(null);

   // DEC-F3.1-07: esperar data.user antes de navigate (F3.1 verbatim)
   useEffect(() => {
     if (isAuthenticated && data?.user && !isLoading) {
       navigate('/', { replace: true });
     }
   }, [isAuthenticated, data?.user, isLoading, navigate]);

+  // F3.2 NUEVO: reset errorState cuando lockout expira
+  const handleLockoutExpired = useCallback(() => {
+    setErrorState(null);
+  }, []);

   const onSubmit = form.handleSubmit(async (values) => {
     setErrorState(null);
     try {
       const pair = await postLogin(values.email, values.password);
       setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
     } catch (err) {
       if (err instanceof InvalidCredentialsError) {
         setErrorState({ kind: 'invalid_credentials' });
       } else if (err instanceof AccountLockedError) {
-        setErrorState({ kind: 'lockout', retryAfterSeconds: err.retryAfterSeconds });
+        setErrorState({ kind: 'lockout', retryAfterSeconds: err.retryAfterSeconds });
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
+      onLockoutExpired={handleLockoutExpired}
     />
   );
 }
```

### A.5 `auth.json` delta (+3 keys target — T2)

```diff
 // apps/electron-sucursal/src/renderer/i18n/locales/auth.json

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
+  "lockoutCountdown": "Reintento disponible en {{time}}",
+  "lockoutReEnable": "El formulario se ha reactivado. Puedes intentar de nuevo.",
+  "lockoutLabel": "Tiempo restante para reintentar: {{time}}",
   "validation": {
     "required": "Este campo es obligatorio",
     "email": { "invalid": "Ingresa un correo válido" },
     "password": {
       "minLength": "La contraseña debe tener al menos 8 caracteres",
       "required": "Ingresa tu contraseña"
     }
   }
 }
```

### A.6 `useAuth.ts` 50min refresh delta (line 60 — T3)

```diff
 // apps/ui-kit/src/hooks/useAuth.ts (F2.2 baseline, F3.2 MODIFY line 60)

 import useSWR from 'swr';
 import { parkosFetch } from '@parkos/ui-kit/fetch';
 import { useAuthStore } from '@parkos/ui-kit/store';

+/**
+ * Intervalo de refresh SWR en milisegundos.
+ *
+ * DEC-F3.2-04: 50 minutos vs TTL del access_token (3600s = 1h).
+ * Deja 10min de safety margin: si un refresh falla, el operador tiene
+ * 10min para retry antes de que useAuth() emita parkos:auth:cleared.
+ *
+ * Per DEC-SUC-03 (plan.md:418) verbatim.
+ */
+export const REFRESH_INTERVAL_MS = 50 * 60 * 1000;

 export function useAuth() {
   const accessToken = useAuthStore((s) => s.accessToken);

   const { data, error, isLoading, mutate } = useSWR<AuthMeResponse>(
     accessToken ? '/auth/me' : null,
     parkosFetch,
     {
-      refreshInterval: 5 * 60 * 1000,
+      refreshInterval: REFRESH_INTERVAL_MS,
       revalidateOnFocus: true,
       dedupingInterval: 2000,
       onError: (err) => {
         if (err instanceof ParkosHttpError && err.status === 401) {
           useAuthStore.getState().clear();
           window.dispatchEvent(new Event('parkos:auth:cleared'));
         }
       },
     }
   );

   return {
     data,
     error,
     isLoading,
     mutate,
     isAuthenticated: !!data?.user,
   };
 }
```

### A.7 `parkosFetch.ts` pre-flight gate delta (+20 LOC target — T3)

```diff
 // apps/ui-kit/src/fetch/parkosFetch.ts (F2.2 baseline, F3.2 MODIFY +20 LOC)

 import { ParkosHttpError, type ParkosFetchInit } from './parkosFetch.types';
 import { useAuthStore } from '@parkos/ui-kit/store';

+/** Paths críticos que triggerean pre-flight refresh gate (DEC-F3.2-03). */
+export const PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/;
+
+/** Umbral de expiración en ms para invocar pre-flight (DEC-F3.2-07). */
+export const PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000;
+
+/**
+ * Refresh proactivo del access_token si está por expirar (<5min).
+ * Reusa refreshAccessToken Mutex (F2.2 DEC-FETCH-03 invariant).
+ * No-op si expiresAt es null (pre-login).
+ */
+async function refreshIfExpiringSoon(): Promise<void> {
+  const { expiresAt, refreshAccessToken } = useAuthStore.getState();
+  if (expiresAt === null) return;
+  const msUntilExpiry = Date.parse(expiresAt) - Date.now();
+  if (msUntilExpiry < PRE_FLIGHT_THRESHOLD_MS) {
+    await refreshAccessToken();
+  }
+}

 export async function parkosFetchRaw<T = unknown>(
   url: string,
   init: ParkosFetchInit = {},
 ): Promise<T> {
+  const method = (init.method ?? 'GET').toUpperCase();
+  const isPreFlightCandidate = method === 'POST' && PRE_FLIGHT_PATHS.test(url);
+
+  // DEC-F3.2-03: pre-flight gate solo para POST críticos.
+  if (isPreFlightCandidate) {
+    await refreshIfExpiringSoon();
+  }
+
   const res = await fetch(url, { ...init, credentials: 'include' });

   if (res.status === 401) {
     // F2.2 handle401 Mutex preserved (DEC-FETCH-03)
     return handle401<T>(url, init);
   }

   if (!res.ok) {
     throw new ParkosHttpError(res.status, await res.text().catch(() => ''), res.url);
   }

   return (await res.json()) as T;
 }
```

### A.8 `e2e/auth/lockout.spec.ts` outline (~80 LOC target — T4)

```typescript
// apps/electron-sucursal/e2e/auth/lockout.spec.ts (NEW F3.2 T4)

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Lockout countdown flow', () => {
  test.beforeEach(async ({ page, context }) => {
    // Limpiar cookies para tests aislados
    await context.clearCookies();
  });

  test('E1: 4 intentos fallidos → 429 + countdown visible', async ({ page }) => {
    let attemptCount = 0;
    await page.route('**/api/v1/auth/login', (route) => {
      attemptCount += 1;
      if (attemptCount < 4) {
        return route.fulfill({ status: 401, body: JSON.stringify({ error: 'invalid_credentials' }) });
      }
      return route.fulfill({
        status: 429,
        headers: { 'Retry-After': '600' },
        body: JSON.stringify({ error: 'account_locked' }),
      });
    });

    await page.goto('/login');
    for (let i = 0; i < 4; i++) {
      await page.fill('[data-testid="login-email"]', `wrong${i}@example.com`);
      await page.fill('[data-testid="login-password"]', 'wrongpass');
      await page.click('[data-testid="login-submit"]');
      await page.waitForResponse(/.*\/auth\/login/);
    }

    await expect(page.getByTestId('login-countdown')).toBeVisible();
    await expect(page.getByTestId('login-countdown')).toContainText(/\d{2}:\d{2}/);
    await expect(page.getByTestId('login-email')).toBeDisabled();
    await expect(page.getByTestId('login-password')).toBeDisabled();
    await expect(page.getByTestId('login-submit')).toBeDisabled();
  });

  test('E2: countdown decrementa cada ~1000ms', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 429,
        headers: { 'Retry-After': '10' },
        body: JSON.stringify({ error: 'account_locked' }),
      }),
    );

    await page.goto('/login');
    await page.fill('[data-testid="login-email"]', 'op@sucursal.parkos.local');
    await page.fill('[data-testid="login-password"]', 'valid-password-1234');
    await page.click('[data-testid="login-submit"]');

    const countdown = page.getByTestId('login-countdown');
    await expect(countdown).toBeVisible();
    const initialText = (await countdown.textContent()) ?? '';
    const initialMatch = initialText.match(/(\d{2}):(\d{2})/);
    expect(initialMatch).not.toBeNull();

    await page.waitForTimeout(2500);
    const laterText = (await countdown.textContent()) ?? '';
    const laterMatch = laterText.match(/(\d{2}):(\d{2})/);
    expect(laterMatch).not.toBeNull();
    expect(Number(initialMatch![2])).toBeGreaterThan(Number(laterMatch![2]));
  });

  test('E3: countdown llega a 0 → form re-habilitado', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 429,
        headers: { 'Retry-After': '2' },
        body: JSON.stringify({ error: 'account_locked' }),
      }),
    );

    await page.goto('/login');
    await page.fill('[data-testid="login-email"]', 'op@sucursal.parkos.local');
    await page.fill('[data-testid="login-password"]', 'valid-password-1234');
    await page.click('[data-testid="login-submit"]');

    await expect(page.getByTestId('login-countdown')).toBeVisible();
    await expect(page.getByTestId('login-submit')).toBeDisabled();

    // Esperar ~3s para que countdown llegue a 0
    await page.waitForTimeout(3000);

    await expect(page.getByTestId('login-submit')).not.toBeDisabled();
    await expect(page.getByTestId('login-countdown')).not.toBeVisible();
  });

  test('A1: axe-core WCAG 2.1 AA 0 violaciones en lockout state', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 429,
        headers: { 'Retry-After': '300' },
        body: JSON.stringify({ error: 'account_locked' }),
      }),
    );

    await page.goto('/login');
    await page.fill('[data-testid="login-email"]', 'op@sucursal.parkos.local');
    await page.fill('[data-testid="login-password"]', 'valid-password-1234');
    await page.click('[data-testid="login-submit"]');

    await expect(page.getByTestId('login-countdown')).toBeVisible();

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(accessibilityScanResults.violations).toEqual([]);
  });
});
```

---

## Appendix B: Configuraciones y archivos delta

### B.1 NEW (4 archivos de producción + 3 tests)

| Path | Task | LOC target |
|---|---|---|
| `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` | T1 | 40 |
| `apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts` | T1 | 50 |
| `apps/electron-sucursal/e2e/auth/lockout.spec.ts` | T4 | 80 |
| **TOTAL new prod+tests** | T1+T4 | **~170 LOC** |

### B.2 MODIFY (7 archivos de producción + 3 keys i18n)

| Path | Task | Delta LOC |
|---|---|---|
| `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` | T2 | +25 LOC |
| `apps/electron-sucursal/src/features/auth/pages/Login.tsx` | T2 | +10 LOC |
| `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` | T2 | +25 LOC (U8 + U9) |
| `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` | T2 | +15 LOC (U10) |
| `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` | T2 | +3 keys |
| `apps/ui-kit/src/hooks/useAuth.ts` | T3 | line 60 + JSDoc + REFRESH_INTERVAL_MS export |
| `apps/ui-kit/src/hooks/useAuth.test.ts` | T3 | +10 LOC (U11) |
| `apps/ui-kit/src/fetch/parkosFetch.ts` | T3 | +20 LOC (pre-flight gate + constants) |
| `apps/ui-kit/src/fetch/parkosFetch.test.ts` | T3 | +60 LOC (U12-U16) |
| **TOTAL delta** | T2+T3 | **~165 LOC** |

### B.3 Configuraciones (verbatim diffs)

#### B.3.1 `package.json` (apps/electron-sucursal + apps/ui-kit)

F3.2 **NO requiere nuevas dependencias**. Todo el stack ya está en `package.json:22-77` per F2.1+F2.2+F3.1 baseline (`react@^18.3.1` + `setInterval` vanilla + `Date.now()` vanilla + `useEffect` React + vitest + @testing-library/react + @axe-core/playwright).

```diff
   "dependencies": {
-    // F2.1 + F2.2 + F3.1 stack (sin cambios)
+    // F2.1 + F2.2 + F3.1 stack + F3.2 useCountdown hook (NO requiere deps)
   }
```

#### B.3.2 `tsconfig.renderer.json`

F3.2 **NO requiere cambios**. `useCountdown.ts` usa imports existentes (`useState`, `useEffect` from `react`). `parkosFetch.ts` + `useAuth.ts` modification son type-safe per F2.2 tsconfig.

```diff
   // Sin cambios — F3.2 hereda paths y strict mode de F2.1+F2.2+F3.1
```

#### B.3.3 `vitest.config.ts` (apps/electron-sucursal + apps/ui-kit)

F3.2 **agrega coverage thresholds** para `useCountdown.ts` + `Login.tsx` + `LoginForm.tsx` + `parkosFetch.ts` (pre-flight gate). Sin cambios estructurales.

```diff
   // apps/electron-sucursal/vitest.config.ts
   coverage: {
     provider: 'v8',
     thresholds: {
       // ... existing F2.1+F2.2+F3.1 thresholds ...
+      'src/features/auth/hooks/useCountdown.ts':   { lines: 90, functions: 90, branches: 85 },
+      'src/features/auth/components/LoginForm.tsx': { lines: 80, functions: 80, branches: 75 },
+      'src/features/auth/pages/Login.tsx':         { lines: 80, functions: 80, branches: 75 },
     }
   }

   // apps/ui-kit/vitest.config.ts
   coverage: {
     provider: 'v8',
     thresholds: {
       // ... existing F2.2 thresholds ...
+      'src/fetch/parkosFetch.ts': { lines: 85, functions: 85, branches: 80 }, // F3.2 pre-flight gate
+      'src/hooks/useAuth.ts':      { lines: 80, functions: 80, branches: 75 }, // F3.2 refresh interval
     }
   }
```

### B.4 READ ONLY (anchors — NO modificar)

- `apps/electron-sucursal/electron/main.ts` (F2.3, no F3.2 touch — DEC-F3.1-04 login HTTP no IPC).
- `apps/electron-sucursal/electron/preload.ts` (F2.2, no F3.2 touch — F3.2 NO agrega IPC methods).
- `apps/electron-sucursal/electron/bridge.d.ts` (F2.2+F2.3, no F3.2 touch).
- `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (F3.1, READ ONLY — `AccountLockedError` + `parseRetryAfter` ya shipped, F3.2 consume as-is).
- `apps/electron-sucursal/src/features/auth/api/loginSchema.ts` (F3.1, READ ONLY — Zod schema no F3.2 touch).
- `apps/ui-kit/src/store/authStore.ts` (F2.2, READ ONLY — `setTokens` + `clear` + `refreshAccessToken` Mutex shipped, F3.2 consume as-is).
- `apps/ui-kit/src/cn.ts` + `apps/ui-kit/src/tokens.ts` (F2.1, no F3.2 touch).
- `apps/electron-sucursal/src/renderer/components/ui/{form,input,button}.tsx` (F2.1, no F3.2 touch — reusa shadcn primitives).
- `apps/electron-sucursal/src/renderer/i18n/index.ts` (F2.1, no F3.2 touch — auth namespace ya registrado).
- `apps/electron-sucursal/src/renderer/i18n/locales/{common,operacion,caja,facturacion,sync,errors}.json` (F2.1, no F3.2 touch).
- `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (F2.3, no F3.2 touch).
- `apps/electron-sucursal/src/renderer/App.tsx` (F3.1, no F3.2 touch — `/login` route ya wired).
- `apps/electron-sucursal/src/renderer/main.tsx` (F2.1, no F3.2 touch).
- `apps/electron-sucursal/e2e/{scaffold,auth/login,auth/parkos-fetch,auth/bridge,a11y/wcag-2.1-aa,lifecycle,kiosko}.spec.ts` (F2.1+F2.2+F2.3+F3.1, no F3.2 touch — agrega solo `lockout.spec.ts`).
- `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py` (HU-F1.2 + HU-F1.15 shipped, no F3.2 touch — F3.2 consume `Retry-After` header as-is).
- `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` (HU-F1.2 shipped, no F3.2 touch).

### B.5 Total de impacto

- **NEW**: 3 archivos de producción + tests (~170 LOC) + 4 artefactos SDD (exploration + proposal + design + tasks + verify-report + archive-report, ~3000 LOC).
- **MODIFY**: 7 archivos (~165 LOC delta production + 3 keys i18n + coverage thresholds).
- **READ ONLY**: 16 archivos.
- **TOTAL IMPACT**: 26 archivos de 170 LOC nuevos + 165 LOC delta.

---

## CHANGELOG

- (2026-09-15) F3.2 design phase complete — 15 secciones + 2 apéndices verbatim clonando layout F3.1 1:1, ~880 LOC total. 11 DEC-F3.2-01..11 documentados (cross-ref `proposal.md` §4 + `exploration.md` §7). DEC-F3.2-08 + DEC-F3.2-11 verdict **DELTA** (F3.2 ES user-facing: countdown visual + form disabled + pre-flight gate + 50min refresh). 6 acceptance gates G1..G6 mapeados a tests (G1 useCountdown U1-U4, G2 regression loginApi F3.1, G3 LoginForm U8-U9, G4 Login U10, G5 parkosFetch U12-U16, G6 e2e E1-E3+A1). 6 REQ-OPS-113..118 coverage (REQ-OPS-113 useCountdown baseline + cleanup, REQ-OPS-114 form disabled + countdown display, REQ-OPS-115 auto re-enable, REQ-OPS-116 pre-flight gate, REQ-OPS-117 50min refresh, REQ-OPS-118 axe-core A1 WCAG). Arquitectura: `<LoginPage>` container (F3.1 + useEffect reset errorState cuando lockout expira) + `<LoginForm>` presentational (F3.1 + useCountdown + `<p role="status" aria-live="polite">` countdown + form `disabled` + `aria-disabled`) + `useCountdown` hook NEW (`Date.now()` baseline + `setInterval(1000)` + cleanup + onComplete) + `useAuth` 50min refresh (`REFRESH_INTERVAL_MS` exportada) + `parkosFetch` pre-flight gate (`PRE_FLIGHT_PATHS` regex + `PRE_FLIGHT_THRESHOLD_MS = 5min` + Mutex shared con handle401 F2.2 DEC-FETCH-03 invariant preserved). 8 TS mockups en Appendix A (useCountdown.ts + useCountdown.test.ts + LoginForm.tsx delta + Login.tsx delta + auth.json delta + useAuth.ts delta + parkosFetch.ts delta + e2e lockout.spec.ts outline) + 3 configs delta en Appendix B.3 (package.json no-cambios + tsconfig no-cambios + vitest.config.ts thresholds nuevos). Ready for `sdd-tasks`.

---

**End of design — HU-F3.2.**