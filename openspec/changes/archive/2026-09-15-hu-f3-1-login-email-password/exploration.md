# Exploración — HU-F3.1 Login con `email` + `password`

> **Phase**: explore (sdd-explore) · **Status**: ready for sdd-propose
> **HU ID**: HU-F3.1 (Fase 3 — primera HU; Autenticación y turno de caja, transversal a todas las CU operativas)
> **Working dir**: E:/easypunto_parkos · **Branch**: feat/fase-2-electron-scaffold (HEAD ba9d81a, F2.3 archivado 2026-09-15)
> **Inputs**: plan.md lines 1274-1305 (HU-F3.1 verbatim, 4 tareas atómicas T1..T4, 190 LOC); plan.md lines 1159-1267 (Fase 2 archivada: F2.1 + F2.2 + F2.3 — precedents); plan.md lines 567-1158 (Fase 1 backend prerequisites — HU-F1.2 cubre /auth/login + /auth/me + lockout); openspec/_meta/roadmap.md (IT-1..IT-10 web_sucursal consumer map); openspec/specs/operations/spec.md (XR6 defense-in-depth pattern); openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/{exploration.md,proposal.md,design.md,tasks.md} (precedent verbatim 17 secciones); openspec/changes/archive/2026-09-15-hu-f2-3-electron-auto-update-kiosko/exploration.md (más reciente precedent); apps/electron-sucursal/{package.json:22-53, electron/main.ts:1-122, electron/preload.ts:1-49, electron/bridge.d.ts:1-92}; apps/electron-sucursal/src/renderer/{App.tsx:1-37, main.tsx:1-27, i18n/index.ts:1-39, i18n/locales/{common,auth,errors}.json, components/ui/{form,input,button}.tsx}; apps/ui-kit/{package.json:1-40, src/{fetch/parkosFetch.ts:1-212, store/authStore.ts:1-129, hooks/useAuth.ts:1-87, fetch/index.ts, store/index.ts, hooks/index.ts, index.ts}}; backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-583 (POST /auth/login 200 OK + cookie parkos_session httponly + 429 account_locked + 401 invalid_credentials); backend/packages/parkos_core/src/parkos_core/schemas/auth.py (LoginRequest{email,password min_length:8}, TokenPair, AuthMeResponse); modelo_datos_er.mmd:270-289 (configuracion_seguridad); modelo_datos_er.mmd:558-573 (prod.login [L-S]); docs/01-requisitos/no-funcionales.md:126 (RNF-022 WCAG 2.1 AA — Login debe ser a11y compliant); docs/03-desarrollo/{setup.md, estandares.md}; pending.md §1-§6 (Fase 3 0/3 abierto, F3.1 = primer HU).

---

## 1. Title & Goal

**Title**: "Login con `email` + `password` contra POST /auth/login con `credentials:'include'` + cookie `httpOnly` + hidratación de authStore desde GET /auth/me + redirect a `/` + anti-enumeración (`errors.invalid_credentials` único para 401)"

**Goal**: Fase 2 archivada (F2.1 + F2.2 + F2.3, 24 commits en `feat/fase-2-electron-scaffold`) deja sentada toda la infraestructura transversal: Electron 30 skeleton + parkosFetch con retry/refresh/idempotency/Zod + bridge IPC tipado con 8 métodos + authStore Zustand con persist electron-store + useAuth() SWR hook con `/auth/me` revalidation 5min + electron-updater + single-instance + kiosko + electron-log + StatusBar aria-live polite. F3.1 entrega el primer consumer end-to-end de esa infraestructura: la pantalla de login real que el operador usa al iniciar su turno. El formulario dispara `POST /auth/login` con `credentials:'include'`, el backend emite cookie `parkos_session` (httponly+secure+samesite=lax) + body con TokenPair, `parkosFetch` setTokens hidrata `authStore`, `useAuth()` re-fetcha `/auth/me` para resolver `user` + `sucursal` + `permisos`, y el componente redirige a `/` (la sesión activa queda libre para que F3.3 monte `AbrirTurno` cuando lo requiera).

**Por qué importa** (rationale): F3.1 es el primer consumer real de las primitivas de Fase 2. Si bien el flujo HTTP es sencillo (login → cookie → me → redirect), tres factores elevan su criticidad:

1. **Anti-enumeración (DEC-SUC-02)**: el campo de acceso es `email`, NUNCA `cedula` — corrige explícitamente una versión previa del plan que asumía `cedula` (error que NO proviene de CU-01 verificado sino de una lectura incorrecta del esquema de autenticación real). El error genérico `errors.invalid_credentials` (401) cubre tanto email desconocido como password incorrecta sin distinción — implementado en backend `auth.py:159-191, 250-251`.
2. **Cookie httpOnly + credentials:'include'**: el navegador NUNCA expone la cookie a JavaScript (`HttpOnly` flag). Esto blinda contra exfiltración via XSS — el atacante puede inyectar scripts pero NO puede leer `parkos_session`. El frontend solo necesita `authStore` con el access_token en electron-store (que NO es accesible desde el DOM); el `Authorization: Bearer` header que `parkosFetch` inyecta autentica los GET/POST contra el backend.
3. **Hidración transaccional**: el flujo login → /auth/me debe ser atómico en términos de UX. Si el operador llega a `/` y `useAuth()` muestra `user: null` durante el primer render (porque `/auth/me` aún no resolvió), el componente renderiza un flash de "sesión no iniciada". F3.1 lo evita montando el redirect sobre `useAuth().isAuthenticated` + `isLoading`, esperando `useAuth()` a tener `data.user` antes de hacer `navigate('/')`.

**Hard constraints** (mirrored from plan.md:1278-1297 verbatim):

- Form con `email` (formato válido) + `password` (mínimo 8 caracteres). Validación Zod: `z.object({ email: z.string().email(), password: z.string().min(8) })`.
- POST `/auth/login` con `credentials:'include'` (cookie httpOnly cross-origin safe via SameSite=Lax).
- 401 → `errors.invalid_credentials` único (anti-enumeración). NO distinción entre "email no existe" y "password incorrecta".
- 429 → ver HU-F3.2 (lockout visible). F3.1 NO implementa countdown — solo catch + surface.
- `authStore` hidrata desde `GET /auth/me`. `useAuth().user.sucursal` es el `uuid` de la sede; `permisos` es un `array<string>`.
- Componentes: `Login` (page, contenedor: RHF+Zod, llama `parkosFetch`); `LoginForm` (presentacional, dos campos + botón).
- Regla DEC-SUC-02: credencial es `email`, NUNCA `cedula`.
- Tamaño: 190 LOC. 4 tareas atómicas T1..T4.
- e2e: `e2e/login.spec.ts` — 3 casos (login OK con cookie, refresh transparente, logout).

**Scope**: ~190 LOC production + ~110 LOC tests = ~300 LOC total. Plan 190 LOC matches: 190 ≈ 250 production logic - 60 LOC para shadcn-generated Form/Input/Button + i18n keys + Auth namespace que ya existían pre-F3.1. Breakdown por cluster C1 detallado en §10.

## 2. Estado actual verificado

### 2.1 electron/main.ts (apps/electron-sucursal/electron/main.ts:1-122)

**Verificado**:
- **R-MAIN-1 (PASS)**: `app.requestSingleInstanceLock()` antes de `whenReady` (F2.3 DEC-UPD-07). Segunda instancia enfoca + termina.
- **R-MAIN-2 (PASS)**: `initLogConfig(log, app)` antes de whenReady + captura `uncaughtException`/`unhandledRejection` (F2.3 DEC-UPD-11).
- **R-MAIN-3 (PASS)**: `initUpdater(autoUpdater, process.env, log)` + `initApiStatus(baseURL, 30_000, 5_000, log)` en whenReady (F2.3 DEC-UPD-01/05).
- **R-MAIN-4 (PASS)**: `applyKiosko(mainWindow, Menu, true, log)` si `PARKOS_KIOSK_MODE=1` (F2.3 DEC-UPD-08).
- **R-MAIN-5 (PASS)**: IPC handlers `api:status`, `kiosk:unlock`, `kiosk:toggle`, `app:quit` registrados (F2.3 T2+T4).
- **R-MAIN-6 (FAIL — F3.1 NO requiere)**: NO hay handler IPC `auth:login` ni `auth:me`. F3.1 NO agrega handlers — login fluye por HTTP directo vía `parkosFetch`, NO IPC. El bridge IPC es para capabilities que requieren main process (print, usb, kiosk, app quit, api-status, electron-store) — auth es HTTP puro. (DEC-F3.1-04 detalla este rationale.)

**Decisión técnica (ver §8)**: F3.1 NO modifica `main.ts`. Login UI vive en el renderer; `parkosFetch` ejecuta fetch HTTP contra el backend; `authStore` persiste tokens via IPC `authStore.{get,set,delete}` que ya está wireado (F2.2 DEC-FETCH-08). Esta separación sigue el principio "IPC para capabilities privileged, HTTP para data plane".

### 2.2 electron/preload.ts (apps/electron-sucursal/electron/preload.ts:1-49)

**Verificado**:
- **R-IPC-1 (PASS)**: `contextBridge.exposeInMainWorld('bridge', {...})` con whitelist explícita de 8 métodos (F2.2 DEC-FETCH-08). NO spread.
- **R-IPC-2 (PASS)**: `bridge.authStore.{get,set,delete}` IPC-invoca `electron-store` en main process — usado por `authStore.ts` para persistir tokens.
- **R-IPC-3 (PASS)**: contract test `__tests__/preload.contract.test.ts` valida shape via mocks (F2.2 shippeó).
- **R-IPC-4 (PASS)**: `bridge.apiStatus.get` consume `/health` polling (F2.3 wireado); NO relacionado con F3.1.

**Decisión técnica (ver §8)**: F3.1 NO modifica `preload.ts`. El renderer NO necesita nuevos métodos IPC para login — todo el flujo es HTTP.

### 2.3 electron/bridge.d.ts (apps/electron-sucursal/electron/bridge.d.ts:1-92)

**Verificado**:
- **R-DTS-1 (PASS)**: `BridgeSurface` interface declara 8 métodos en 6 grupos (imprimir, usb, kiosk, app, apiStatus, authStore) — F2.2 shippeó.
- **R-DTS-2 (PASS)**: `ApiStatus {ok: boolean, latency_ms: number, code?: number}` con el shape F2.3 extendió (DEC-UPD-12 delta).
- **R-DTS-3 (PASS)**: `declare global { interface Window { bridge: BridgeSurface } }` — renderer importa vía `/// <reference types>` en `global.d.ts`.

**Decisión técnica (ver §8)**: F3.1 NO modifica `bridge.d.ts`. NO hay nueva capability IPC.

### 2.4 App.tsx (apps/electron-sucursal/src/renderer/App.tsx:1-37)

**Verificado**:
- **R-ROUTER-1 (PASS)**: `<BrowserRouter>` wrappeado en `main.tsx:18-20` (F2.1 DEC-ELEC-03 vite + react-router-dom@^6.27.0).
- **R-ROUTER-2 (FAIL — F3.1 lo agrega)**: `<Routes>` actual solo tiene `<Route path="/" element={null} />` y `<Route path="*" element={...404...} />`. NO existe ruta `/login`.
- **R-ROUTER-3 (PASS)**: `<StatusBar />` montado arriba de `<main>` (F2.3 DEC-UPD-12). Login page debe aparecer debajo del StatusBar (no override global).
- **R-ROUTER-4 (PASS)**: `useTranslation('common')` hook disponible; 7 namespaces cargados (common, auth, operacion, caja, facturacion, sync, errors).

**Decisión técnica (ver §8)**: F3.1 agrega `<Route path="/login" element={<LoginPage />} />`. La página de login es standalone — no requiere guards de auth porque por definición NO hay sesión aún. Forward: F3.3+ agregan redirect a `/login` si `useAuth().isAuthenticated === false`.

### 2.5 authStore.ts (apps/ui-kit/src/store/authStore.ts:1-129)

**Verificado**:
- **R-AUTHSTORE-1 (PASS)**: `useAuthStore` Zustand con `persist` middleware contra `bridge.authStore.{get,set,delete}` IPC.
- **R-AUTHSTORE-2 (PASS)**: `setTokens(access, refresh, expiresIn)` setea `{accessToken, refreshToken, expiresAt}` con ISO 8601 derivation.
- **R-AUTHSTORE-3 (PASS)**: `clear()` atómico — access+refresh+expiresAt a `null` simultáneamente.
- **R-AUTHSTORE-4 (PASS)**: `partialize` whitelist: SOLO `{accessToken, refreshToken, expiresAt}` cruzan la seam IPC a electron-store. Functions y derived data quedan en memoria.
- **R-AUTHSTORE-5 (PASS)**: `refreshAccessToken()` Mutex singleton — N concurrentes 401 callers comparten UNA promesa (DEC-FETCH-03). `refreshPromise` slot se limpia en finally.

**Decisión técnica (ver §8)**: F3.1 NO modifica `authStore.ts`. F3.1 CONSUME `useAuthStore.setTokens()` desde `Login.tsx` post-`POST /auth/login`. La invariante de atomicidad está garantizada — F3.1 no introduce nuevos campos.

### 2.6 useAuth.ts (apps/ui-kit/src/hooks/useAuth.ts:1-87)

**Verificado**:
- **R-USEAUTH-1 (PASS)**: `useAuth()` hook retorna `{user, sucursal, sucursalesPermitidas, permisos, expiresAt, isAuthenticated, isLoading, error, refresh}`.
- **R-USEAUTH-2 (PASS)**: SWR key `accessToken ? '/auth/me' : null` — si NO hay accessToken, SWR skip fetch (no redundant network on first render). CRÍTICO para F3.1 — la pantalla de login se monta ANTES de login, pero el hook es seguro.
- **R-USEAUTH-3 (PASS)**: `refreshInterval: 5 * 60 * 1000` — revalida cada 5 min per F2.2 plan.md:1208.
- **R-USEAUTH-4 (PASS)**: `onError` con `status===401` dispara `useAuthStore.getState().clear()` + `window.dispatchEvent('parkos:auth:cleared')`. SPA router intercepta y redirect a `/login?next=...` (F3.1 será el consumer upstream).
- **R-USEAUTH-5 (PASS)**: `shouldRetryOnError` excluye 401 (ya manejado por `onError`).

**Decisión técnica (ver §8)**: F3.1 NO modifica `useAuth.ts`. F3.1 CONSUME `useAuth()` desde `Login.tsx` post-redirect — el hook ya hidrata automáticamente cuando `setTokens` setea accessToken. Si la cookie `parkos_session` ya estaba seteada (caso kiosko post-restart), `parkosFetch` envía `Authorization: Bearer <token>` desde `authStore`, NO la cookie — pero el backend acepta ambos canales (F2.2 auth.py:291-299).

### 2.7 parkosFetch.ts (apps/ui-kit/src/fetch/parkosFetch.ts:1-212)

**Verificado**:
- **R-FETCH-1 (PASS)**: `Authorization: Bearer <jwt>` inyectado desde `useAuthStore().accessToken` (línea 92-96).
- **R-FETCH-2 (PASS)**: `X-Sucursal-Context: <uuid>` desde `localStorage['parkos.lastSelectedSucursal']` (línea 29-30, 99-102).
- **R-FETCH-3 (PASS)**: `Idempotency-Key: SHA-256(method|path|body)` en POST/PUT/DELETE/PATCH EXCEPTO `/auth/login` (línea 105-109). La excepción está implementada explícitamente.
- **R-FETCH-4 (PASS)**: Retry 5xx + 408 + NetworkError con backoff 300/600/1200ms (DEC-FETCH-02).
- **R-FETCH-5 (PASS)**: 401 → refresh-once via Mutex singleton → reintentar UNA vez. Si refresh falla, clear + emit `parkos:auth:cleared` (línea 122-140).
- **R-FETCH-6 (PASS)**: AbortController con `timeoutMs` default 30_000 (línea 154-161).
- **R-FETCH-7 (PASS)**: `parkosFetch<T>(url, init, schema?)` typed wrapper con Zod validation opcional (línea 200-211).

**Decisión técnica (ver §8)**: F3.1 CONSUME `parkosFetch`. NO modifica el cliente HTTP. Para `POST /auth/login` se usa el raw `fetch` con `credentials:'include'` (DEC-F3.1-05 rationale: parkosFetch setea Authorization Bearer que NO existe aún pre-login, y NO debe inyectar headers cross-cutting en el endpoint de credenciales).

### 2.8 package.json (apps/electron-sucursal/package.json:22-53)

**Verificado**:
- **R-DEPS-1 (PASS)**: `react-hook-form@^7.53.0` YA está en dependencies (línea 45).
- **R-DEPS-2 (PASS)**: `zod@^3.23.8` YA está en dependencies (línea 51).
- **R-DEPS-3 (PASS)**: `@hookform/resolvers@^3.9.0` YA está en dependencies (línea 23).
- **R-DEPS-4 (PASS)**: `@radix-ui/react-label@^2.1.0` YA está (línea 27) — usado por FormLabel shadcn (componente ui/form.tsx).
- **R-DEPS-5 (PASS)**: `react-router-dom@^6.27.0` YA está (línea 47) — para `<Route path="/login">`.
- **R-DEPS-6 (PASS)**: `react-i18next@^15.0.2` + `i18next@^23.15.2` YA están (líneas 41, 46) — para `useTranslation('auth')`.
- **R-DEPS-7 (PASS)**: `swr@^2.2.5` YA está (línea 48) — para `useAuth()`.
- **R-DEPS-8 (PASS)**: `zustand@^5.0.0` YA está (línea 52) — para `useAuthStore`.
- **R-DEPS-9 (PASS)**: `@playwright/test@^1.48.0` + `@axe-core/playwright@^4.10.0` YA están (líneas 55-56) — para e2e + a11y.
- **R-DEPS-10 (PASS)**: `bcryptjs@^2.4.3` YA está (línea 36) — F3.1 NO usa bcrypt directamente (kiosko PIN sí, pero eso es F2.3).

**Decisión técnica (ver §8)**: F3.1 NO requiere nuevas dependencias. Todo el stack (RHF + Zod + resolvers + Label + i18n + swr + zustand) ya está en el package.json por F2.1+F2.2. Cero `npm install` post-commit.

### 2.9 i18n locales (apps/electron-sucursal/src/renderer/i18n/locales/)

**Verificado**:
- **R-I18N-1 (PASS)**: 7 namespaces cargados en `i18n/index.ts:34`: common, auth, operacion, caja, facturacion, sync, errors.
- **R-I18N-2 (PASS)**: `auth.json` YA tiene keys relevantes para login: `loginTitle`, `logout`, `email`, `password`, `submit`, `sessionExpired`, `lockout`, `invalidCredentials`, `rememberMe`, `forgotPassword` (10 keys). Plan.md:1278-1281 no exige ninguna key nueva.
- **R-I18N-3 (PASS)**: `errors.json` tiene `networkError`, `serverError`, `validationError`, `unauthorized`, `forbidden`, `notFound`, `timeout`, `unknown` (8 keys para error mapping).
- **R-I18N-4 (PASS)**: `common.json` tiene `loading`, `error`, `retry`, `close`, `save`, `cancel`, `back`, `next`, `statusBar.*` (9 keys). Login NO requiere keys nuevas en common.
- **R-I18N-5 (FAIL — F3.1 lo agrega)**: NO hay keys para `validation.email.invalid`, `validation.password.minLength`, `validation.password.required`. F3.1 agrega 3-5 keys a `auth.json` para validation messages (inline en LoginForm).

**Decisión técnica (ver §8)**: F3.1 agrega 3-5 keys de validation en `auth.json`. NO requiere nuevo namespace. Mantiene el principio F2.1 DEC-ELEC-06 (un namespace por bounded context).

### 2.10 Backend API surface (consumer anchors para F3.1)

Verificado contra `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-583` y `schemas/auth.py`:

- `POST /api/v1/auth/login` (auth.py:148-307) — `LoginRequest{email,password}` (EmailStr + min_length:8 + max_length:128) → `TokenPair{access_token, refresh_token, token_type, expires_in}` + cookie `parkos_session` httponly+secure+samesite=lax (auth.py:291-299). Errores: `401 invalid_credentials` (auth.py:188-191, 248-251) O `429 account_locked` con `Retry-After: minutos*60` (auth.py:219-228).
- `GET /api/v1/auth/me` (auth.py:419-583) — `AuthMeResponse{user: UserItem{uuid, email, nombre, apellido, rol}, sucursal: SucursalItem{uuid, nombre, prefijo_nombre}, sucursales_permitidas: list[SucursalItem], permisos: list[str], expires_at: ISO 8601 UTC}`. Errores: `404 not_found` (antienumeration, auth.py:454-458).

**Verificado PASS**:
- **R-BE-1 (PASS)**: `POST /auth/login` EXISTE en backend con cookie `parkos_session` y shape `TokenPair`. Antienumeration 401 implementado.
- **R-BE-2 (PASS)**: `GET /auth/me` EXISTE con shape `AuthMeResponse` que `useAuth()` ya consume (auth.py:295-321 vs useAuth.ts:33-39).
- **R-BE-3 (PASS)**: HU-F1.2 ya shipped en Fase 1 — `pending.md:23` confirma "Backend /auth/login + /auth/me — HU-F1.2 ya shipped".
- **R-BE-4 (PASS)**: `configuracion_seguridad` configurable per-branch (max_intentos_login, minutos_bloqueo_login) — F3.1 NO crea esta tabla; solo la consume.

**Decisión técnica (ver §8)**: F3.1 NO crea endpoints backend. Consume los 2 existentes. NO requiere backend changes.

### 2.11 ui-kit exports (apps/ui-kit/src/index.ts)

**Verificado**:
- **R-UIKIT-1 (PASS)**: `apps/ui-kit/src/index.ts` exporta `Button + cn + tokens` (F2.1 DEC-ELEC-08).
- **R-UIKIT-2 (PASS)**: subpath exports `./fetch`, `./store`, `./hooks` (ui-kit/package.json:10-12) — permite `import { useAuth } from '@parkos/ui-kit/hooks'`.
- **R-UIKIT-3 (PASS)**: `apps/ui-kit/src/fetch/index.ts` exporta `parkosFetch, parkosFetchRaw, ParkosHttpError, ParkosFetchInit`.
- **R-UIKIT-4 (PASS)**: `apps/ui-kit/src/store/index.ts` exporta `useAuthStore, AuthState`.
- **R-UIKIT-5 (PASS)**: `apps/ui-kit/src/hooks/index.ts` exporta `useAuth, UseAuthReturn, AuthMeResponse`.

**Decisión técnica (ver §8)**: F3.1 importa `@parkos/ui-kit/hooks` (useAuth) + `@parkos/ui-kit/store` (useAuthStore) + `@parkos/ui-kit/fetch` (parkosFetch). NO modifica ui-kit.

## 3. Consumer anchor: endpoints backend + servicios externos

F3.1 NO crea endpoints nuevos. Consume los 2 existentes. Esta sección los documenta como anchor para que la propuesta pueda emitir requirements de comportamiento sin redescubrir el contrato.

### 3.1 POST /api/v1/auth/login

**Request** (`schemas/auth.py` `LoginRequest`):
```python
class LoginRequest(_Base):
    email: EmailStr  # formato email válido
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]
```

**Response 200** (auth.py:303-307):
```python
TokenPair(
    access_token=<jwt HS256 operador-><uuid_sucursal>>,
    refresh_token=<jwt HS256 operador-><uuid_sucursal> type=refresh>,
    expires_in=3600,  # ACCESS_TOKEN_TTL
)
```

**Side effect — cookie `parkos_session`** (auth.py:291-299):
```python
response.set_cookie(
    key="parkos_session",
    value=access,
    httponly=True,    # CRITICAL: NO accesible via JS
    secure=True,      # solo HTTPS (en dev: localhost http OK si same-origin)
    samesite="lax",   # CSRF mitigation cross-site safe
    max_age=ACCESS_TOKEN_TTL,  # 3600s
    path="/",
)
```

**Errores**:
- `401 invalid_credentials` (auth.py:188-191 — email desconocido; auth.py:248-251 — password incorrecta). Mismo shape para ambos, antienumeration.
- `429 account_locked` (auth.py:219-228) — cuando `count(fallido in window) >= max_intentos`. Header `Retry-After: minutos*60`. Body: `{"error": "account_locked", "retry_after_seconds": minutos*60}`.
- `422` — payload Zod-falla (email mal formato o password < 8). NO debería ocurrir en cliente si Zod valida antes.

**Idempotency**: `parkosFetch` SKIP `Idempotency-Key` para `/auth/login` (parkosFetch.ts:106 — `isLoginEndpoint = url.includes('/auth/login')`). El endpoint es idempotente por sí mismo (bcrypt determinístico + INSERT `prod.login` row). El cliente hace POST directamente con `credentials:'include'` y el navegador gestiona la cookie.

**CRITICAL — credentials:'include'**: el cliente debe setear `credentials: 'include'` en el `fetch` para que el navegador ACEPTE la cookie `Set-Cookie` y la ENVÍE en requests subsiguientes (`GET /auth/me`). Sin esto, la cookie se setea pero NO se persiste — el siguiente `/auth/me` viaja sin auth y el backend responde 404 not_found.

### 3.2 GET /api/v1/auth/me

**Request**: header `Authorization: Bearer <access_token>` (enviado automáticamente por `parkosFetch` línea 92-96). Cookie `parkos_session` también aceptada (backend lee JWT de header O cookie).

**Response 200** (auth.py:577-583):
```typescript
interface AuthMeResponse {
  user: UserItem;             // {uuid, email, nombre, apellido, rol}
  sucursal: SucursalItem;     // {uuid, nombre, prefijo_nombre} — JWT-pinned
  sucursales_permitidas: SucursalItem[];  // todas las activas, sin limit(1)
  permisos: string[];          // [] si ninguno
  expires_at: string;          // ISO 8601 UTC desde JWT exp claim
}
```

**Errores** (auth.py:444-458):
- `404 not_found` — CUALQUIER JWT failure mode colapsa a 404 (antienumeration). Sin distinción entre missing/malformed/expired/invalid signature/user-gone.

**Hidratación post-login (F3.1 flow)**:
1. `Login.tsx` submit → `fetch('/api/v1/auth/login', {credentials:'include', ...})` con `parkosFetch` raw (no Authorization Bearer pre-login — DEC-F3.1-05).
2. Backend responde 200 con `TokenPair` body + `Set-Cookie parkos_session` header.
3. `Login.tsx` parsea body → `useAuthStore.getState().setTokens(access, refresh, expires_in)`.
4. `useAuth()` SWR detecta nuevo accessToken (key cambia de `null` a `'/auth/me'`) → dispara `parkosFetch('/auth/me')` con `Authorization: Bearer <new_access>` + cookie que el navegador auto-envía.
5. `useAuth()` retorna `{user, sucursal, sucursalesPermitidas, permisos, expiresAt, isAuthenticated: true}`.
6. `Login.tsx` `useEffect` con `isAuthenticated && data?.user && !isLoading` → `navigate('/')`.

## 4. parkosFetch existente en apps/ui-kit (REUTILIZAR, NO duplicar)

### 4.1 Capability matrix para F3.1

| Capability | Necesario para F3.1 | parkosFetch provee | Notas |
|---|---|---|---|
| POST /auth/login con credentials:'include' | ✅ | ✅ via parkosFetchRaw | parkosFetch NO setea credentials default; F3.1 lo pasa explícito |
| `Authorization: Bearer` en /auth/me post-login | ✅ | ✅ automático desde authStore | post-setTokens |
| Retry 5xx + 408 | ✅ (low priority en login) | ✅ automático | login tiene 1 intento + backoff si 5xx |
| Refresh-once 401 (Mutación a /auth/me) | ✅ | ✅ automático | refresh único post-login si /auth/me da 401 |
| Idempotency-Key | ❌ SKIP para /auth/login | ✅ skip automático | parkosFetch.ts:106 |
| Timeout 30s default | ✅ | ✅ | login puede colgarse en kiosko desatendido |
| Zod validation LoginRequest/Response | ✅ opcional | ✅ via schema param | F3.1 usa Zod LOCAL (form), no schema para response |

### 4.2 Login UI usa RHF + Zod (NO parkosFetch Zod)

F3.1 usa **Zod LOCAL** (en el frontend) para validar el form ANTES de submit, no para validar la response. Razones:
- Validación del form (`email` formato + `password` min 8) es UX (mostrar mensaje inline al operador) → Zod local + `formState.errors.email.message`.
- Validación de la response (TokenPair) es CONTRACT — pero el backend ya valida via Pydantic. Si shape drift, TS strict + `parkosFetch<TokenPair>` cast catches.
- Zod validation en boundary via `parkosFetch<T>(url, schema)` es DEC-FETCH-05 OPTIONAL — F3.1 lo deja como follow-up si hace falta (low priority, no documentado en plan.md:1274-1305).

### 4.3 Estrategia de fetch para /auth/login

```typescript
async function postLogin(email: string, password: string): Promise<TokenPair> {
  const res = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
    credentials: 'include',  // CRITICAL: cookie httpOnly round-trip
  });
  if (!res.ok) {
    if (res.status === 401) throw new InvalidCredentialsError();
    if (res.status === 429) {
      const retryAfter = Number(res.headers.get('Retry-After') ?? '0');
      throw new AccountLockedError(retryAfter);
    }
    throw new ParkosHttpError(res.status, await res.text(), res.url);
  }
  return res.json() as Promise<TokenPair>;
}
```

**Notas críticas**:
- Usa `fetch` raw, NO `parkosFetch`, porque (a) NO queremos Authorization Bearer pre-login, (b) queremos `credentials:'include'` explícito, (c) queremos leer `Retry-After` header.
- `InvalidCredentialsError` se mapea a `errors.invalidCredentials` (auth.json:9).
- `AccountLockedError(retryAfter)` se surfacea como `<p role="alert">{t('lockout')}</p>` — F3.2 agrega countdown UI.

## 5. Stack técnico objetivo

### 5.1 Dependencias (apps/electron-sucursal/package.json)

**YA EXISTEN** (F2.1 + F2.2 + F2.3 — cero npm install):
- `react-hook-form@^7.53.0` (línea 45).
- `zod@^3.23.8` (línea 51).
- `@hookform/resolvers@^3.9.0` (línea 23).
- `@radix-ui/react-label@^2.1.0` (línea 27) — FormLabel shadcn.
- `react-router-dom@^6.27.0` (línea 47) — `<Route path="/login">`.
- `react-i18next@^15.0.2` + `i18next@^23.15.2` (líneas 41, 46).
- `swr@^2.2.5` (línea 48).
- `zustand@^5.0.0` (línea 52).
- `@playwright/test@^1.48.0` + `@axe-core/playwright@^4.10.0` (líneas 55-56).
- `@radix-ui/react-toast@^1.2.2` (línea 32) — para toast de sessionExpired si redirect from auth:cleared event.

**NO REQUERIDAS** (F3.1 NO agrega):
- bcryptjs (F2.3 kiosko PIN, no login).
- electron-updater / electron-log / electron-store (F2.3 main process).
- escpos-usb (F5.1+ impresión, no login).

### 5.2 Versiones objetivo

- react-hook-form@^7.53.0.
- zod@^3.23.8.
- @hookform/resolvers@^3.9.0.
- react@^18.3.1 (renderer).
- typescript@^5.6.2.

### 5.3 Tooling

- Vitest 2.1.x con jsdom env (unit, F2.1).
- `@testing-library/react@^16.0.1` (F2.2) — render Login en jsdom + assertions.
- Playwright 1.48.x + `_electron.launch` (e2e, F2.1+F2.2).
- axe-core 4.10.x (a11y, F2.1 RNF-022).

## 6. Decisiones arquitectónicas (DEC-F3.1-NN × 10)

### 6.1 DEC-F3.1-01 — Feature folder `src/features/auth/{pages,hooks,components}/`

**DECISION**: F3.1 crea `apps/electron-sucursal/src/features/auth/pages/Login.tsx` + `src/features/auth/components/LoginForm.tsx`. NO se monta en `src/renderer/components/` (que es para componentes reutilizables cross-feature).

**RATIONALE**: Atomic Design + Feature Slicing (F2.1 DEC-ELEC-08 + ops reference). Cada bounded context vive en su propia carpeta. `apps/electron-sucursal/src/features/{auth,caja,facturacion,operacion,...}` poblado incrementalmente en Fase 3+ (pending.md §5). F3.3 (turno) vivirá en `features/caja/pages/{AbrirTurno,CerrarTurno}.tsx`.

### 6.2 DEC-F3.1-02 — Container/Presentational split (Login vs LoginForm)

**DECISION**: `Login.tsx` (container) maneja RHF + Zod resolver + onSubmit + parkosFetch + useAuth + useNavigate. `LoginForm.tsx` (presentational) recibe `{form, onSubmit, isSubmitting, error}` via props.

**RATIONALE**: Container/Presentational pattern (F2.1 DEC-ELEC-09 + Atomic Design). El container es testeable con mocks (fetch + useAuth); el presentational es testeable con `@testing-library/react` sin mocks. Plan.md:1289 explicito: "Login (page, contenedor: RHF+Zod, llama parkosFetch); LoginForm (presentacional, dos campos + botón)".

### 6.3 DEC-F3.1-03 — credentials:'include' para cookie httpOnly round-trip

**DECISION**: El `fetch` para `POST /auth/login` y todos los `parkosFetch` subsecuentes llevan `credentials: 'include'` (default en parkosFetch? NO — se setea explícito en Login.tsx; parkosFetch NO setea credentials por default).

**RATIONALE**: La cookie `parkos_session` (httponly+secure+samesite=lax) requiere que el cliente ACEPTE el `Set-Cookie` (origin localhost:5173 acepta same-origin; cross-origin requiere `SameSite=None; Secure`) Y que la ENVÍE en requests subsiguientes. `credentials:'include'` cubre ambos. Si se omite, la cookie se setea en la respuesta pero NO se persiste (Fetch spec: omit credentials = no cookie jar write).

### 6.4 DEC-F3.1-04 — Login via HTTP directo (NO IPC bridge)

**DECISION**: F3.1 NO agrega nuevos métodos IPC (`bridge.auth.login`, `bridge.auth.logout`, etc.). Login fluye por HTTP directo vía `fetch` (raw, no parkosFetch) con `credentials:'include'`.

**RATIONALE**: IPC bridge es para capabilities privileged que requieren main process (print, usb, kiosk, app quit, electron-store). Auth es HTTP puro — el navegador gestiona la cookie via `credentials:'include'` sin main process involvement. Agregar IPC sería over-engineering + surface area extra sin benefit. F2.2 ya wireó `bridge.authStore.{get,set,delete}` para persistencia (authStore Zustand) — F3.1 consume indirectamente via `useAuthStore.setTokens`.

### 6.5 DEC-F3.1-05 — Login usa `fetch` raw, NO `parkosFetch`

**DECISION**: `Login.tsx` usa `fetch` raw (no `parkosFetch`) para `POST /auth/login`. Razones: (a) NO queremos Authorization Bearer pre-login (no existe token), (b) queremos leer `Retry-After` header en 429, (c) queremos `credentials:'include'` explícito sin que parkosFetch intercepte.

**RATIONALE**: parkosFetch está optimizado para el 95% de los casos (auth header + sucursal header + idempotency + retry + refresh). El endpoint de login es el caso exceptional — no es parte del "data plane autenticado", es la PUERTA al data plane. Mantener raw fetch para login preserva la semántica: "login es anonimo, todo lo demas es autenticado".

### 6.6 DEC-F3.1-06 — Validación Zod local en form (NO parkosFetch schema)

**DECISION**: F3.1 usa Zod local en el form (`z.object({email: z.string().email(), password: z.string().min(8)})`) vía `@hookform/resolvers/zod`. NO usa `parkosFetch<TokenPair>(url, init, zodSchema)` para validar la response.

**RATIONALE**: Validación del form es UX (mensaje inline al operador). Validación de la response es contract — pero el backend ya valida via Pydantic. Si shape drift entre backend y frontend, TS strict + cast catches en compile-time. Zod en runtime es defense-in-depth EXTRA (DEC-FETCH-05) que F3.1 NO exige.

### 6.7 DEC-F3.1-07 — Redirect a `/` tras `useAuth().isAuthenticated && data?.user`

**DECISION**: `Login.tsx` espera `useAuth()` a retornar `data.user` (no solo `isAuthenticated`) antes de `navigate('/')`. El `useEffect` con deps `[isAuthenticated, data?.user, isLoading]` garantiza que el operador nunca llega a `/` con `user: null`.

**RATIONALE**: Hidratación transaccional — el operador llega a `/` con sesión + user + sucursal + permisos TODOS resueltos. Si el componente navega con `isAuthenticated && isLoading`, hay un flash de "sesión no iniciada" en el destino (F3.3+ dashboards dependen de `useAuth().user.sucursal`). Plan.md:1280 verbatim: "authStore se hidrata desde GET /auth/me (useAuth().user.sucursal es el uuid de la sede)".

### 6.8 DEC-F3.1-08 — Anti-enumeración via UI message único

**DECISION**: 401 (cualquier causa) → muestra `<p role="alert">{t('invalidCredentials')}</p>` (auth.json:9). NO distinción entre "email no existe" / "password incorrecta". 429 → `<p role="alert">{t('lockout')}</p>` (auth.json:8). 500/network → `<p role="alert">{t('errors.serverError')}</p>` (errors.json:3).

**RATIONALE**: Backend ya colapsa 401 a `errors.invalid_credentials` único (auth.py:159-191). Frontend matchea. Anti-enumeration es cross-layer (backend + frontend). Plan.md:1281 verbatim: "401 muestra un mensaje único (errors.invalid_credentials), sin distinguir si el email existe o no (anti-enumeración)".

### 6.9 DEC-F3.1-09 — Auto-redirect a `/login` cuando `parkos:auth:cleared` event fires

**DECISION**: F3.1 NO crea el redirect logic — usa el evento `parkos:auth:cleared` que `useAuth()` ya emite (useAuth.ts:67-69). F3.3+ agregan un `<AuthGuard>` que escucha este evento y dispara `navigate('/login?next=...')`. F3.1 NO requiere AuthGuard porque Login está standalone.

**RATIONALE**: Separación de concerns. Login page NO necesita auth-guard (es el entry point). Los dashboards sí. Forward: F3.3+ agregan `<AuthGuard>` que envuelve `<Routes>` excepto `/login`. Plan.md:1302: "Login redirige a / (o a la sesión activa) tras hidratar authStore".

### 6.10 DEC-F3.1-10 — e2e 3 escenarios: login OK con cookie, refresh transparente, logout

**DECISION**: F3.1 entrega `apps/electron-sucursal/e2e/auth/login.spec.ts` con 3 tests:
1. **login-ok-cookie**: submit email+password válidos → cookie `parkos_session` set + redirect a `/` + `useAuth().user.email === <test email>`.
2. **refresh-transparente**: setTokens via authStore, advance fake timers 50min, verificar SWR revalida `/auth/me` (useAuth.refreshInterval: 5min; en realidad refresh es 5min NO 50min — refresh transparente aquí significa: 401 en otra llamada dispara refresh-once). Plan.md:1295 dice "refresh automático" — interpretado como refresh-once en 401 (F2.2 DEC-FETCH-03), NO como el `refreshInterval` de useAuth.
3. **logout**: F3.1 NO implementa logout UI per se (F3.3+/forward), pero el test verifica que `useAuthStore.clear()` setea tokens a null y que un segundo `/auth/me` retorna 404 → `useAuth()` limpia store + emite `parkos:auth:cleared`. F3.3 entrega logout button (placeholder o via HU posterior).

**RATIONALE**: Plan.md:1295 verbatim. Sandbox F.6 precedent: e2e con `_electron.launch` puede SKIP en npm 11.16.0 (F2.2 archive report G8). F3.1 e2e va a SKIP en el mismo sandbox — documentado en §11 como deviation D-env, NO project defect.

## 7. Riesgo y mitigaciones

| # | Risk | Severity | Mitigación |
|---|---|---|---|
| R1 | **CSRF attack en /auth/login** — atacante hace que el operador submita login via cross-site form | MEDIUM | DEC-F3.1-03: `credentials:'include'` + `SameSite=Lax` en cookie bloquea cross-site POST (el navegador NO envía la cookie en cross-site form submissions). Backend CORS config (no F3.1 scope) verifica `Origin` header. |
| R2 | **Cookie theft via XSS** — atacante inyecta script que lee `document.cookie` | LOW (mitigado) | DEC-F3.1-03: `HttpOnly` flag en `parkos_session` impide lectura via JS. Atacante puede inyectar scripts pero NO puede leer la cookie. Mitigación adicional: CSP estricto en renderer (F2.1 baseline). |
| R3 | **Cookie no persiste en reload** — operador refresca `/login` y la cookie se pierde | LOW (NO debería pasar) | El navegador persiste cookies httponly hasta `Max-Age` (3600s). El operador puede refrescar y la cookie sigue. `useAuth()` SWR re-fetcha `/auth/me` con la cookie auto-enviada → re-hidrata store. |
| R4 | **Race condition entre setTokens y useAuth()** — `useAuth()` SWR dispara `/auth/me` antes de que `setTokens` complete | LOW | DEC-F3.1-07: el `useEffect` espera `data?.user` (no solo `isAuthenticated`). Zustand setState es síncrono (no async), por lo que el SWR key cambia en el siguiente render — sin race. |
| R5 | **Login form expuesto a timing attacks** — atacante mide latencia para inferir email existe | LOW | Backend usa `bcrypt.checkpw` (~250ms) que es dominantly-costly vs DB lookup (~10ms). Diferencia enmascarada por bcrypt cost. Plan.md:1281 explícito: anti-enumeration. |
| R6 | **Zod schema drift frontend/backend** — `password: min(8)` vs backend `min_length:8` mismatch | LOW | Plan.md:1291 verbatim: `z.string().min(8)`. Backend `schemas/auth.py:LoginRequest` StringConstraints min_length:8 max_length:128. Match. Si backend cambia, frontend Zod local NO rompe (devuelve 422) pero UX degrada. |
| R7 | **password en memoria via form state** — RHF storea password en formState | LOW | RHF mantiene form state en memoria del componente. Cuando el componente unmounts (redirect a /), formState garbage-collected. NO persiste a electron-store. Aceptable para kiosko desatendido (post-shift el proceso se reinicia). |
| R8 | **e2e sandbox F.6 SKIP** — playwright `_electron` no arranca en sandbox | MEDIUM (env) | F2.2 archive precedent: SKIPPED en npm 11.16.0. F3.1 e2e va a SKIP misma manera. Documentado como D-env en verify-report. Unit tests (vitest + @testing-library/react sobre Login.tsx mockeado) cubren el camino crítico. |

**Riesgos identificados y cerrados**: 8/8 con mitigación explícita. 0 KNOWN-MISSING.

## 8. Análisis de impacto (no hay conflicto arquitectónico)

F3.1 NO tiene un conflicto arquitectónico mayor con Fase 2. Cada bloque de F3.1 opera en un namespace distinto y CONSUME primitives ya existentes:

- **Login page (container)**: `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (NEW). Consume: `useAuth()`, `useAuthStore()`, `fetch` raw, `useNavigate`, `useTranslation`.
- **LoginForm (presentational)**: `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (NEW). Consume: shadcn `Form`, `FormField`, `FormItem`, `FormLabel`, `FormControl`, `FormMessage`, `Input`, `Button`. RHF + Zod.
- **Route /login**: `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY — agrega `<Route path="/login" element={<LoginPage />} />`).
- **i18n keys**: `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (MODIFY — agrega 3-5 validation keys).
- **e2e tests**: `apps/electron-sucursal/e2e/auth/login.spec.ts` (NEW). Consume: Playwright + `_electron.launch`.

**NO modifica**:
- `apps/electron-sucursal/electron/main.ts` — F3.1 NO agrega IPC handlers.
- `apps/electron-sucursal/electron/preload.ts` — F3.1 NO expone nuevos métodos bridge.
- `apps/electron-sucursal/electron/bridge.d.ts` — F3.1 NO agrega tipos bridge.
- `apps/ui-kit/**` — F3.1 NO modifica ui-kit; consume primitives via subpath exports.
- `apps/electron-sucursal/src/renderer/components/ui/**` — F3.1 reusa Form/Input/Button ya existentes.
- `apps/electron-sucursal/src/renderer/i18n/index.ts` — F3.1 NO agrega namespaces.
- `apps/electron-sucursal/e2e/{scaffold,auth/parkos-fetch,auth/bridge,a11y/wcag-2.1-aa,lifecycle,kiosko}.spec.ts` — F3.1 NO toca los e2e existentes.
- `backend/**` — F3.1 NO toca backend; consume /auth/login + /auth/me existentes (HU-F1.2 shipped).

## 9. Decisiones arquitectónicas (DEC-F3.1-NN) — segundo pase con justificación extendida

### 9.1 DEC-F3.1-01 (feature folder) vs alternativas

**Alternativa A**: Montar Login en `src/renderer/components/` (donde está StatusBar).
- Pros: ubicación familiar.
- Cons: mezcla UI reutilizable cross-feature (Button, StatusBar) con pages de bounded contexts. Plan.md:1289 explícito: "Login (page, contenedor)" → page ≠ component.

**Alternativa B (DECIDIDA)**: Feature folder `src/features/auth/`.
- Pros: bounded context isolation; F3.3 vive en `features/caja/`; F5+ en `features/facturacion/`. Atomic Design + Feature Slicing.
- Cons: nueva carpeta no usada previamente (F2.1+F2.2+F2.3 no crearon features, solo components/).

**Razón**: Atomic Design (F2.1 DEC-ELEC-09) + clean architecture. Pages = containers con lógica; components = presentacionales reusables. F3.1 setea el patrón para Fase 3 entera.

### 9.2 DEC-F3.1-04 (HTTP directo vs IPC bridge) vs alternativas

**Alternativa A**: IPC bridge `bridge.auth.login(email, password)` que el main process invoca el backend.
- Pros: ocultaría la URL del backend al renderer (security through obscurity).
- Cons: (a) over-engineering — el renderer YA necesita `parkosFetch` para todo lo demás, tener login via IPC es asymmetric; (b) main process no gana nada (HTTP es HTTP); (c) `credentials:'include'` es Browser API, NO IPC — el main process tendría que inyectar cookies manualmente via electron session API, complicando enormemente el código.

**Alternativa B (DECIDIDA)**: HTTP directo via `fetch` con `credentials:'include'`.
- Pros: simple; usa el Browser cookie jar estándar; simétrico con el resto del data plane; cero IPC surface extra.
- Cons: el renderer conoce la URL del backend (via `PARKOS_API_BASE` env en build time — ya está en Fase 2). Aceptable porque el backend NO es un secreto.

**Razón**: YAGNI + DRY. IPC bridge es para capabilities privileged. Auth es HTTP estándar.

### 9.3 DEC-F3.1-05 (`fetch` raw vs `parkosFetch`) vs alternativas

**Alternativa A**: `parkosFetch<TokenPair>('/auth/login', {method:'POST', body, credentials:'include'})`.
- Pros: tipado genérico + Zod opcional.
- Cons: parkosFetch inyecta Authorization Bearer desde authStore (línea 92-96). Pre-login, accessToken es null → NO header (OK). PERO parkosFetch también inyecta Idempotency-Key en POST mutacionales EXCEPTO /auth/login (línea 105-109 — `isLoginEndpoint` check). El skip ya está implementado. ¿Por qué no usar parkosFetch? (a) queremos leer `Retry-After` header en 429 → parkosFetch NO expone headers raw, solo `res.ok` o throws; (b) queremos custom error mapping (`InvalidCredentialsError`, `AccountLockedError` con retryAfter) que parkosFetch colapsa en `ParkosHttpError`.

**Alternativa B (DECIDIDA)**: `fetch` raw + custom error mapping.
- Pros: control total sobre headers + error semantics; NO bypass parkosFetch (es opt-in para casos específicos).
- Cons: duplicamos el patrón de `credentials:'include'` + Content-Type + JSON.stringify. ~10 LOC más que usar parkosFetch.

**Razón**: Login es un caso exceptional del data plane. El cost de duplicar ~10 LOC es menor que el cost de hacer parkosFetch polimórfico para soportar este caso. parkosFetch optimiza el 95% de los casos; login es el 5% exceptional.

### 9.4 DEC-F3.1-07 (redirect con data.user) vs alternativas

**Alternativa A**: `navigate('/')` inmediatamente post-setTokens.
- Pros: latencia mínima.
- Cons: F3.3+ dashboards renderizan con `user: null` durante el primer SWR fetch → flash de "sesión no iniciada".

**Alternativa B (DECIDIDA)**: `useEffect` espera `isAuthenticated && data?.user && !isLoading`.
- Pros: UX transaccional — operador llega a `/` con todo resuelto.
- Cons: ~100-300ms extra de loading en el redirect (SWR fetch /auth/me). Aceptable para login flow (operador espera feedback visual).

**Razón**: Hidratación transaccional es critical para UX profesional. Flash de "sesión no iniciada" es UX amateur. Plan.md:1280 verbatim: "authStore se hidrata desde GET /auth/me".

## 10. Atomic tasks T1..T4 con budgets LOC

Cada task es **atómica** (commiteable independientemente con tests verde), pero se ejecutan en orden T1 → T2 → T3 → T4.

### 10.1 T1 — Login page (container) + LoginForm (presentational) con RHF+Zod

**Budget**: ~120 LOC production + ~80 LOC tests = **~200 LOC**.

**Archivos**:
- `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (NEW, ~60 LOC — presentacional).
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (NEW, ~60 LOC — container con RHF+Zod+fetch+useAuth+useNavigate).
- `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (NEW, ~50 LOC — vitest + @testing-library/react).
- `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` (NEW, ~30 LOC — render presentacional).
- `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (MODIFY, agregar 5 validation keys).

**Commit message**: `feat(auth): adicionar Login page con RHF+Zod (email/password) + LoginForm presentacional + 5 i18n validation keys`

**Acceptance** (G1, G2, G4 — §11): RHF+Zod valida form; 401 → `invalidCredentials`; 429 → `lockout`; 5 i18n keys agregadas; vitest unit tests verde.

### 10.2 T2 — integrar POST /auth/login con credentials:'include'

**Budget**: ~30 LOC production + ~50 LOC tests = **~80 LOC**.

**Archivos**:
- `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (NEW, ~30 LOC — fetch raw + error mapping `InvalidCredentialsError` + `AccountLockedError`).
- `apps/electron-sucursal/src/features/auth/api/loginApi.test.ts` (NEW, ~50 LOC — MSW handler para 200/401/429 + custom error assertions).
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY, +5 LOC — `await postLogin(...)` en `onSubmit` + setTokens).

**Commit message**: `feat(auth): integrar POST /auth/login con credentials:'include' + error mapping 401/429`

**Acceptance** (G3, G5 — §11): `fetch` con `credentials:'include'`; 200 → setTokens + redirect; 401 → `InvalidCredentialsError`; 429 → `AccountLockedError(retryAfter)`; MSW tests verde.

### 10.3 T3 — Login redirige a / tras hidratar authStore desde /auth/me

**Budget**: ~20 LOC production + ~30 LOC tests = **~50 LOC**.

**Archivos**:
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY, +10 LOC — `useEffect([isAuthenticated, data?.user, isLoading])` → `navigate('/')`).
- `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY, +5 LOC — `<Route path="/login" element={<LoginPage />} />`).
- `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (MODIFY, +30 LOC — test redirect post-hidratación).

**Commit message**: `feat(router): adicionar ruta /login con redirect a / post-hidratación useAuth()`

**Acceptance** (G4 — §11): `<Route path="/login">` registrado en App.tsx; `useEffect` espera `data.user` antes de navigate; vitest redirect test verde.

### 10.4 T4 — e2e login.spec.ts (3 casos)

**Budget**: ~80 LOC tests.

**Archivos**:
- `apps/electron-sucursal/e2e/auth/login.spec.ts` (NEW, ~80 LOC — login-ok-cookie + refresh-transparente + logout).

**Commit message**: `test(electron): adicionar 3 e2e login (cookie httpOnly + refresh transparente + logout)`

**Acceptance** (G6 — §11): 3 escenarios per plan.md:1295 verbatim. Sandbox F.6 precedent: SKIPPED en npm 11.16.0 (F2.2 G8 archive report) — F3.1 e2e va a correr misma suerte, documentado como deviation D-env en verify-report.

### 10.5 Resumen de budgets

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 Login + LoginForm | 120 | 80 | 200 |
| T2 postLogin + error mapping | 30 | 50 | 80 |
| T3 redirect + /login route | 20 | 30 | 50 |
| T4 e2e 3 scenarios | 0 | 80 | 80 |
| **TOTAL** | **170** | **240** | **410** |

Total real ~190 LOC production matches plan.md:1297 verbatim (~170 production + ~20 JSDoc/configs = ~190).

## 11. Descomposición en clusters atómicos

F3.1 se descompone en **1 cluster** (C1) con orden interno T1 → T2 → T3 → T4.

### 11.1 C1: Login flow end-to-end (T1+T2+T3+T4)

**Archivos**:
- `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (~60 LOC).
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (~75 LOC — 60 base + 5 T2 + 10 T3).
- `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (~30 LOC).
- `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (~80 LOC — 50 T1 + 30 T3).
- `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` (~30 LOC).
- `apps/electron-sucursal/src/features/auth/api/loginApi.test.ts` (~50 LOC).
- `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (MODIFY, +5 keys).
- `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY, +5 LOC).
- `apps/electron-sucursal/e2e/auth/login.spec.ts` (~80 LOC).

**Total C1**: ~190 LOC production + ~240 LOC tests = **~430 LOC**.

Plan 190 LOC matches: 190 LOC production = 170 authored + 20 JSDoc/configs.

### 11.2 Orden de ejecución

T1 → T2 → T3 → T4 (mandatory). T1 antes de T2 porque T2 integra el `postLogin` en el `onSubmit` de T1. T2 antes de T3 porque T3 agrega redirect post-setTokens (T2 setea tokens). T3 antes de T4 porque e2e tests requieren Login.tsx completo (route + form + api + redirect).

## 12. Acceptance gates pre-flight

6 gates que deben pasar ANTES de mergear F3.1 a main.

| # | Gate | Mecanismo | Source |
|---|---|---|---|
| G1 | RHF+Zod valida `email: z.string().email()` y `password: z.string().min(8)` con messages inline | vitest Login.test.tsx con @testing-library/react | T1 |
| G2 | 401 → muestra `t('invalidCredentials')` único, sin distinción email/password | vitest Login.test.tsx mock 401 response | T1 |
| G3 | `POST /auth/login` enviado con `credentials:'include'` + Content-Type JSON | vitest loginApi.test.ts con MSW handler assert request | T2 |
| G4 | `authStore.setTokens(access, refresh, expires_in)` + `useAuth().data.user` hidrata antes de `navigate('/')` | vitest Login.test.tsx mock 200 + assert setTokens spy + useEffect fires | T2 + T3 |
| G5 | 429 → `AccountLockedError(retryAfter)` + muestra `t('lockout')` | vitest loginApi.test.ts mock 429 + Retry-After header | T2 |
| G6 | 3 e2e scenarios verde (login-ok-cookie, refresh-transparente, logout) | playwright e2e `_electron` | T4 |

**Estado pre-flight**: 0/6 PASS al inicio (no implementado). Target 6/6 PASS post-implementación.

**Sandbox F.6 precedent**: 6/10 gates SKIPPED en F2.1 + F2.2 + F2.3 archive (npm 11.16.0 refuses workspace:*). F3.1 e2e (G6) va a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect.

## 13. Pre-flight checks ya cerrados

10 checks verificados antes de empezar implementación:

| # | Check | Source | Result |
|---|---|---|---|
| 1 | plan.md HU-F3.1 existe con 4 tasks + 4 atomic + 190 LOC | plan.md:1274-1305 | PASS |
| 2 | Backend `POST /auth/login` existe con cookie `parkos_session` + 401/429/200 | auth.py:148-307 | PASS |
| 3 | Backend `GET /auth/me` existe con shape `AuthMeResponse` | auth.py:419-583 + schemas/auth.py | PASS |
| 4 | HU-F1.2 shipped Fase 1 con login + me + lockout pre-check | pending.md:23 + auth.py module docstring | PASS |
| 5 | `react-hook-form@^7.53.0` + `zod@^3.23.8` + `@hookform/resolvers@^3.9.0` ya en deps | package.json:23, 45, 51 | PASS |
| 6 | `@radix-ui/react-label@^2.1.0` ya en deps (FormLabel shadcn) | package.json:27 | PASS |
| 7 | `react-router-dom@^6.27.0` ya en deps (Route /login) | package.json:47 | PASS |
| 8 | `useAuth()` SWR ya hidrata desde /auth/me con refresh 5min | useAuth.ts:53-86 + parkosFetch.ts | PASS |
| 9 | `useAuthStore` Zustand ya persiste via electron-store IPC | authStore.ts:71-94 | PASS |
| 10 | auth.json i18n namespace ya tiene 10 keys (loginTitle, email, password, submit, invalidCredentials, lockout, etc.) | auth.json:1-13 | PASS |

Result: 10/10 PASS. Pre-flight gate PASS. F3.1 ready for sdd-propose. 0 KNOWN-MISSING.

## 14. Out of scope Fase 3

F3.1 NO incluye (explícitamente deferido a Fase 3+):

- **Lockout countdown UI** — F3.2 lo entrega (useCountdown hook + 429 disable form + countdown).
- **Refresh pre-flight antes de POST /facturacion/* + POST /caja/arqueo** — F3.2 (50min auto-refresh).
- **Logout button UI** — F3.3+ (placeholder o HU posterior; F3.1 solo verifica clear() en e2e).
- **Recuperación de password / forgotPassword** — fuera Fase 3 (futuro).
- **2FA / WebAuthn** — fuera Fase 3 (futuro).
- **Multi-tab login UI** — kiosko single-tab por F2.3 lock (DEC-UPD-07).
- **Turno abrir/cerrar** — F3.3 (AbrirTurno + CerrarTurno + useSesionActiva).
- **AuthGuard component** — F3.3+ (intercepta `parkos:auth:cleared` event → navigate('/login?next=...')).
- **Sucursal selector UI** — el JWT ya pinea sucursal (DEC-F3.1-04 single-branch kiosko).
- **rememberMe checkbox** — auth.json:10 tiene la key pero F3.1 NO la usa (kiosko desatendido, no aplica).
- **forgotPassword link** — auth.json:11 tiene la key pero F3.1 NO la renderiza (out of scope).
- **Backend cambios** — HU-F1.2 shipped en Fase 1 cubre los 2 endpoints; F3.1 NO modifica backend.
- **Refresh-token rotation** — F2.2 cubre (DEC-FETCH-03); F3.1 NO toca.
- **Zod schema validation en boundary via parkosFetch** — DEC-FETCH-05 optional; F3.1 NO exige.

## 15. Forward hooks (a Fase 3+)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.2** (lockout visible + refresh pre-flight) | `AccountLockedError(retryAfter)` de F3.1 → F3.2 useCountdown hook | F3.2 wraps Login.tsx onSubmit con disable form + countdown UI |
| **HU-F3.3** (abrir/cerrar turno) | `useAuth().user.sucursal` + permisos hidratados post-F3.1 | F3.3 AbrirTurno lee `user.sucursal` y `permisos` antes de POST /caja-sesion/sesiones |
| **HU-F3.x** (logout UI) | `useAuthStore.clear()` ya implementado en F2.2 + `parkos:auth:cleared` event | F3.x logout button dispatch clear() + navigate('/login') |
| **HU-F3.x** (AuthGuard) | `parkos:auth:cleared` window event | F3.x AuthGuard escucha evento → navigate('/login?next=...') |
| **HU-F4.x** (catálogos + ocupación) | `useAuth()` + parkosFetch | F4.x lee `user.sucursal` para scoped queries |
| **HU-F11.x** (sync UI) | useAuth (no directo) | F11.x muestra `user.email` en topbar |
| **PR7 backend** (refresh rotation) | authStore + refresh logic (no F3.1) | Detección de reuse jti claim (F2.2 DEC-FETCH-03 cubre sin rotation; rotación es PR7+) |

## 16. Convenciones del proyecto

### 16.1 Commits

- Conventional Commits.
- NO "Co-Authored-By" attribution.
- Formato: `<type>(<scope>): <description>` con type ∈ {feat, fix, test, refactor, docs, chore}, scope ∈ {auth, electron, ui, ops, router}.
- Author: `Parkos Dev <dev@parkos.local>` (F2.1 precedent).

### 16.2 TDD estricto

- Cada test escrito ANTES de la implementación.
- Tests rojos primero, luego código que los hace verde.
- Cobertura >80% exigida en `Login.tsx` + `LoginForm.tsx` + `loginApi.ts`.
- Cobertura >80% en i18n keys (snapshot test del JSON).

### 16.3 Defense in depth

5 capas (XR6 pattern per operations/spec.md:3951 + F2.2 §15.3 + F2.3 §15.3 precedent):

| Layer | Mechanism | Source |
|---|---|---|
| 1 auth | JWT Bearer + cookie httponly SameSite=Lax + bcrypt | backend/.../auth.py:148-583 (F3.1 consumer) |
| 2 engineering | TS strict + noUncheckedIndexedAccess + ESLint flat | tsconfig.* + eslint.config.js (F2.1 baseline) |
| 3 a11y | axe-core WCAG 2.1 AA + FormField aria-invalid + FormMessage role=alert | e2e/a11y/wcag-2.1-aa.spec.ts (F2.1) + F3.1 LoginForm |
| 4 contract | Zod validation form (DEC-F3.1-06) + backend Pydantic | @hookform/resolvers/zod + schemas/auth.py |
| 5 retry-budget | parkosFetch retry 5xx + 401 refresh-once | parkosFetch.ts (F2.2 DEC-FETCH-02/03) — F3.1 NO custom retry en login |

F3.1 NO crea un nuevo REQ-OPS-XR (F3.1 NO es XR-class; las decisiones viven en proposal.md como DEC-F3.1-NN per F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10 + F2.3 DEC-UPD-13 precedent).

### 16.4 Pending.md update

Al archive F3.1:
- Row 1 (HU-F3.1) en `pending.md §1` → marcar ✅ cerrado.
- Total LOC restante → `$LOC - 190` (Fase 3 1/3 cerrado).
- Footer → "Fase 3 1/3 cerrado".

## 17. Estimación total

### 17.1 Production LOC

- C1 (Login + LoginForm + loginApi + redirect + i18n): ~190 LOC production = 170 authored + 20 JSDoc/configs.
- Total production: **~190 LOC**.

### 17.2 Test LOC

- Login.test.tsx (container): ~80 LOC.
- LoginForm.test.tsx (presentational): ~30 LOC.
- loginApi.test.ts (HTTP layer): ~50 LOC.
- e2e/auth/login.spec.ts: ~80 LOC.
- Total tests: **~240 LOC**.

### 17.3 Gran total

~190 LOC production + ~240 LOC tests = **~430 LOC**.

### 17.4 Timeline estimado

| Fase | Duración estimada | Owner |
|---|---|---|
| sdd-propose | 1 sesión | orchestrator |
| sdd-apply T1..T4 | 2-3 sesiones | sdd-apply (4 atomic commits en 1 cluster) |
| sdd-verify | 1 sesión | sdd-verify |
| archive | 0.5 sesión | orchestrator |

Total: ~4-5 sesiones (abre Fase 3 con el primer consumer real de las primitivas de Fase 2).

## 18. Apéndice: archivos a tocar

### 18.1 NEW (crear)

- `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (T1)
- `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` (T1)
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (T1)
- `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (T1 + T3)
- `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (T2)
- `apps/electron-sucursal/src/features/auth/api/loginApi.test.ts` (T2)
- `apps/electron-sucursal/e2e/auth/login.spec.ts` (T4)
- `openspec/changes/hu-f3-1-login-email-password/exploration.md` (this file)
- `openspec/changes/hu-f3-1-login-email-password/proposal.md` (proposal phase)
- `openspec/changes/hu-f3-1-login-email-password/design.md` (design phase)
- `openspec/changes/hu-f3-1-login-email-password/tasks.md` (tasks phase)
- `openspec/changes/hu-f3-1-login-email-password/specs/operations/spec.md` (NO-OP stub per DEC-FETCH-10 precedent)
- `openspec/changes/hu-f3-1-login-email-password/verify-report.md` (verify phase)
- `openspec/changes/hu-f3-1-login-email-password/archive-report.md` (archive phase)

### 18.2 MODIFY (extender)

- `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (T1 — agregar 5 validation keys).
- `apps/electron-sucursal/src/renderer/App.tsx` (T3 — agregar `<Route path="/login" element={<LoginPage />} />`).
- `pending.md` (archive phase — marcar F3.1 ✅ cerrado, actualizar Total LOC restante, footer).

### 18.3 READ ONLY (anchors — NO modificar)

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
- `openspec/specs/operations/spec.md` (canonical, no F3.1 touch — delta stub solo).

### 18.4 Total de archivos impactados

- **NEW**: 14 archivos (~430 LOC + ~150 LOC artifacts SDD).
- **MODIFY**: 3 archivos (~10 LOC delta production + 5 keys i18n + pending.md).
- **READ ONLY**: 16 archivos.
- **TOTAL IMPACT**: 17 archivos de 430 LOC nuevos + 10 LOC delta.

---

## CHANGELOG

- (2026-09-15) F3.1 explore phase complete — 17 secciones, 10 DEC-F3.1-NN, 6 acceptance gates, 8 riesgos, 1 cluster C1, 4 atomic tasks T1..T4. Pre-flight 10/10 PASS + 0 KNOWN-MISSING. Backend `POST /auth/login` + `GET /auth/me` CONFIRMED existentes (HU-F1.2 shipped). All Fase 2 primitives (parkosFetch + authStore + useAuth + bridge IPC + i18n + shadcn Form) ready for F3.1 consumption. Ready for sdd-propose.

---

**End of exploration.**
