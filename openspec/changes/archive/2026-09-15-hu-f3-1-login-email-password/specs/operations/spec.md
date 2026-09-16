# Delta Spec — HU-F3.1 Login con `email` + `password`

> **Phase**: spec (sdd-spec) · **Status**: ready for sdd-design (parallel) + sdd-tasks
> **HU ID**: HU-F3.1 (Fase 3 — primera HU; Autenticación y turno de caja)
> **Change**: `hu-f3-1-login-email-password`
> **Spec canonical**: `openspec/specs/operations/spec.md` (v: post-F3.1, 112 REQ-OPS-001..112)
> **Delta type**: MATERIALIZED con 7 new REQ-OPS-106..112 (user-facing behavior per F1.15 precedent)
> **DEC-F3.1-11 verdict**: DELTA stub (NOT NO-OP) — F3.1 IS user-facing behavior observable (login UI + error messages + cookie round-trip + redirect + WCAG 2.1 AA compliance).

---

## 0. Metadata

- **HU**: HU-F3.1
- **Fase**: 3 (Autenticación y turno de caja — primera HU; transversal a todas las CU operativas)
- **Spec delta type**: MATERIALIZED DELTA (NOT NO-OP stub)
- **New REQ-OPS**: 7 (REQ-OPS-106..112)
- **Author**: Parkos Dev <dev@parkos.local>
- **Date**: 2026-09-15
- **Precedente directo**: F1.15 (login histórico) archivado 2026-09-15 con 4 new REQ-OPS-102..105 user-facing (`openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/specs/operations/spec.md`).
- **Spec canonical vigente**: 105 REQ-OPS (REQ-OPS-001..105) + 6 XR (REQ-OPS-XR1..XR6) post-F1.15 archive.

---

## 1. Purpose

Esta delta materializa el primer consumer end-to-end de las primitivas transversales de Fase 2 (`parkosFetch`, `useAuthStore`, `useAuth()` SWR, `bridge.authStore` IPC, shadcn Form primitives). A diferencia de F2.1/F2.2/F2.3 (infra-only con NO-OP stub per `DEC-ELEC-10`, `DEC-FETCH-10`, `DEC-UPD-13`), F3.1 ES user-facing behavior observable: el operador escribe `email` + `password`, recibe mensajes de error con semántica de anti-enumeración, la cookie `parkos_session` round-trip entre cliente y backend, y el redirect post-hidratación transaccional. Esta behavior visible al usuario no puede vivir solo en `DEC-F3.1-NN` dentro de `proposal.md` — debe anclarse en `REQ-OPS-NNN` dentro del spec canónico `openspec/specs/operations/spec.md` para que sea verificable, auditable y refactorizable.

`DEC-F3.1-11` (introducido en `proposal.md §5.11`) rompe el precedent NO-OP de F2.x y adopta precedent F1.15 (4 new REQ-OPS-102..105 user-facing archivados 2026-09-15). Las 7 new REQ-OPS-106..112 documentan el comportamiento observable al operador en formato Given/When/Then/And RFC 2119, con anchor links explícitos a `DEC-F3.1-NN` ratificados en `exploration.md §6` + `proposal.md §5`. Las decisiones técnicas viven en `proposal.md` (qué hace cada componente, layout, archivos), las requirements viven en este spec (qué comportamiento debe ser verdadero post-cambio).

---

## 2. Scope of the delta

### 2.1 In scope (7 new REQ-OPS)

| REQ-OPS | Comportamiento observable |
|---|---|
| **REQ-OPS-106** | LoginForm con validación inline RHF+Zod (`email` formato + `password` min 8) |
| **REQ-OPS-107** | POST /auth/login con `credentials:'include'` + Content-Type JSON (cookie httpOnly round-trip) |
| **REQ-OPS-108** | 401 → mensaje único `errors.invalidCredentials` (anti-enumeración cross-layer) |
| **REQ-OPS-109** | 429 → `errors.lockout` con `Retry-After` header (forward hook F3.2 countdown) |
| **REQ-OPS-110** | `useAuthStore.setTokens(access, refresh, expires_in)` hidrata desde 200 OK atómicamente |
| **REQ-OPS-111** | Redirect a `/` post-`useAuth().isAuthenticated && data?.user && !isLoading` (transaccional) |
| **REQ-OPS-112** | WCAG 2.1 AA compliance: axe-core 0 violaciones en `<LoginForm>` (RNF-022) |

### 2.2 Out of scope (deferred a Fase 3+)

- **Lockout countdown UI** — F3.2 entrega `useCountdown` hook + 429 disable form.
- **Refresh pre-flight** — F3.2 (50min auto-refresh antes de POST `/facturacion/*` + POST `/caja/arqueo`).
- **Logout button UI** — F3.3+ (F3.1 solo verifica `useAuthStore.clear()` en e2e).
- **Recuperación de password / 2FA / WebAuthn** — fuera Fase 3.
- **Multi-tab login UI** — kiosko single-tab por F2.3 `requestSingleInstanceLock`.
- **Turno abrir/cerrar** — F3.3 (`features/caja/pages/{AbrirTurno,CerrarTurno}.tsx`).
- **AuthGuard component** — F3.3+ (intercepta `parkos:auth:cleared` → `navigate('/login?next=...')`).
- **Sucursal selector UI** — JWT ya pinea sucursal (kiosko single-branch).
- **`rememberMe` checkbox** — auth.json:10 tiene la key pero F3.1 NO la usa.
- **`forgotPassword` link** — auth.json:11 tiene la key pero F3.1 NO la renderiza.
- **Backend cambios** — HU-F1.2 shipped cubre `/auth/login` + `/auth/me`; F3.1 NO modifica backend.
- **Refresh-token rotation** — F2.2 cubre (`DEC-FETCH-03`); F3.1 NO toca.
- **Zod schema validation en boundary via `parkosFetch<T>(url, schema)`** — opcional, F3.1 NO exige.

---

## 3. ADDED Requirements

### REQ-OPS-106 — LoginForm con validación RHF+Zod inline (DEC-F3.1-02 + DEC-F3.1-06)

**Source**: HU-F3.1 (`plan.md:1278, 1289, 1291` + `DEC-F3.1-02` Container/Presentational split + `DEC-F3.1-06` Zod local) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<LoginForm>` MUST renderizar dos campos de formulario (`email` + `password`) con validación inline React Hook Form + Zod (`@hookform/resolvers/zod`) usando el schema `z.object({ email: z.string().email(), password: z.string().min(8) })`. Los mensajes de validación (`validation.email.invalid`, `validation.password.minLength`, `validation.required`) MUST mostrarse inline en cada `FormField` vía `<FormMessage />` con `role="alert"` (atributo semántico del componente shadcn `Form`). El botón submit MUST estar deshabilitado (`disabled={!form.formState.isValid || isSubmitting}`) hasta que ambos campos pasen la validación Zod. El componente MUST cumplir WCAG 2.1 AA — `FormField` con `aria-invalid={!!error}`, label asociado via `htmlFor` (componente `FormLabel` shadcn), tab order secuencial.

**Rationale**: El operador necesita feedback inmediato sobre la validez de sus credenciales antes de tocar el backend. RHF + Zod evita renders innecesarios (re-render solo en `onChange` blur/submit) y mantiene la lógica de validación declarativa (vs imperativa). La validación local es UX — la validación final la hace el backend via Pydantic (`schemas/auth.py::LoginRequest` `EmailStr + StringConstraints min_length:8`); si hay mismatch (R6 risk), el cliente recibe 422 con detalle.

**Source**: `apps/electron-sucursal/package.json:23, 45, 51` (`react-hook-form@^7.53.0` + `zod@^3.23.8` + `@hookform/resolvers@^3.9.0` — F2.1 baseline); `apps/electron-sucursal/src/renderer/components/ui/{form,input,button}.tsx` (F2.1 shadcn primitives); `backend/packages/parkos_core/src/parkos_core/schemas/auth.py::LoginRequest` (Pydantic anchor).

**Scenario 1: Happy path — form válido habilita submit**
- **Given** el operador accede a `/login` sin sesión activa (`useAuthStore.getState().accessToken === null`)
- **And** los dos campos están vacíos (`email: ''`, `password: ''`)
- **When** el operador tipea `email = "operador@sucursal-1.parkos.local"` (formato válido) y `password = "Pass1234word"` (8+ chars)
- **Then** el `<Button type="submit">` MUST estar habilitado (`disabled === false`)
- **And** NO MUST haber mensajes de validación visibles
- **And** el form MUST pasar `formState.isValid === true` (RHF + Zod resolver).

**Scenario 2: Email formato inválido — `validation.email.invalid` inline + submit deshabilitado**
- **Given** el operador tipea `email = "no-es-email"` y `password = "Pass1234word"`
- **When** el operador hace blur en `email` (RHF dispara validación)
- **Then** `<FormMessage name="email">` MUST mostrar el texto exacto de la key i18n `validation.email.invalid` (`auth.json` — pre-F3.1 NO existe; F3.1 T1 agrega las 5 keys de validation)
- **And** el FormField MUST setear `aria-invalid="true"` en el `<Input>`
- **And** el `<Button type="submit">` MUST estar deshabilitado (`disabled === true`).

**Scenario 3: Password < 8 caracteres — `validation.password.minLength` inline**
- **Given** el operador tipea `email = "operador@sucursal-1.parkos.local"` y `password = "123"` (3 chars)
- **When** el operador hace blur en `password`
- **Then** `<FormMessage name="password">` MUST mostrar `validation.password.minLength`
- **And** el FormField MUST setear `aria-invalid="true"`
- **And** el submit MUST estar deshabilitado.

**Scenario 4: Submit con campos vacíos — `validation.required` inline + form NO submitea**
- **Given** el operador accede a `/login` y submita el form sin tipear nada (click submit con campos vacíos)
- **When** `onSubmit` se dispara
- **Then** RHF MUST abortar submit (resolver detecta campos vacíos)
- **And** ambos FormMessages MUST show `validation.required`
- **And** NO MUST haber network request al backend.

---

### REQ-OPS-107 — POST /auth/login con `credentials:'include'` + cookie httpOnly round-trip (DEC-F3.1-03 + DEC-F3.1-04 + DEC-F3.1-05)

**Source**: HU-F3.1 (`plan.md:1279, 1284` + `DEC-F3.1-03` credentials include + `DEC-F3.1-04` HTTP no IPC + `DEC-F3.1-05` fetch raw no parkosFetch) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El cliente MUST enviar `POST /api/v1/auth/login` con `credentials: 'include'` explícito en el `fetch` para que el navegador ACEPTE la cookie `parkos_session` (httponly+secure+samesite=lax) y la ENVÍE en requests subsiguientes (`GET /auth/me`). El `fetch` MUST ser raw (no `parkosFetch`) porque (a) NO queremos `Authorization: Bearer` pre-login (no existe token), (b) queremos leer `Retry-After` header en 429, (c) queremos `credentials:'include'` explícito sin que parkosFetch intercepte. La request MUST llevar `Content-Type: application/json` y body `{"email": "...", "password": "..."}` (password min 8 chars, validado Zod localmente en REQ-OPS-106). El cliente MUST aceptar la response 200 con body `TokenPair{access_token, refresh_token, token_type, expires_in}` (backend `auth.py:303-307` + `schemas/auth.py::TokenPair`).

**Rationale**: La cookie httpOnly es el canal primario de autenticación cross-request (no el access_token en memoria, que se usa para header `Authorization: Bearer`). `credentials:'include'` es mandatory — sin esto, el navegador setea la cookie en la response pero NO la persiste en el cookie jar, y el siguiente `/auth/me` viaja sin auth y el backend responde 404 (`auth.py:454-458`). El raw fetch (no parkosFetch) preserva la semántica "login es anónimo, todo lo demás es autenticado" (DEC-F3.1-05).

**Source**: `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-307` (POST /auth/login endpoint); `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:291-299` (cookie set_cookie call con httponly+secure+samesite=lax); `backend/packages/parkos_core/src/parkos_core/schemas/auth.py::LoginRequest` + `TokenPair`; `apps/ui-kit/src/fetch/parkosFetch.ts:105-109` (`isLoginEndpoint = url.includes('/auth/login')` — Idempotency-Key skip); `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (T2 nuevo, fetch raw).

**Scenario 1: Login OK con credenciales válidas — 200 + cookie persistida + TokenPair body**
- **Given** el operador submita `email = "operador@sucursal-1.parkos.local"` + `password = "Pass1234word"` (válido)
- **When** `loginApi.postLogin(email, password)` ejecuta `fetch('/api/v1/auth/login', {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email, password})})`
- **Then** el backend MUST responder `200 OK` con `Content-Type: application/json` + `Set-Cookie: parkos_session=<jwt>; HttpOnly; Secure; SameSite=Lax; Max-Age=3600; Path=/`
- **And** el body MUST ser `TokenPair{access_token, refresh_token, token_type: "Bearer", expires_in: 3600}`
- **And** el navegador MUST persistir la cookie `parkos_session` (httponly bloquea JS lectura; cookie jar la mantiene hasta Max-Age).
- **And** el cliente MUST retornar el `TokenPair` parseado al caller (Login.tsx → REQ-OPS-110 setTokens).

**Scenario 2: Request sin `credentials:'include'` — cookie se setea pero NO se persiste (anti-regression test)**
- **Given** un hipotético cliente que envía `fetch('/api/v1/auth/login', {method:'POST'})` SIN `credentials:'include'`
- **When** el backend responde 200 con `Set-Cookie parkos_session`
- **Then** el navegador MUST NO persistir la cookie (Fetch spec: omit credentials = no cookie jar write)
- **And** el siguiente `GET /auth/me` MUST NO llevar la cookie
- **And** el backend MUST responder 404 (`auth.py:454-458`)
- **And** el test e2e MUST validar que `loginApi.postLogin` SIEMPRE incluye `credentials:'include'` (no se omite accidentalmente).

---

### REQ-OPS-108 — 401 → `errors.invalidCredentials` único anti-enumeración (DEC-F3.1-08)

**Source**: HU-F3.1 (`plan.md:1281` + `DEC-F3.1-08` anti-enumeration UI message) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
Cuando el backend responde `401 Unauthorized` con body `{"error": "invalid_credentials", ...}` (causa: email desconocido O password incorrecta — indistinguibles por anti-enumeration backend en `auth.py:159-191, 248-251`), el frontend MUST mostrar un único mensaje `<p role="alert">{t('invalidCredentials')}</p>` con texto exacto de `auth.json:9` (`invalidCredentials`). MUST NO haber distinción visible entre "email no existe" / "password incorrecta" / "cuenta deshabilitada" — esto previene enumeración de usuarios válidos por differential analysis. El componente `<LoginForm>` MUST renderizar el mensaje en `<FormMessage>` o `<p role="alert">` arriba del submit button, con `aria-live="polite"` o `role="alert"` para screen readers.

**Rationale**: Anti-enumeración es cross-layer (backend + frontend). El backend ya colapsa 401 a `errors.invalid_credentials` único (`auth.py:159-191, 248-251`). El frontend matchea — no debe filtrar información que el backend colapsó. Esto evita el vector de ataque "POST /auth/login con emails conocidos vs aleatorios → comparar respuestas para inferir emails válidos".

**Source**: `apps/electron-sucursal/src/renderer/i18n/locales/auth.json:9` (`invalidCredentials` key — pre-F3.1 existe per `exploration.md §2.9`); `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:159-191, 248-251` (anti-enumeration backend); R1..R5 risks en `exploration.md §7` (timing attacks mitigados por bcrypt cost).

**Scenario 1: 401 con email desconocido — mensaje único `invalidCredentials`**
- **Given** el operador tipea `email = "fantasma@sucursal.local"` (no existe en `prod.usuarios`) + `password = "Pass1234word"`
- **And** el backend responde 401 con `{"error": "invalid_credentials", ...}` (auth.py:188-191)
- **When** `loginApi.postLogin` parsea la response y `Login.tsx` setea `error = t('invalidCredentials')`
- **Then** el componente MUST renderizar `<p role="alert">{t('invalidCredentials')}</p>` ("Credenciales inválidas" en español neutro)
- **And** el componente MUST NO renderizar "Email no encontrado" ni "Usuario inexistente" (anti-enumeration).

**Scenario 2: 401 con email válido + password incorrecta — MISMO mensaje `invalidCredentials`**
- **Given** el operador tipea `email = "operador@sucursal-1.parkos.local"` (existe) + `password = "wrong-pass"` (incorrecta)
- **And** el backend responde 401 con `{"error": "invalid_credentials", ...}` (auth.py:248-251)
- **When** `loginApi.postLogin` parsea la response
- **Then** el componente MUST renderizar el MISMO texto que Scenario 1 (`t('invalidCredentials')`)
- **And** el componente MUST NO renderizar "Password incorrecta" ni "Credenciales erróneas — verifique su contraseña" (mismo shape, indistinguible).

---

### REQ-OPS-109 — 429 → `errors.lockout` con `Retry-After` header parseado (DEC-F3.1-08)

**Source**: HU-F3.1 (`plan.md:1283` + `DEC-F3.1-05` fetch raw para Retry-After + `DEC-F3.1-08` lockout forward hook) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Cuando el backend responde `429 Too Many Requests` con `Retry-After: <segundos>` header (cuando `count(fallido in window) >= max_intentos_login` per `configuracion_seguridad` configurable per-branch, `auth.py:219-228`), el cliente MUST emitir `AccountLockedError(retryAfterSeconds)` donde `retryAfterSeconds = Number(response.headers.get('Retry-After') ?? '0')`. El frontend MUST mostrar `<p role="alert">{t('lockout')}</p>` con texto de `auth.json:8` (`lockout` — "Cuenta bloqueada. Intenta de nuevo en N minutos." donde N = `Math.ceil(retryAfterSeconds / 60)`). F3.1 MUST NO implementar countdown UI (forward hook a F3.2 — `useCountdown` hook + 429 disable form + countdown visual). El componente MUST mantener el form deshabilitado hasta que `retryAfterSeconds` expire, pero SIN countdown visual en F3.1 (texto estático "Intenta de nuevo en N minutos.").

**Rationale**: F3.1 entrega el catch + surface del 429 (REQ-OPS-109). F3.2 (HU-F3.2) entrega el countdown UI (forward hook declarado en `proposal.md §14` + `exploration.md §15`). El split es por atomicidad: F3.1 NO depende de F3.2 para shippear; F3.2 consume `AccountLockedError` que F3.1 emite.

**Source**: `apps/electron-sucursal/src/renderer/i18n/locales/auth.json:8` (`lockout` key); `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:219-228` (429 + Retry-After); `backend/packages/parkos_core/src/parkos_core/models/V/configuracion_seguridad.py` (max_intentos_login + minutos_bloqueo_login — modelo_datos_er.mmd:270-289); `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (T2 — error mapping custom).

**Scenario 1: 429 + Retry-After: 600 — lockout estático "10 minutos"**
- **Given** el operador agotó `max_intentos_login` en `configuracion_seguridad` (default 5 intentos)
- **And** el operador tipea credenciales (válidas o inválidas — el backend bloquea cualquiera)
- **When** el backend responde `429 Too Many Requests` con `Retry-After: 600` header (10 minutos)
- **Then** `loginApi.postLogin` MUST parsear `Number(response.headers.get('Retry-After') ?? '0')` = 600
- **And** MUST throw `AccountLockedError(retryAfterSeconds: 600)`
- **And** el componente MUST mostrar `<p role="alert">{t('lockout')}</p>` ("Cuenta bloqueada. Intenta de nuevo en 10 minutos.")
- **And** MUST NO mostrar countdown visual (forward hook F3.2).

**Scenario 2: 429 sin `Retry-After` header — fallback `retryAfterSeconds: 0` + mensaje genérico**
- **Given** una response 429 hipotética SIN `Retry-After` header (anomaly del backend)
- **When** `loginApi.postLogin` parsea la response
- **Then** `retryAfterSeconds` MUST ser 0 (fallback `?? '0'`)
- **And** `AccountLockedError(0)` MUST emitirse
- **And** el componente MUST mostrar `t('lockout')` SIN "N minutos" (texto fallback).

---

### REQ-OPS-110 — `useAuthStore.setTokens(access, refresh, expires_in)` atómico post 200 OK (DEC-F3.1-07)

**Source**: HU-F3.1 (`plan.md:1280, 1292` + `DEC-F3.1-07` hidratación transaccional) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
Cuando `loginApi.postLogin` retorna el `TokenPair` parseado de 200 OK, el componente `<LoginPage>` MUST llamar `useAuthStore.getState().setTokens(access_token, refresh_token, expires_in)` ANTES de cualquier otra acción (incluyendo redirect o re-render). El state de `useAuthStore` MUST pasar de `{accessToken: null, refreshToken: null, expiresAt: null}` a `{accessToken: <jwt>, refreshToken: <jwt>, expiresAt: <ISO 8601>}` atómicamente (Zustand `setState` es síncrono). El estado MUST persistir vía `bridge.authStore.{set}` IPC a `electron-store` (F2.2 `DEC-FETCH-08` — `partialize` whitelist persiste SOLO `{accessToken, refreshToken, expiresAt}`). Tras `setTokens`, `useAuth()` SWR hook MUST detectar el key change (`null` → `'/auth/me'`) y disparar `parkosFetch('/auth/me')` con `Authorization: Bearer <new_access>` (header automático per `parkosFetch.ts:92-96`) + cookie `parkos_session` auto-enviada (browser cookie jar).

**Rationale**: Hidratación atómica garantiza que el operador nunca llega a `/` con `accessToken: null` mientras `useAuth()` está hidratando. Zustand `setState` síncrono elimina la race condition entre setTokens y SWR key change (R4 risk en `exploration.md §7`).

**Source**: `apps/ui-kit/src/store/authStore.ts:1-129` (F2.2 — `setTokens` + `clear` + `partialize`); `apps/ui-kit/src/hooks/useAuth.ts:1-87` (F2.2 — SWR key `accessToken ? '/auth/me' : null`); `apps/ui-kit/src/fetch/parkosFetch.ts:92-96` (Authorization Bearer injection).

**Scenario 1: 200 OK → setTokens atómico + persist electron-store**
- **Given** `loginApi.postLogin` retorna `TokenPair{access_token: "<jwt>", refresh_token: "<jwt>", token_type: "Bearer", expires_in: 3600}`
- **When** `<LoginPage>` ejecuta `useAuthStore.getState().setTokens("<access>", "<refresh>", 3600)`
- **Then** `useAuthStore.getState().accessToken` MUST ser `<access>` (no null, no previous value)
- **And** `useAuthStore.getState().refreshToken` MUST ser `<refresh>`
- **And** `useAuthStore.getState().expiresAt` MUST ser `<now + 3600s>` en ISO 8601 UTC
- **And** `bridge.authStore.set({accessToken, refreshToken, expiresAt})` MUST invocarse vía IPC (F2.2 wireado)
- **And** `electron-store` MUST persistir el state (visible post Electron app restart).

**Scenario 2: SWR key change → useAuth() re-fetcha `/auth/me` con Bearer + cookie**
- **Given** `setTokens` se ejecutó (state actualizado)
- **When** React re-renderiza `<LoginPage>` con el nuevo `useAuth()` state
- **Then** SWR MUST detectar `accessToken !== null` y disparar `parkosFetch('/auth/me')` con:
  - `Authorization: Bearer <access>` (header automático)
  - `Cookie: parkos_session=<jwt>` (browser cookie jar auto-envía)
- **And** `useAuth()` MUST retornar `{user, sucursal, sucursalesPermitidas, permisos, expiresAt, isAuthenticated: true, isLoading: true}` (loading durante el fetch).

---

### REQ-OPS-111 — Redirect a `/` post-`useAuth().isAuthenticated && data?.user && !isLoading` (DEC-F3.1-07)

**Source**: HU-F3.1 (`plan.md:1302` + `DEC-F3.1-07` hidratación transaccional + `DEC-F3.1-09` AuthGuard deferred) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<LoginPage>` MUST ejecutar `navigate('/')` SOLO cuando `useAuth()` retorna `{isAuthenticated: true, isLoading: false, data: {user: <UserItem>, sucursal: <SucursalItem>, sucursalesPermitidas: <SucursalItem[]>, permisos: <string[]>, expiresAt: <ISO 8601>}}`. El `useEffect` MUST tener deps `[isAuthenticated, data?.user, isLoading]` (R4 race mitigation). MUST NO navegar si `data?.user === undefined` (in-flight SWR) ni si `isLoading === true` (transición). Esto previene el flash de "sesión no iniciada" en el destino — F3.3+ dashboards dependen de `useAuth().user.sucursal` y renderizarían con `user: null` durante el primer render. El componente MUST NO implementar AuthGuard (forward hook F3.3+ — `parkos:auth:cleared` event listener que dispara `navigate('/login?next=...')`); F3.1 Login page es standalone (entry point, no requiere auth-guard).

**Rationale**: Hidratación transaccional es critical para UX profesional. El operador llega a `/` con sesión + user + sucursal + permisos TODOS resueltos (F3.3+ lee `user.sucursal` para abrir turno).

**Source**: `apps/ui-kit/src/hooks/useAuth.ts:67-69` (`parkos:auth:cleared` event emission); `apps/electron-sucursal/src/renderer/App.tsx:1-37` (F2.1 router + F2.3 StatusBar mount — F3.1 T3 MODIFY +5 LOC para agregar `<Route path="/login">`); react-router-dom@^6.27.0 `useNavigate`.

**Scenario 1: Hidratación completa → navigate('/') atómico**
- **Given** el operador completó `setTokens` (REQ-OPS-110) + `useAuth()` SWR resolvió `/auth/me` con 200 OK
- **And** `useAuth()` retorna `{isAuthenticated: true, isLoading: false, data: {user: {uuid, email, nombre, apellido, rol}, sucursal: {uuid, nombre, prefijo_nombre}, sucursalesPermitidas: [...], permisos: [...], expiresAt: <ISO>}}`
- **When** el `useEffect` en `<LoginPage>` dispara con deps `[isAuthenticated, data?.user, isLoading]`
- **Then** el componente MUST llamar `navigate('/')`
- **And** el operador MUST llegar a `/` con `useAuth()` ya hidratado (sin flash de "sesión no iniciada").

**Scenario 2: Hidratación en curso — useEffect NO navega**
- **Given** el operador completó `setTokens` (REQ-OPS-110) pero `/auth/me` AÚN no resolvió
- **And** `useAuth()` retorna `{isAuthenticated: true, isLoading: true, data: undefined}`
- **When** el `useEffect` dispara con deps `[isAuthenticated, data?.user, isLoading]`
- **Then** el componente MUST NO llamar `navigate('/')` (falta `data?.user`)
- **And** el operador MUST permanecer en `/login` viendo un spinner o estado de loading.

---

### REQ-OPS-112 — WCAG 2.1 AA compliance via axe-core 0 violaciones (RNF-022)

**Source**: HU-F3.1 (`plan.md:1295` + `RNF-022` WCAG 2.1 AA — `docs/01-requisitos/no-funcionales.md:126` + `DEC-F3.1-01` feature folder + `DEC-F3.1-02` Container/Presentational con a11y) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<LoginForm>` MUST pasar el scan `axe-core` (vía `@axe-core/playwright` extension) con 0 violaciones de WCAG 2.1 AA. Cobertura mandatory: (1) labels asociados via `htmlFor` (componente shadcn `FormLabel` resuelve automáticamente), (2) `aria-invalid="true"` en `<Input>` cuando hay error de validación (`formState.errors.email` o `.password`), (3) `aria-describedby` apuntando a `FormMessage` (componente shadcn `FormControl` + `FormMessage` linked via `useFormField`), (4) `role="alert"` en mensajes de error (`FormMessage` shadcn), (5) tab order secuencial (email → password → submit), (6) contraste de color mínimo 4.5:1 (CSS tokens de `apps/ui-kit/src/tokens.ts` — F2.1 baseline), (7) focus visible en inputs (CSS `focus-visible` ring). El e2e test `e2e/auth/login.spec.ts` MUST incluir un test `axe-core scan on /login` que ejecute el analyzer post-render del form.

**Rationale**: RNF-022 (`docs/01-requisitos/no-funcionales.md:126`) exige WCAG 2.1 AA compliance para todas las pantallas transaccionales. Login es la primera pantalla post-Fase 2 — setea el patrón a11y para Fase 3 entera (F3.2, F3.3, etc.).

**Source**: `apps/electron-sucursal/package.json:55-56` (`@playwright/test@^1.48.0` + `@axe-core/playwright@^4.10.0` — F2.1 baseline); `docs/01-requisitos/no-funcionales.md:126` (RNF-022 anchor); `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` (F2.1 axe-core pattern precedent — F3.1 replica el patrón en `e2e/auth/login.spec.ts`).

**Scenario 1: axe-core scan en `<LoginForm>` — 0 violaciones**
- **Given** el operador accede a `/login` y `<LoginForm>` renderiza completamente
- **When** `e2e/auth/login.spec.ts::test_axe_core_login` ejecuta `new AxeBuilder({page}).analyze()` con tags `wcag2a, wcag2aa, wcag21a, wcag21aa`
- **Then** el array `result.violations` MUST estar vacío (length === 0)
- **And** el test MUST pasar verde (no skip en CI).

**Scenario 2: Form con error — aria-invalid + role="alert" + axe-core 0 violaciones**
- **Given** el operador tipea `email = "no-es-email"` y dispara blur (REQ-OPS-106 Scenario 2)
- **And** `<FormMessage>` renderiza `validation.email.invalid` con `role="alert"`
- **And** el `<Input>` tiene `aria-invalid="true"`
- **When** el scan axe-core re-ejecuta post-error
- **Then** MUST haber 0 violaciones adicionales (axe-core valida que aria-invalid + role="alert" juntos pasan WCAG 2.1 AA).

**Scenario 3: Tab order secuencial email → password → submit**
- **Given** el operador accede a `/login`
- **When** el operador presiona Tab 3 veces desde el body
- **Then** el foco MUST pasar por: (1) `<Input name="email">`, (2) `<Input name="password">`, (3) `<Button type="submit">`
- **And** el orden MUST ser el document order (no `tabindex` overrides).

---

## 4. Cross-reference table

| REQ-OPS | DEC-F3.1 anchor | Plan.md line | Precedent directo |
|---|---|---|---|
| REQ-OPS-106 | DEC-F3.1-02, DEC-F3.1-06 | 1278, 1289, 1291 | F1.15 REQ-OPS-102 (SELECT-only validation precedent) |
| REQ-OPS-107 | DEC-F3.1-03, DEC-F3.1-04, DEC-F3.1-05 | 1279, 1284 | F2.2 DEC-FETCH-08 (parkosFetch infra) |
| REQ-OPS-108 | DEC-F3.1-08 | 1281 | F1.15 REQ-OPS-104 (anti-enumeration 200 vs 404) |
| REQ-OPS-109 | DEC-F3.1-05, DEC-F3.1-08 | 1283 | F3.2 forward hook (countdown UI) |
| REQ-OPS-110 | DEC-F3.1-07 | 1280, 1292 | F2.2 useAuth.ts:53-86 (SWR refresh 5min) + authStore.ts:71-94 (persist) |
| REQ-OPS-111 | DEC-F3.1-07, DEC-F3.1-09 | 1302 | F1.15 REQ-OPS-105 (XR6 reference — F3.1 NO crea new XR) |
| REQ-OPS-112 | RNF-022 + DEC-F3.1-01, DEC-F3.1-02 | 1295 | F2.1 e2e/a11y/wcag-2.1-aa.spec.ts |

**Nota**: F3.1 NO crea un nuevo REQ-OPS-XR (cross-cutting requirement). Las 7 new REQ-OPS-106..112 son SPECIFIC a login flow (no cross-cutting). REQ-OPS-XR6 de F1.13 (5-layer defense in depth) sigue siendo el canonical cross-cutting contract para backend; F3.1 frontend replica el patrón pero NO formaliza un XR7 (precedent F1.15 `DEC-XR7 NOT-CREATED` en `operations/spec.md:4386`).

---

## 5. Acceptance criteria for sdd-verify

| # | Criterion | Test source | Type |
|---|---|---|---|
| AC-1 | LoginForm renderiza con validación RHF+Zod (REQ-OPS-106) | `LoginForm.test.tsx` (T1, ~30 LOC) + `Login.test.tsx` (T1, ~50 LOC) | Unit (vitest + @testing-library/react) |
| AC-2 | `loginApi.postLogin` envía `credentials:'include'` + `Content-Type: application/json` (REQ-OPS-107) | `loginApi.test.ts` (T2, ~50 LOC) con MSW handler assert request | Unit (vitest + MSW) |
| AC-3 | 401 → `t('invalidCredentials')` único, sin distinción email/password (REQ-OPS-108) | `Login.test.tsx` mock 401 response (T1) | Unit (vitest) |
| AC-4 | 429 → `AccountLockedError(retryAfter)` + `t('lockout')` (REQ-OPS-109) | `loginApi.test.ts` mock 429 + Retry-After header (T2) | Unit (vitest) |
| AC-5 | `useAuthStore.setTokens` hidrata atómicamente + persist electron-store (REQ-OPS-110) | `Login.test.tsx` mock 200 + assert setTokens spy (T2) | Unit (vitest) |
| AC-6 | `useEffect` espera `data?.user` antes de `navigate('/')` (REQ-OPS-111) | `Login.test.tsx` mock 200 + useEffect fires (T3) | Unit (vitest) |
| AC-7 | axe-core 0 violaciones WCAG 2.1 AA en `<LoginForm>` (REQ-OPS-112) | `login.spec.ts::test_axe_core_login` (T4, ~30 LOC embed) | E2E (playwright + axe-core) |
| AC-8 | 3 e2e scenarios verde (login-ok-cookie + refresh-transparente + logout) | `e2e/auth/login.spec.ts` (T4, ~80 LOC) | E2E (playwright _electron) |
| AC-9 | (transversal) i18n `auth.json` agrega 5 validation keys (`validation.email.invalid`, `validation.email.required`, `validation.password.minLength`, `validation.password.required`, `validation.required`) | snapshot test del JSON (T1) | Unit (vitest snapshot) |

**Sandbox F.6 caveat**: AC-8 puede SKIP en sandbox F.6 (npm 11.16.0 refuses `workspace:*` resolution — F2.2 archive report G8 precedent). Unit tests AC-1..AC-6 + AC-9 + AC-7 axe-core SÍ corren. Documentado como deviation D-env en `verify-report.md`, NO project defect.

---

## 6. Forward hooks (Fase 3+ consumer map)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.2** (lockout visible + refresh pre-flight) | `AccountLockedError(retryAfterSeconds)` de F3.1 → F3.2 `useCountdown` hook | F3.2 wraps Login.tsx onSubmit con disable form + countdown visual + auto-refresh check 50min |
| **HU-F3.3** (abrir/cerrar turno) | `useAuth().user.sucursal` + `permisos[]` hidratados post-F3.1 | F3.3 `AbrirTurno` lee `user.sucursal` (uuid de la sede) y `permisos` antes de POST `/caja-sesion/sesiones` |
| **HU-F3.x** (logout button UI) | `useAuthStore.clear()` ya implementado en F2.2 + `parkos:auth:cleared` window event | F3.x logout button dispatch `clear()` + `navigate('/login')` |
| **HU-F3.x** (AuthGuard component) | `parkos:auth:cleared` window event | F3.x `<AuthGuard>` envuelve `<Routes>` excepto `/login` → `navigate('/login?next=...')` cuando event fires |
| **HU-F4.x** (catálogos + ocupación) | `useAuth()` + `parkosFetch` | F4.x lee `user.sucursal` para scoped queries (`/facturacion/ocupacion?uuid_sucursal=...`) |
| **HU-F11.x** (sync UI) | `useAuth()` (no directo) | F11.x muestra `user.email` en topbar de StatusBar |
| **HU-F5.x+** (impresión térmica) | `useAuth().permisos` filter | F5.x verifica permiso `facturacion.emitir` antes de imprimir ticket |
| **PR7 backend** (refresh-token rotation) | `authStore` + `refreshAccessToken()` Mutex (F2.2) | Detección de reuse `jti` claim (F2.2 `DEC-FETCH-03` cubre sin rotation; rotación es PR7+) |

---

## 7. Out of scope (verbatim de `exploration.md §14`)

F3.1 NO incluye (explícitamente deferido a Fase 3+):

- **Lockout countdown UI** — F3.2 lo entrega (`useCountdown` hook + 429 disable form + countdown visual).
- **Refresh pre-flight antes de POST /facturacion/* + POST /caja/arqueo** — F3.2 (50min auto-refresh check).
- **Logout button UI** — F3.3+ (placeholder o HU posterior; F3.1 solo verifica `useAuthStore.clear()` en e2e).
- **Recuperación de password / forgotPassword** — fuera Fase 3 (futuro).
- **2FA / WebAuthn** — fuera Fase 3 (futuro).
- **Multi-tab login UI** — kiosko single-tab por F2.3 `requestSingleInstanceLock` (`DEC-UPD-07`).
- **Turno abrir/cerrar** — F3.3 (`AbrirTurno` + `CerrarTurno` + `useSesionActiva` en `features/caja/`).
- **AuthGuard component** — F3.3+ (intercepta `parkos:auth:cleared` event → `navigate('/login?next=...')`).
- **Sucursal selector UI** — JWT ya pinea sucursal (F3.1 single-branch kiosko).
- **`rememberMe` checkbox** — `auth.json:10` tiene la key pero F3.1 NO la usa (kiosko desatendido, no aplica).
- **`forgotPassword` link** — `auth.json:11` tiene la key pero F3.1 NO la renderiza (out of scope).
- **Backend cambios** — HU-F1.2 shipped en Fase 1 cubre los 2 endpoints (`POST /auth/login` + `GET /auth/me`); F3.1 NO modifica backend.
- **Refresh-token rotation** — F2.2 cubre (`DEC-FETCH-03`); F3.1 NO toca.
- **Zod schema validation en boundary via `parkosFetch<T>(url, schema)`** — `DEC-FETCH-05` optional; F3.1 NO exige.
- **OS-level kiosk** — Windows Assigned Access / macOS kiosk mode (FUERA Fase 3).
- **PIN rotation UI** — kiosko PIN pre-shared by F2.3, no rotation UI.

---

## 8. DoD checklist

- [ ] 7 REQ-OPS-106..112 materializadas en `openspec/changes/hu-f3-1-login-email-password/specs/operations/spec.md` (este archivo)
- [ ] Given/When/Then/And format RFC 2119 per F1.15 precedent
- [ ] Anchor links explícitos a `DEC-F3.1-NN` ratificados en `proposal.md §5`
- [ ] Cross-reference table completa (§4)
- [ ] Acceptance criteria verificables para `sdd-verify` (§5) — 9 criterios
- [ ] Forward hooks documentados para F3.2, F3.3, F3.x (§6)
- [ ] Out of scope verbatim de `exploration.md §14` (§7)
- [ ] NO-OP stub NO aplicado — DELTA stub con 7 new REQ-OPS confirmado (per `DEC-F3.1-11`)
- [ ] Numeración monotónica verificada (REQ-OPS-105 vigente post-F1.15; F3.1 ocupa REQ-OPS-106..112)
- [ ] Spanish neutro profesional per F1.15 precedent + global contract
- [ ] Author: `Parkos Dev <dev@parkos.local>` (F2.1 verbatim precedent)
- [ ] No "Co-authored-by" attribution per `CLAUDE.md` global rules
- [ ] RFC 2119 MUST/SHOULD/MAY keywords consistentes en las 7 REQ-OPS

---

## CHANGELOG

- **(2026-09-15)** F3.1 spec delta complete — 7 REQ-OPS-106..112 materializadas en Given/When/Then/And format RFC 2119. DELTA stub (NOT NO-OP) per critical re-evaluation en `sdd-propose §5.11` (DEC-F3.1-11). F3.1 ES user-facing behavior observable (login UI + anti-enumeration 401 + cookie httpOnly round-trip + redirect transaccional + WCAG 2.1 AA compliance). Precedent directo: F1.15 (login histórico) archivado 2026-09-15 con 4 new REQ-OPS-102..105. Numeración monotónica: REQ-OPS-105 vigente post-F1.15; F3.1 ocupa REQ-OPS-106..112 (continuación). Ready for `sdd-design` (parallel) + `sdd-tasks`.

---

**End of delta spec — HU-F3.1.**