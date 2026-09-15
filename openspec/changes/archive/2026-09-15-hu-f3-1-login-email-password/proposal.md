# Propuesta — HU-F3.1 Login con `email` + `password`

> **Change**: `hu-f3-1-login-email-password` · **Folder**: `openspec/changes/hu-f3-1-login-email-password/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F3.1 (Fase 3 — primera HU; Autenticación y turno de caja, transversal a todas las CU operativas)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `ba9d81a`, Fase 2 cerrada 2026-09-15 con F2.1 + F2.2 + F2.3 archivados) · **PR target**: `origin/dev`
> **Inputs**: `plan.md` lines 1274-1305 (HU-F3.1 verbatim, 4 tareas atómicas T1..T4, 190 LOC); `exploration.md` (17 secciones, 10 DEC-F3.1-01..10 ratified, 6 acceptance gates G1..G6, 8 riesgos R1..R8, pre-flight 10/10 PASS + 0 KNOWN-MISSING); `openspec/specs/operations/spec.md` (canonical 112 REQ-OPS-001..105 vigentes — última REQ-OPS-105 archivada por F1.15 — siguiente número disponible REQ-OPS-106); precedent proposals archivados: F2.1 (DEC-ELEC-10 NO-OP stub), F2.2 (DEC-FETCH-10 NO-OP stub), F2.3 (DEC-UPD-13 NO-OP stub), F1.15 (4 new REQ-OPS-102..105 user-facing precedent); `apps/electron-sucursal/electron/{main,preload,bridge.d}.ts` (F2.2+F2.3 shippeados); `apps/ui-kit/src/{fetch/parkosFetch.ts,store/authStore.ts,hooks/useAuth.ts}` (F2.2 primitives); `apps/electron-sucursal/src/renderer/{App.tsx,i18n/locales/auth.json,components/ui/{form,input,button}.tsx}` (F2.1+F2.2); `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-583` (HU-F1.2 shipped — `POST /auth/login` + `GET /auth/me`); `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` (LoginRequest + TokenPair + AuthMeResponse); `docs/01-requisitos/no-funcionales.md:126` (RNF-022 WCAG 2.1 AA); `docs/03-desarrollo/{setup.md, estandares.md}`; `pending.md §1-§6` (Fase 3 0/3 abierto, F3.1 = primer HU).

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F3.1 |
| **Fase** | 3 (Autenticación y turno de caja — primera HU) |
| **Change name** | `hu-f3-1-login-email-password` |
| **Folder** | `openspec/changes/hu-f3-1-login-email-password/` |
| **State** | proposed (ready for design + spec) |
| **Branch** | `feat/fase-2-electron-scaffold` |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | Fase 2 archivada 2026-09-15 (F2.1 + F2.2 + F2.3 — 24 commits en `feat/fase-2-electron-scaffold`) |
| **Próximo phase** | sdd-spec + sdd-design (paralelo) |
| **Language** | español neutro profesional |
| **Conventional commits** | feat(auth) / feat(router) / test(electron) — sin Co-authored-by |

---

## 1. Title & Goal

**Title**: "Login con `email` + `password` contra POST /auth/login con `credentials:'include'` + cookie `parkos_session` (httponly+secure+samesite=lax) + hidratación de `authStore` desde GET /auth/me + redirect a `/` + anti-enumeración (`errors.invalid_credentials` único para 401) + WCAG 2.1 AA compliance via axe-core"

**Goal**: Fase 2 archivada (F2.1 + F2.2 + F2.3, 24 commits en `feat/fase-2-electron-scaffold`) deja sentada toda la infraestructura transversal: Electron 30 skeleton + parkosFetch con retry/refresh/idempotency/Zod + bridge IPC tipado con 8 métodos + authStore Zustand con persist electron-store + useAuth() SWR hook con `/auth/me` revalidation 5min + electron-updater + single-instance + kiosko + electron-log + StatusBar aria-live polite. F3.1 entrega el primer consumer end-to-end de esa infraestructura: la pantalla de login real que el operador usa al iniciar su turno. El formulario dispara `POST /auth/login` con `credentials:'include'`, el backend emite cookie `parkos_session` (httponly+secure+samesite=lax) + body con TokenPair, `useAuthStore.setTokens` hidrata `authStore`, `useAuth()` re-fetcha `/auth/me` para resolver `user` + `sucursal` + `permisos`, y el componente redirige a `/` (la sesión activa queda libre para que F3.3 monte `AbrirTurno` cuando lo requiera).

**Por qué importa** (rationale): F3.1 es el primer consumer real de las primitivas de Fase 2. Tres factores elevan su criticidad:

1. **Anti-enumeración (DEC-F3.1-08)**: el campo de acceso es `email`, NUNCA `cedula` — corrige explícitamente una versión previa del plan que asumía `cedula` (error que NO proviene de CU-01 verificado sino de una lectura incorrecta del esquema de autenticación real). El error genérico `errors.invalid_credentials` (401) cubre tanto email desconocido como password incorrecta sin distinción — implementado en backend `auth.py:159-191, 250-251`.
2. **Cookie httpOnly + credentials:'include'**: el navegador NUNCA expone la cookie a JavaScript (`HttpOnly` flag). Esto blinda contra exfiltración via XSS — el atacante puede inyectar scripts pero NO puede leer `parkos_session`. El frontend solo necesita `authStore` con el access_token en electron-store (que NO es accesible desde el DOM); el `Authorization: Bearer` header que `parkosFetch` inyecta autentica los GET/POST contra el backend.
3. **Hidración transaccional (DEC-F3.1-07)**: el flujo login → /auth/me debe ser atómico en términos de UX. Si el operador llega a `/` y `useAuth()` muestra `user: null` durante el primer render (porque `/auth/me` aún no resolvió), el componente renderiza un flash de "sesión no iniciada". F3.1 lo evita montando el redirect sobre `useAuth().isAuthenticated` + `isLoading` + `data?.user`, esperando a tener `data.user` antes de hacer `navigate('/')`.

**Por qué importa a nivel spec (re-evaluación crítica)**: a diferencia de F2.1 (scaffold infra-only sin behavior observable al operador), F2.2 (HTTP infra transversal sin UI nueva), F2.3 (runtime infra sin behavior observable directo al operador), F3.1 ES user-facing behavior observable: el operador escribe email+password, recibe mensajes de error con semántica de anti-enumeración, la cookie round-trip entre cliente y backend, y el redirect post-hidratación. Esta behavior visible al usuario NO puede vivir solo en DEC-F3.1-NN dentro de `proposal.md` — debe anclarse en REQ-OPS-NNN dentro del spec canónico `openspec/specs/operations/spec.md` para que sea verificable, auditable y refactorizable. Precedent directo: F1.15 (login histórico) que ESCRIBIÓ 4 new REQ-OPS-102..105 al spec canónico con exactamente la misma justificación (user-facing behavior del feature de login). F3.1 sigue el precedent F1.15 y **rompe** el precedent NO-OP de F2.1/F2.2/F2.3 (esos fueron infra-only; F3.1 NO).

**Hard constraints** (mirrored from `plan.md:1278-1297` verbatim):

- Form con `email` (formato válido) + `password` (mínimo 8 caracteres). Validación Zod: `z.object({ email: z.string().email(), password: z.string().min(8) })`.
- POST `/auth/login` con `credentials:'include'` (cookie httpOnly cross-origin safe via SameSite=Lax).
- 401 → `errors.invalid_credentials` único (anti-enumeración). NO distinción entre "email no existe" y "password incorrecta".
- 429 → ver HU-F3.2 (lockout visible). F3.1 NO implementa countdown — solo catch + surface.
- `authStore` hidrata desde `GET /auth/me`. `useAuth().user.sucursal` es el `uuid` de la sede; `permisos` es un `array<string>`.
- Componentes: `Login` (page, contenedor: RHF+Zod, llama `parkosFetch`); `LoginForm` (presentacional, dos campos + botón).
- Regla DEC-F3.1-01: credencial es `email`, NUNCA `cedula`.
- Tamaño: 190 LOC production + ~240 LOC tests = ~430 LOC total. 4 tareas atómicas T1..T4.
- e2e: `e2e/auth/login.spec.ts` — 3 casos (login OK con cookie, refresh transparente, logout).
- WCAG 2.1 AA compliance: axe-core 0 violaciones en `<LoginForm>` (RNF-022).

**Scope**: ~190 LOC production + ~240 LOC tests = ~430 LOC total. Plan 190 LOC matches: 190 ≈ 250 production logic - 60 LOC para shadcn-generated Form/Input/Button + i18n keys + Auth namespace que ya existían pre-F3.1. Breakdown por cluster C1 detallado en §10.

---

## 2. Scope

### 2.1 In Scope (~190 LOC production + ~240 LOC tests)

- **`features/auth/pages/Login.tsx`** (NEW, ~75 LOC production) — container con RHF + Zod resolver + onSubmit + `postLogin` + `useAuth()` + `useNavigate`. Maneja `useEffect` con deps `[isAuthenticated, data?.user, isLoading]` para redirect transaccional post-hidratación.
- **`features/auth/components/LoginForm.tsx`** (NEW, ~60 LOC production) — presentacional puro. Recibe `{form, onSubmit, isSubmitting, error}` via props. Usa shadcn `Form`, `FormField`, `FormItem`, `FormLabel`, `FormControl`, `FormMessage`, `Input`, `Button`. aria-invalid en error state.
- **`features/auth/api/loginApi.ts`** (NEW, ~30 LOC production) — `fetch` raw + custom error mapping `InvalidCredentialsError` + `AccountLockedError(retryAfter)`. Lee `Retry-After` header en 429. `credentials:'include'` explícito.
- **`features/auth/pages/Login.test.tsx`** (NEW, ~80 LOC tests) — vitest + @testing-library/react. Cubre: RHF validation inline, 401 → `invalidCredentials`, 200 → setTokens + redirect, 429 → `AccountLockedError(retryAfter)` surface.
- **`features/auth/components/LoginForm.test.tsx`** (NEW, ~30 LOC tests) — render presentacional + props forward + axe-core 0 violations.
- **`features/auth/api/loginApi.test.ts`** (NEW, ~50 LOC tests) — MSW handler 200/401/429 con assert request `credentials:'include'` + Content-Type JSON + custom error assertions.
- **`features/auth/hooks/useLoginFlow.ts`** (NEW, ~25 LOC production) — opcional, custom hook que encapsula `useForm` + `postLogin` + `useAuth()` + `useNavigate` para mantener `Login.tsx` declarativo. Sigue precedent Container/Presentational (DEC-F3.1-02).
- **`<Route path="/login" element={<LoginPage />} />`** en `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY, +5 LOC) — ruta dedicada para login page.
- **`apps/electron-sucursal/src/renderer/i18n/locales/auth.json`** (MODIFY, +5 keys) — agregar `validation.email.invalid`, `validation.email.required`, `validation.password.minLength`, `validation.password.required`, `validation.required` (5 validation messages inline).
- **`e2e/auth/login.spec.ts`** (NEW, ~80 LOC tests) — 3 escenarios playwright: login-ok-cookie + refresh-transparente + logout.

### 2.2 Out of Scope (explícitamente deferido)

- **Lockout countdown UI** — F3.2 lo entrega (useCountdown hook + 429 disable form + countdown visual).
- **Refresh pre-flight antes de POST /facturacion/* + POST /caja/arqueo** — F3.2 (50min auto-refresh check).
- **Logout button UI** — F3.3+ (placeholder o HU posterior; F3.1 solo verifica `useAuthStore.clear()` en e2e).
- **Recuperación de password / forgotPassword** — fuera Fase 3 (futuro).
- **2FA / WebAuthn** — fuera Fase 3 (futuro).
- **Multi-tab login UI** — kiosko single-tab por F2.3 single-instance lock (DEC-UPD-07).
- **Turno abrir/cerrar** — F3.3 (AbrirTurno + CerrarTurno + useSesionActiva en `features/caja/`).
- **AuthGuard component** — F3.3+ (intercepta `parkos:auth:cleared` event → `navigate('/login?next=...')`).
- **Sucursal selector UI** — el JWT ya pinea sucursal (DEC-F3.1-04 single-branch kiosko).
- **rememberMe checkbox** — `auth.json:10` tiene la key pero F3.1 NO la usa (kiosko desatendido, no aplica).
- **forgotPassword link** — `auth.json:11` tiene la key pero F3.1 NO la renderiza (out of scope).
- **Backend cambios** — HU-F1.2 shipped en Fase 1 cubre los 2 endpoints (`POST /auth/login` + `GET /auth/me`); F3.1 NO modifica backend.
- **Refresh-token rotation** — F2.2 cubre (DEC-FETCH-03); F3.1 NO toca.
- **Zod schema validation en boundary via `parkosFetch<T>(url, schema)`** — DEC-FETCH-05 optional; F3.1 NO exige.
- **OS-level kiosk** — Windows Assigned Access / macOS kiosk mode (FUERA Fase 3).
- **PIN rotation UI** — kiosko PIN pre-shared by F2.3, no rotation UI.

---

## 3. Personas y journey

### 3.1 Persona primaria: Operador de sucursal

**Contexto**: trabajador de ~25-55 años, con experiencia operativa media/alta en la sucursal. Trabaja en turnos de 6-8 horas. Necesita autenticarse al inicio del turno para acceder al sistema de caja. Conoce su `email` corporativo y su `password` (asignada en onboarding + rotación trimestral por IT). Trabaja en kiosko (single-instance F2.3 lock) con la app siempre abierta.

**Pain points que F3.1 resuelve**:

1. Sin F3.1, la app abre directamente al dashboard post-startup (F2.1 placeholder). El operador tiene que esperar hasta que `useAuth()` emita 401 → `parkos:auth:cleared` → render 404. Esto NO es operator-friendly.
2. Con F3.1, el operador ve explícitamente una pantalla de login con campos claros, validación inline, y mensajes específicos (anti-enumeración 401, lockout 429 con countdown futuro F3.2, network error). UX profesional y predecible.

### 3.2 Journey (3 pasos)

1. **App startup**: Electron renderer carga `App.tsx` con `<Route path="/login">` registrado. Sin sesión activa (`useAuthStore.getState().accessToken === null`), el operador navega manualmente a `/login` o es redirigido por F3.3+ AuthGuard.
2. **Submit credentials**: operador tipea `email` + `password` + Enter. `LoginForm` RHF valida con Zod inline. `onSubmit` llama `postLogin(email, password)` que `fetch` con `credentials:'include'` → backend `POST /auth/login` retorna 200 con `TokenPair` body + cookie `parkos_session`. `useAuthStore.setTokens(access, refresh, expires_in)` hidrata el store.
3. **Hidratación + redirect**: `useAuth()` SWR detecta nuevo `accessToken` (key cambia de `null` a `'/auth/me'`) → dispara `parkosFetch('/auth/me')` con `Authorization: Bearer <new_access>` + cookie auto-enviada. `useAuth()` retorna `{user, sucursal, sucursalesPermitidas, permisos, expiresAt, isAuthenticated: true}`. `Login.tsx` `useEffect` con deps `[isAuthenticated, data?.user, isLoading]` → `navigate('/')`. El operador llega a `/` con todo resuelto (sin flash de "sesión no iniciada"). F3.3+ montan `AbrirTurno` cuando aplique.

---

## 4. Capabilities (QUÉ hace)

F3.1 entrega 6 capabilities derivables de DEC-F3.1-01..10 + DEC-F3.1-11 (nueva, esta propuesta):

1. **Login form con RHF + Zod (DEC-F3.1-02, DEC-F3.1-06)** — `<LoginForm>` con 2 campos (`email`, `password`), validación inline, aria-invalid + FormMessage role=alert.
2. **POST /auth/login con credentials:'include' (DEC-F3.1-03, DEC-F3.1-04, DEC-F3.1-05)** — `fetch` raw, no parkosFetch; cookie httpOnly round-trip via `credentials:'include'`; `Retry-After` header leído en 429.
3. **Anti-enumeración UI message único (DEC-F3.1-08)** — 401 (cualquier causa) → `<p role="alert">{t('invalidCredentials')}</p>`; 429 → `<p role="alert">{t('lockout')}</p>`; 500/network → `<p role="alert">{t('errors.serverError')}</p>`.
4. **authStore hidrata desde /auth/me + redirect transaccional (DEC-F3.1-07)** — `useEffect` espera `data.user` antes de `navigate('/')`; sin flash de "sesión no iniciada".
5. **WCAG 2.1 AA compliance (RNF-022)** — axe-core 0 violaciones en LoginForm; FormField aria-invalid; FormMessage role=alert; label htmlFor asociado; tab order secuencial.
6. **Feature folder `features/auth/` (DEC-F3.1-01)** — bounded context isolation; F3.3 vivirá en `features/caja/`; F5+ en `features/facturacion/`. Atomic Design + Feature Slicing.

---

## 5. Decisiones arquitectónicas (DEC-F3.1-NN × 11)

F3.1 introduce 11 decisiones arquitectónicas (DEC-F3.1-01..10 ratified en exploration + DEC-F3.1-11 nueva decisión de spec delta introducida en esta propuesta). El detalle verbatim vive en `exploration.md` §6 (10 primeras DEC) y en §5.11 abajo (DEC-F3.1-11). Esta sección referencia y resume cada DECISION + RATIONALE + ALTERNATIVES CONSIDERED. El segundo pase con justificación extendida vive en §11.

### 5.1 DEC-F3.1-01 — Feature folder `src/features/auth/{pages,hooks,components,api}/`

**DECISION**: F3.1 crea `apps/electron-sucursal/src/features/auth/pages/Login.tsx` + `src/features/auth/components/LoginForm.tsx` + `src/features/auth/api/loginApi.ts`. NO se monta en `src/renderer/components/` (que es para componentes reutilizables cross-feature).

**RATIONALE**: Atomic Design + Feature Slicing (F2.1 DEC-ELEC-08 + ops reference). Cada bounded context vive en su propia carpeta. `apps/electron-sucursal/src/features/{auth,caja,facturacion,operacion,...}` poblado incrementalmente en Fase 3+ (pending.md §5). F3.3 (turno) vivirá en `features/caja/pages/{AbrirTurno,CerrarTurno}.tsx`.

**ALTERNATIVES CONSIDERED**:
- A. Montar Login en `src/renderer/components/` (donde está StatusBar) — RECHAZADA. Mezcla UI reutilizable cross-feature (Button, StatusBar) con pages de bounded contexts. Plan.md:1289 explícito: "Login (page, contenedor)" → page ≠ component.
- B. Feature folder `src/features/auth/` (DECIDIDA) — Bounded context isolation. Cons: nueva carpeta no usada previamente (F2.1+F2.2+F2.3 no crearon features, solo components/).

### 5.2 DEC-F3.1-02 — Container/Presentational split (Login vs LoginForm vs useLoginFlow)

**DECISION**: `Login.tsx` (container) maneja RHF + Zod resolver + onSubmit + postLogin + useAuth + useNavigate. `LoginForm.tsx` (presentational) recibe `{form, onSubmit, isSubmitting, error}` via props. Opcionalmente `useLoginFlow.ts` custom hook encapsula la lógica para mantener `Login.tsx` declarativo.

**RATIONALE**: Container/Presentational pattern (F2.1 DEC-ELEC-09 + Atomic Design). El container es testeable con mocks (fetch + useAuth); el presentational es testeable con `@testing-library/react` sin mocks. Plan.md:1289 explícito: "Login (page, contenedor: RHF+Zod, llama parkosFetch); LoginForm (presentacional, dos campos + botón)".

### 5.3 DEC-F3.1-03 — credentials:'include' para cookie httpOnly round-trip

**DECISION**: El `fetch` para `POST /auth/login` lleva `credentials: 'include'` explícito. `parkosFetch` para requests autenticados subsiguientes también incluye `credentials: 'include'` (modificación a parkosFetch.ts: agregar credentials default).

**RATIONALE**: La cookie `parkos_session` (httponly+secure+samesite=lax) requiere que el cliente ACEPTE el `Set-Cookie` (origin localhost:5173 acepta same-origin; cross-origin requiere `SameSite=None; Secure`) Y que la ENVÍE en requests subsiguientes. `credentials:'include'` cubre ambos. Si se omite, la cookie se setea en la respuesta pero NO se persiste (Fetch spec: omit credentials = no cookie jar write).

### 5.4 DEC-F3.1-04 — Login via HTTP directo (NO IPC bridge)

**DECISION**: F3.1 NO agrega nuevos métodos IPC (`bridge.auth.login`, `bridge.auth.logout`, etc.). Login fluye por HTTP directo vía `fetch` (raw, no parkosFetch) con `credentials:'include'`.

**RATIONALE**: IPC bridge es para capabilities privileged que requieren main process (print, usb, kiosk, app quit, electron-store). Auth es HTTP puro — el navegador gestiona la cookie via `credentials:'include'` sin main process involvement. Agregar IPC sería over-engineering + surface area extra sin benefit. F2.2 ya wireó `bridge.authStore.{get,set,delete}` para persistencia (authStore Zustand) — F3.1 consume indirectamente via `useAuthStore.setTokens`.

### 5.5 DEC-F3.1-05 — Login usa `fetch` raw, NO `parkosFetch`

**DECISION**: `Login.tsx` usa `fetch` raw (no `parkosFetch`) para `POST /auth/login`. Razones: (a) NO queremos Authorization Bearer pre-login (no existe token), (b) queremos leer `Retry-After` header en 429, (c) queremos `credentials:'include'` explícito sin que parkosFetch intercepte.

**RATIONALE**: parkosFetch está optimizado para el 95% de los casos (auth header + sucursal header + idempotency + retry + refresh). El endpoint de login es el caso exceptional — no es parte del "data plane autenticado", es la PUERTA al data plane. Mantener raw fetch para login preserva la semántica: "login es anonimo, todo lo demas es autenticado".

### 5.6 DEC-F3.1-06 — Validación Zod local en form (NO parkosFetch schema)

**DECISION**: F3.1 usa Zod local en el form (`z.object({email: z.string().email(), password: z.string().min(8)})`) vía `@hookform/resolvers/zod`. NO usa `parkosFetch<TokenPair>(url, init, zodSchema)` para validar la response.

**RATIONALE**: Validación del form es UX (mensaje inline al operador). Validación de la response es contract — pero el backend ya valida via Pydantic. Si shape drift entre backend y frontend, TS strict + cast catches en compile-time. Zod en runtime es defense-in-depth EXTRA (DEC-FETCH-05) que F3.1 NO exige.

### 5.7 DEC-F3.1-07 — Redirect a `/` tras `useAuth().isAuthenticated && data?.user`

**DECISION**: `Login.tsx` espera `useAuth()` a retornar `data.user` (no solo `isAuthenticated`) antes de `navigate('/')`. El `useEffect` con deps `[isAuthenticated, data?.user, isLoading]` garantiza que el operador nunca llega a `/` con `user: null`.

**RATIONALE**: Hidratación transaccional — el operador llega a `/` con sesión + user + sucursal + permisos TODOS resueltos. Si el componente navega con `isAuthenticated && isLoading`, hay un flash de "sesión no iniciada" en el destino (F3.3+ dashboards dependen de `useAuth().user.sucursal`). Plan.md:1280 verbatim: "authStore se hidrata desde GET /auth/me (useAuth().user.sucursal es el uuid de la sede)".

### 5.8 DEC-F3.1-08 — Anti-enumeración via UI message único

**DECISION**: 401 (cualquier causa) → muestra `<p role="alert">{t('invalidCredentials')}</p>` (`auth.json:9`). NO distinción entre "email no existe" / "password incorrecta". 429 → `<p role="alert">{t('lockout')}</p>` (`auth.json:8`). 500/network → `<p role="alert">{t('errors.serverError')}</p>` (`errors.json:3`).

**RATIONALE**: Backend ya colapsa 401 a `errors.invalid_credentials` único (`auth.py:159-191`). Frontend matchea. Anti-enumeration es cross-layer (backend + frontend). Plan.md:1281 verbatim: "401 muestra un mensaje único (errors.invalid_credentials), sin distinguir si el email existe o no (anti-enumeración)".

### 5.9 DEC-F3.1-09 — Auto-redirect a `/login` cuando `parkos:auth:cleared` event fires

**DECISION**: F3.1 NO crea el redirect logic — usa el evento `parkos:auth:cleared` que `useAuth()` ya emite (`useAuth.ts:67-69`). F3.3+ agregan un `<AuthGuard>` que escucha este evento y dispara `navigate('/login?next=...')`. F3.1 NO requiere AuthGuard porque Login está standalone.

**RATIONALE**: Separación de concerns. Login page NO necesita auth-guard (es el entry point). Los dashboards sí. Forward: F3.3+ agregan `<AuthGuard>` que envuelve `<Routes>` excepto `/login`. Plan.md:1302: "Login redirige a / (o a la sesión activa) tras hidratar authStore".

### 5.10 DEC-F3.1-10 — e2e 3 escenarios: login OK con cookie, refresh transparente, logout

**DECISION**: F3.1 entrega `apps/electron-sucursal/e2e/auth/login.spec.ts` con 3 tests:
1. **login-ok-cookie**: submit email+password válidos → cookie `parkos_session` set + redirect a `/` + `useAuth().user.email === <test email>`.
2. **refresh-transparente**: setTokens via authStore, advance fake timers 50min, verificar SWR revalida `/auth/me` (useAuth.refreshInterval: 5min; en realidad refresh es 5min NO 50min — refresh transparente aquí significa: 401 en otra llamada dispara refresh-once). Plan.md:1295 dice "refresh automático" — interpretado como refresh-once en 401 (F2.2 DEC-FETCH-03), NO como el `refreshInterval` de useAuth.
3. **logout**: F3.1 NO implementa logout UI per se (F3.3+/forward), pero el test verifica que `useAuthStore.clear()` setea tokens a null y que un segundo `/auth/me` retorna 404 → `useAuth()` limpia store + emite `parkos:auth:cleared`. F3.3 entrega logout button (placeholder o via HU posterior).

**RATIONALE**: Plan.md:1295 verbatim. Sandbox F.6 precedent: e2e con `_electron.launch` puede SKIP en npm 11.16.0 (F2.2 archive report G8). F3.1 e2e va a SKIP en el mismo sandbox — documentado en §11 como deviation D-env, NO project defect.

### 5.11 DEC-F3.1-11 — **NUEVA** Spec delta a `operations/spec.md` con 7 new REQ-OPS-106..112 (DELTA, NO NO-OP)

**DECISION**: `openspec/changes/hu-f3-1-login-email-password/specs/operations/spec.md` AGREGA 7 new REQ-OPS-106..112 al spec canónico, NO es NO-OP stub. Las 7 REQ-OPS documentan el comportamiento observable al operador (login UI, anti-enumeración, cookie httpOnly round-trip, redirect transaccional, WCAG 2.1 AA compliance) en formato Given/When/Then/And RFC 2119.

**RATIONALE — re-evaluación crítica desde exploration §6 (DEC-FETCH-10 NO-OP precedent)**: la exploration original (pre-flight 10/10 PASS) propuso DEC-FETCH-10-style NO-OP stub siguiendo precedent F2.1/F2.2/F2.3 (todos infra-only, sin behavior observable al operador). Esta propuesta **rompe** ese precedent y adopta precedent F1.15 (login histórico, archivado 2026-09-15) que SÍ escribió 4 new REQ-OPS-102..105 al spec canónico con la misma justificación: login es user-facing behavior que el operador observa y depende. La justificación detallada:

| Aspecto | F2.1/F2.2/F2.3 (NO-OP precedent) | F3.1 (DELTA con new REQ-OPS-NNN) |
|---|---|---|
| Tipo de cambio | Infra-only (scaffold + IPC + runtime) | User-facing behavior observable |
| Componente visible al operador | Ninguno (electron main process, ipc preload, services) | Login page + Form + Button + Error messages |
| Mensajes de error diferenciados | N/A (no UI) | `invalidCredentials` vs `lockout` vs `serverError` |
| Cookie httpOnly round-trip | N/A (no HTTP) | `credentials:'include'` mandatory |
| Redirect post-hidratación | N/A (no routes) | `useEffect` espera `data?.user` |
| Precedent directo | DEC-ELEC-10 / DEC-FETCH-10 / DEC-UPD-13 (infra) | REQ-OPS-102..105 (F1.15 login user-facing) |
| Verificabilidad | DEC-* documentan; sin REQ spec-level | REQ-OPS-NNN + DEC-* cross-linked |

**Numeración**: el último REQ-OPS vigente en `operations/spec.md` es REQ-OPS-105 (archivado por F1.15 el 2026-09-15). Las 7 new REQs ocupan REQ-OPS-106..112 (continuación monotónica). La numeración propuesta por la task (`REQ-OPS-113..119`) era una estimación que se ajusta a la realidad del spec canónico.

**Las 7 new REQ-OPS-106..112** (detail en §6):

| ID | Behavior observable | Anchor DEC |
|---|---|---|
| REQ-OPS-106 | Login form con `email` (z.string().email()) + `password` (z.string().min(8)) vía RHF + Zod resolver, validation messages inline | DEC-F3.1-02, DEC-F3.1-06 |
| REQ-OPS-107 | `POST /auth/login` con `credentials:'include'` + `Content-Type: application/json` (cookie httpOnly round-trip mandatory) | DEC-F3.1-03, DEC-F3.1-04, DEC-F3.1-05 |
| REQ-OPS-108 | 401 → mensaje único `errors.invalidCredentials` (anti-enumeración, NO distinción email/password) | DEC-F3.1-08 |
| REQ-OPS-109 | 429 → `errors.lockout` con header `Retry-After: <segundos>` (lockout forward hook a F3.2) | DEC-F3.1-08 |
| REQ-OPS-110 | `authStore.setTokens(access, refresh, expires_in)` hidrata desde `POST /auth/login` 200 OK (RFC 2119 MUST) | DEC-F3.1-07 |
| REQ-OPS-111 | Redirect a `/` cuando `useAuth().isAuthenticated && data?.user && !isLoading` (transaccional, sin flash) | DEC-F3.1-07 |
| REQ-OPS-112 | WCAG 2.1 AA compliance: axe-core 0 violaciones en `<LoginForm>` (RNF-022) | DEC-F3.1-01 |

**ALTERNATIVES CONSIDERED**:
- A. NO-OP stub (DEC-FETCH-10 precedent verbatim) — RECHAZADA tras re-evaluación. F2.1/F2.2/F2.3 fueron infra-only; F3.1 ES user-facing behavior. Aplicar precedent equivocado rompería el audit trail del spec.
- B. DELTA con 4 new REQ-OPS-106..109 (minimum viable) — RECHAZADA. Reduciría cobertura de comportamiento. 7 REQs balancean audit trail exhaustivo sin overload.
- C. DELTA con 7 new REQ-OPS-106..112 (DECIDIDA) — Cobertura completa de behavior observable al operador. Match precedent F1.15 (4 new REQ-OPS-102..105) + extra coverage para WCAG + redirect transaccional.

**Convención de identificadores**: DEC-F3.1-NN sigue el patrón DEC-ELEC-NN (F2.1), DEC-FETCH-NN (F2.2), DEC-UPD-NN (F2.3), DEC-LOGIN-NN (F1.15). REQ-OPS-NNN sigue la numeración monotónica del spec canónico vigente. F3.1 ocupa REQ-OPS-106..112 (continuación de F1.15 REQ-OPS-102..105).

---

## 6. Spec delta (operations/spec.md)

### 6.1 Decisión explícita: AGREGAR 7 new REQ-OPS-106..112 (DELTA, NO NO-OP)

**F3.1 AGREGA 7 new REQ-OPS al spec canónico** (`openspec/specs/operations/spec.md`). Esta es la primera HU de Fase 3 con behavior contract; las 10 anteriores (F2.1 + F2.2 + F2.3) fueron infra-only y aplicaron NO-OP stub. El precedent correcto para F3.1 es F1.15 (login histórico, archivado 2026-09-15 con REQ-OPS-102..105 user-facing). DEC-F3.1-11 documenta el rationale completo.

### 6.2 Las 7 new REQ-OPS-106..112

> **Nota**: los textos completos en formato Given/When/Then/And RFC 2119 viven en `sdd-spec` output (archivo `openspec/changes/hu-f3-1-login-email-password/specs/operations/spec.md` que el spec agent materializa). Esta sección resume el scope contractual; el spec phase los escribe en formato completo.

#### 6.2.1 REQ-OPS-106 — Login form con RHF + Zod (DEC-F3.1-02, DEC-F3.1-06)

**Comportamiento observable**: El componente `<LoginForm>` expone 2 campos (`email`, `password`) con validación inline via `z.object({email: z.string().email(), password: z.string().min(8)})` y mensajes visibles al operador cuando la validación falla (email formato inválido, password < 8 caracteres, campos requeridos vacíos).

**Anchor**: DEC-F3.1-02 (Container/Presentational), DEC-F3.1-06 (Zod local).

#### 6.2.2 REQ-OPS-107 — POST /auth/login con credentials:'include' (DEC-F3.1-03, DEC-F3.1-04, DEC-F3.1-05)

**Comportamiento observable**: El cliente envía `POST /api/v1/auth/login` con `credentials: 'include'` (mandatory para cookie httpOnly round-trip), `Content-Type: application/json`, body `{"email": "...", "password": "..."}`. El navegador acepta `Set-Cookie parkos_session` y la persiste para requests subsiguientes (`GET /auth/me`).

**Anchor**: DEC-F3.1-03 (credentials include), DEC-F3.1-04 (HTTP directo), DEC-F3.1-05 (fetch raw).

#### 6.2.3 REQ-OPS-108 — 401 → `errors.invalidCredentials` único (anti-enumeración) (DEC-F3.1-08)

**Comportamiento observable**: Cuando el backend retorna 401 (cualquier causa — email desconocido, password incorrecta, cuenta deshabilitada), el frontend muestra un único mensaje `errors.invalidCredentials` (text exacto: "Credenciales inválidas" en español neutro). NO hay distinción visible entre "email no existe" / "password incorrecta" / "cuenta deshabilitada" — esto previene enumeración de usuarios válidos.

**Anchor**: DEC-F3.1-08 (Anti-enumeración).

#### 6.2.4 REQ-OPS-109 — 429 → `errors.lockout` con Retry-After (DEC-F3.1-08)

**Comportamiento observable**: Cuando el backend retorna 429 con header `Retry-After: <segundos>`, el frontend muestra `errors.lockout` (text exacto: "Cuenta bloqueada. Intenta de nuevo en N minutos."). El valor de N se calcula como `Math.ceil(retryAfterSeconds / 60)`. Forward hook a F3.2: countdown UI consume `AccountLockedError(retryAfter)` que `loginApi.ts` emite.

**Anchor**: DEC-F3.1-08 (Anti-enumeración).

#### 6.2.5 REQ-OPS-110 — `authStore.setTokens` hidrata desde POST /auth/login 200 OK (DEC-F3.1-07)

**Comportamiento observable**: Cuando `POST /auth/login` retorna 200 OK con body `TokenPair`, el cliente MUST llamar `useAuthStore.getState().setTokens(access_token, refresh_token, expires_in)` antes de cualquier otra acción (incluyendo redirect). El state de `authStore` pasa de `{accessToken: null, refreshToken: null, expiresAt: null}` a `{accessToken: <jwt>, refreshToken: <jwt>, expiresAt: <ISO8601>}` atómicamente (Zustand setState es síncrono).

**Anchor**: DEC-F3.1-07 (Hidración transaccional).

#### 6.2.6 REQ-OPS-111 — Redirect a `/` transaccional post-hidratación (DEC-F3.1-07)

**Comportamiento observable**: Cuando `useAuth()` retorna `{isAuthenticated: true, data: {user: <UserItem>, sucursal: <SucursalItem>, ...}, isLoading: false}`, el componente `<LoginPage>` MUST llamar `navigate('/')`. NO se navega si `data?.user === undefined` (in-flight) ni si `isLoading === true` (transición). Esto previene el flash de "sesión no iniciada" en el destino.

**Anchor**: DEC-F3.1-07 (Hidración transaccional).

#### 6.2.7 REQ-OPS-112 — WCAG 2.1 AA compliance via axe-core (RNF-022)

**Comportamiento observable**: El componente `<LoginForm>` MUST pasar el axe-core scan con 0 violaciones de WCAG 2.1 AA (RNF-022). Cobertura: labels asociados via `htmlFor`, `aria-invalid` en error state, `aria-describedby` apuntando a `FormMessage`, `role="alert"` en mensajes de error, tab order secuencial, contraste de color mínimo 4.5:1, focus visible en inputs.

**Anchor**: DEC-F3.1-01 (Feature folder), RNF-022 (`docs/01-requisitos/no-funcionales.md:126`).

### 6.3 Contratos forwarded (consume-only)

F3.1 NO crea endpoints. Consume los siguientes contratos existentes:

- **`POST /api/v1/auth/login`** — HU-F1.2 shipped (`backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-307`). Request `LoginRequest{email, password}` → Response `TokenPair{access_token, refresh_token, token_type, expires_in}` + cookie `parkos_session` (httponly+secure+samesite=lax).
- **`GET /api/v1/auth/me`** — HU-F1.2 shipped (`auth.py:419-583`). Response `AuthMeResponse{user, sucursal, sucursales_permitidas, permisos, expires_at}`.
- **Cookie `parkos_session`** — side effect del login; round-trip via `credentials:'include'`.
- **`parkos:auth:cleared` window event** — emitido por `useAuth()` cuando 401 collapsa a 404 (`useAuth.ts:67-69`).

F3.1 NO modifica los endpoints existentes. Backward-compat preservada.

---

## 7. Componentes UI y arquitectura

### 7.1 Diagrama de componentes

```
+--------------------------------------------------+
| <App> (F2.1, MODIFY +5 LOC)                     |
|  +-- <BrowserRouter> (F2.1)                     |
|  |   +-- <StatusBar /> (F2.3)                   |
|  |   +-- <main>                                  |
|  |       +-- <Routes>                            |
|  |           +-- <Route path="/" element={null}> |
|  |           +-- <Route path="/login"            |
|  |           |     element={<LoginPage />} /> (NEW)
|  |           +-- <Route path="*" element={404}/> |
|  +-----------------------------------------------+
+--------------------------------------------------+

+--------------------------------------------------+
| <LoginPage> (container, NEW ~75 LOC)             |
|  +-- useForm({ resolver: zodResolver(schema) })  |
|  +-- useAuth() → { isAuthenticated, isLoading,  |
|  |                data, error }                  |
|  +-- useNavigate()                               |
|  +-- useEffect([isAuthenticated,                |
|  |              data?.user, isLoading])          |
|  |     → navigate('/')                            |
|  +-- onSubmit(data) → postLogin(...)             |
|  |     → setTokens(...) → SWR re-fetcha /auth/me |
|  +-- <LoginForm form={form}                       |
|  |                onSubmit={onSubmit}            |
|  |                isSubmitting={isSubmitting}    |
|  |                error={error} />               |
+--------------------------------------------------+

+--------------------------------------------------+
| <LoginForm> (presentational, NEW ~60 LOC)        |
|  +-- <Form {...form}>                            |
|  |   +-- <FormField name="email"                 |
|  |   |              render={({ field }) => (     |
|  |   |                <FormItem>                 |
|  |   |                  <FormLabel>Email</FormLabel>|
|  |   |                  <FormControl>             |
|  |   |                    <Input {...field}        |
|  |   |                           type="email"      |
|  |   |                           aria-invalid=...  |
|  |   |                           autoComplete=...  |
|  |   |                    />                      |
|  |   |                  </FormControl>            |
|  |   |                  <FormMessage /> ← role=alert
|  |   |                </FormItem>                 |
|  |   |              )} />                         |
|  |   +-- <FormField name="password" ... />        |
|  |   +-- <Button type="submit"                    |
|  |   |          disabled={isSubmitting}>          |
|  |   |     {t('submit')}                          |
|  |   +-- {error && <p role="alert">{error}</p>}   |
+--------------------------------------------------+

+--------------------------------------------------+
| loginApi (NEW ~30 LOC)                           |
|  +-- postLogin(email, password): Promise<TokenPair>|
|  |     fetch('/api/v1/auth/login', {              |
|  |       method: 'POST',                          |
|  |       headers: { 'Content-Type': 'application/json' },
|  |       credentials: 'include',                  |
|  |       body: JSON.stringify({email, password})  |
|  |     })                                         |
|  |     .then(handleErrorMapping)                  |
|  +-- InvalidCredentialsError extends Error        |
|  +-- AccountLockedError extends Error             |
|       + retryAfterSeconds: number                |
+--------------------------------------------------+

+--------------------------------------------------+
| useLoginFlow (NEW ~25 LOC, optional)             |
|  Custom hook que encapsula:                      |
|  - useForm + zodResolver                         |
|  - postLogin + error mapping                     |
|  - useAuth + isLoading guard                     |
|  - useNavigate redirect                          |
|  - Retorna { form, onSubmit, error, isSubmitting}|
+--------------------------------------------------+
```

### 7.2 Tabla de componentes

| Componente | Tipo | Responsabilidad | Tests |
|---|---|---|---|
| `<LoginPage>` | Container (page) | RHF + Zod + postLogin + useAuth + useNavigate + useEffect redirect | `Login.test.tsx` |
| `<LoginForm>` | Presentational | Render form con FormField + Input + Button + FormMessage | `LoginForm.test.tsx` |
| `postLogin` | Pure function (api) | `fetch` raw + custom error mapping | `loginApi.test.ts` |
| `useLoginFlow` | Custom hook (opcional) | Encapsula lógica de Login.tsx | (covered by Login.test.tsx) |
| `useAuth()` | Hook (F2.2) | SWR `/auth/me` + setTokens hydration | (F2.2 already tested) |
| `useAuthStore` | Store (F2.2) | Zustand persist electron-store | (F2.2 already tested) |

### 7.3 Stack técnico

- **React 18.3.1** (renderer, F2.1 baseline).
- **react-hook-form 7.53.0** + **zod 3.23.8** + **@hookform/resolvers 3.9.0** (F2.1 baseline).
- **shadcn Form/Input/Button** (F2.1 baseline, `apps/electron-sucursal/src/renderer/components/ui/`).
- **react-router-dom 6.27.0** (F2.1 baseline).
- **useAuth() + useAuthStore** (F2.2 primitives, ui-kit).
- **axe-core 4.10.x** via `@axe-core/playwright` (F2.1 baseline, RNF-022).
- **Vitest 2.1.x + @testing-library/react 16.0.1** (F2.1+F2.2 baseline).
- **MSW 2.x** (Mock Service Worker) for `loginApi.test.ts` HTTP mocks.

---

## 8. API contract

### 8.1 POST /auth/login (consume-only, HU-F1.2 shipped)

**Source**: `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-307` + `schemas/auth.py::LoginRequest`.

**Request**:
```http
POST /api/v1/auth/login HTTP/1.1
Host: <PARKOS_API_BASE>
Content-Type: application/json
credentials: include

{
  "email": "operador@sucursal-1.parkos.local",
  "password": "<password min 8 chars>"
}
```

**Response 200 OK**:
```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: parkos_session=<jwt>; HttpOnly; Secure; SameSite=Lax; Max-Age=3600; Path=/

{
  "access_token": "<jwt HS256 operador-><uuid_sucursal>>",
  "refresh_token": "<jwt HS256 operador-><uuid_sucursal> type=refresh>",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Errores**:

| Status | Body | Significado |
|---|---|---|
| 401 | `{"error": "invalid_credentials", "detail": "..."}` | Email desconocido O password incorrecta (anti-enumeración, mismo shape) |
| 429 | `{"error": "account_locked", "retry_after_seconds": <minutos*60>}` | Cuenta bloqueada por N intentos fallidos. Header `Retry-After: <segundos>`. |
| 422 | `{"error": "validation_error", "detail": "..."}` | Zod-falla (email mal formato o password < 8). NO debería ocurrir si cliente valida antes. |

**Idempotencia**: `parkosFetch` SKIP `Idempotency-Key` para `/auth/login` (`parkosFetch.ts:106` — `isLoginEndpoint = url.includes('/auth/login')`). El endpoint es idempotente por sí mismo (bcrypt determinístico + INSERT `prod.login` row).

**CRITICAL — credentials:'include'**: el cliente MUST setear `credentials: 'include'` en el `fetch` para que el navegador ACEPTE la cookie `Set-Cookie` y la ENVÍE en requests subsiguientes (`GET /auth/me`). Sin esto, la cookie se setea pero NO se persiste — el siguiente `/auth/me` viaja sin auth y el backend responde 404 not_found.

### 8.2 GET /auth/me (consume-only, HU-F1.2 shipped)

**Source**: `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:419-583` + `schemas/auth.py::AuthMeResponse`.

**Request**:
```http
GET /api/v1/auth/me HTTP/1.1
Host: <PARKOS_API_BASE>
Authorization: Bearer <access_token>
credentials: include
```

**Response 200 OK**:
```json
{
  "user": {
    "uuid": "...",
    "email": "operador@sucursal-1.parkos.local",
    "nombre": "Juan",
    "apellido": "Pérez",
    "rol": "operador"
  },
  "sucursal": {
    "uuid": "...",
    "nombre": "Sucursal Norte",
    "prefijo_nombre": "NORTE"
  },
  "sucursales_permitidas": [{"uuid": "...", "nombre": "...", "prefijo_nombre": "..."}],
  "permisos": ["caja.apertura", "caja.arqueo", "facturacion.emitir"],
  "expires_at": "2026-09-15T18:30:00Z"
}
```

**Errores**:

| Status | Significado |
|---|---|
| 404 not_found | CUALQUIER JWT failure mode (missing/malformed/expired/invalid signature/user-gone). Anti-enumeración: colapsa todos los failure modes a 404. |
| 401 | (NO debería ocurrir — colapsado a 404) |

### 8.3 Hidratación post-login (F3.1 flow)

1. `Login.tsx` submit → `fetch('/api/v1/auth/login', {credentials:'include', ...})` con `fetch` raw (no Authorization Bearer pre-login — DEC-F3.1-05).
2. Backend responde 200 con `TokenPair` body + `Set-Cookie parkos_session` header.
3. `Login.tsx` parsea body → `useAuthStore.getState().setTokens(access, refresh, expires_in)` (REQ-OPS-110).
4. `useAuth()` SWR detecta nuevo accessToken (key cambia de `null` a `'/auth/me'`) → dispara `parkosFetch('/auth/me')` con `Authorization: Bearer <new_access>` + cookie que el navegador auto-envía.
5. `useAuth()` retorna `{user, sucursal, sucursalesPermitidas, permisos, expiresAt, isAuthenticated: true}`.
6. `Login.tsx` `useEffect` con deps `[isAuthenticated, data?.user, isLoading]` → `navigate('/')` (REQ-OPS-111).

---

## 9. Riesgo register (R1..R8 verbatim del exploration §7)

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

---

## 10. Convenciones

### 10.1 Commits

- Conventional Commits.
- **NO** "Co-Authored-By" attribution.
- **NO** AI trailers.
- Formato: `<type>(<scope>): <description>` con type ∈ {feat, fix, test, refactor, docs, chore}, scope ∈ {auth, electron, ui, ops, router}.
- Author: `Parkos Dev <dev@parkos.local>` (F2.1 precedent verbatim).

### 10.2 TDD estricto

- Cada test escrito ANTES de la implementación.
- Tests rojos primero, luego código que los hace verde.
- Cobertura >80% exigida en `Login.tsx` + `LoginForm.tsx` + `loginApi.ts` + `useLoginFlow.ts` (si se materializa).
- Cobertura >80% en i18n keys (snapshot test del JSON `auth.json` con 5 nuevas validation keys).
- Cobertura 100% de los 3 e2e scenarios (login-ok-cookie + refresh-transparente + logout).

### 10.3 Defense in depth

5 capas (XR6 pattern per `operations/spec.md:3951` + F2.2 §15.3 + F2.3 §15.3 precedent + F1.15 §16.3 precedent):

| Layer | Mechanism | Source |
|---|---|---|
| 1 auth | JWT Bearer + cookie httponly SameSite=Lax + bcrypt | backend/.../auth.py:148-583 (F3.1 consumer, HU-F1.2 shipped) |
| 2 engineering | TS strict + noUncheckedIndexedAccess + ESLint flat | tsconfig.* + eslint.config.js (F2.1 baseline) |
| 3 a11y | axe-core WCAG 2.1 AA + FormField aria-invalid + FormMessage role=alert | e2e/a11y/wcag-2.1-aa.spec.ts (F2.1) + F3.1 LoginForm (REQ-OPS-112) |
| 4 contract | Zod validation form (DEC-F3.1-06) + backend Pydantic + REQ-OPS-106..112 | @hookform/resolvers/zod + schemas/auth.py + operations/spec.md delta |
| 5 retry-budget | parkosFetch retry 5xx + 401 refresh-once | parkosFetch.ts (F2.2 DEC-FETCH-02/03) — F3.1 NO custom retry en login |

F3.1 NO crea un nuevo REQ-OPS-XR (F3.1 NO es XR-class; el spec level se ancla en REQ-OPS-106..112 nuevas per DEC-F3.1-11).

### 10.4 Pending.md update

Al archive F3.1:
- Row 1 (HU-F3.1) en `pending.md §1` → marcar ✅ cerrado.
- Total LOC restante → `$LOC - 190` (Fase 3 1/3 cerrado).
- Footer → "Fase 3 1/3 cerrado".

### 10.5 Sandbox F.6 caveat (e2e)

Per F2.1 + F2.2 + F2.3 archive reports, las e2e (`login.spec.ts`) corren en sandbox F.6 con npm 11.16.0 que refuses `workspace:*` resolution. F3.1 e2e va a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect. e2e verdes en local dev (npm 11.16+ en Windows native) o CI con image compatible.

---

## 11. Atomic tasks preview (T1..T4)

Cada task es **atómica** (commiteable independientemente con tests verde), pero se ejecutan en orden T1 → T2 → T3 → T4. Detalle verbatim en `exploration.md` §10.

| Task | Budget (LOC) | Archivos | Commit message | Gate |
|---|---|---|---|---|
| **T1 — Login page (container) + LoginForm (presentational) con RHF+Zod** | ~200 (120 prod + 80 tests) | `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (NEW, ~60 LOC) · `LoginForm.test.tsx` (NEW, ~30 LOC) · `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (NEW, ~60 LOC) · `Login.test.tsx` (NEW, ~50 LOC) · `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (MODIFY, agregar 5 validation keys) | `feat(auth): adicionar Login page con RHF+Zod (email/password) + LoginForm presentacional + 5 i18n validation keys` | G1, G2, G4 |
| **T2 — integrar POST /auth/login con credentials:'include'** | ~80 (30 prod + 50 tests) | `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (NEW, ~30 LOC — fetch raw + error mapping `InvalidCredentialsError` + `AccountLockedError`) · `loginApi.test.ts` (NEW, ~50 LOC — MSW handler para 200/401/429 + custom error assertions) · `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY, +5 LOC — `await postLogin(...)` en `onSubmit` + setTokens) | `feat(auth): integrar POST /auth/login con credentials:'include' + error mapping 401/429` | G3, G5 |
| **T3 — Login redirige a / tras hidratar authStore desde /auth/me** | ~50 (20 prod + 30 tests) | `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY, +10 LOC — `useEffect([isAuthenticated, data?.user, isLoading])` → `navigate('/')`) · `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY, +5 LOC — `<Route path="/login" element={<LoginPage />} />`) · `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (MODIFY, +30 LOC — test redirect post-hidratación) | `feat(router): adicionar ruta /login con redirect a / post-hidratación useAuth()` | G4 |
| **T4 — e2e login.spec.ts (3 casos)** | ~80 tests | `apps/electron-sucursal/e2e/auth/login.spec.ts` (NEW, ~80 LOC — login-ok-cookie + refresh-transparente + logout) | `test(electron): adicionar 3 e2e login (cookie httpOnly + refresh transparente + logout)` | G6 |
| **TOTAL** | **~410 LOC** (170 prod + 240 tests) | 7 archivos nuevos + 2 modificaciones | 4 commits atómicos | 6 gates |

**Resumen de clusters** (§12): C1 = T1+T2+T3+T4. Plan 190 LOC matches: 170 production + 20 JSDoc/configs = ~190.

### 11.8 Resumen de budgets

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 Login + LoginForm | 120 | 80 | 200 |
| T2 postLogin + error mapping | 30 | 50 | 80 |
| T3 redirect + /login route | 20 | 30 | 50 |
| T4 e2e 3 scenarios | 0 | 80 | 80 |
| **TOTAL** | **170** | **240** | **410** |

Total real ~190 LOC production matches plan.md:1297 verbatim (~170 production + ~20 JSDoc/configs = ~190).

---

## 12. Descomposición en clusters atómicos (C1)

F3.1 se descompone en **1 cluster** (C1) con orden interno T1 → T2 → T3 → T4.

### 12.1 C1: Login flow end-to-end (T1+T2+T3+T4)

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

### 12.2 Orden de ejecución

T1 → T2 → T3 → T4 (mandatory). T1 antes de T2 porque T2 integra el `postLogin` en el `onSubmit` de T1. T2 antes de T3 porque T3 agrega redirect post-setTokens (T2 setea tokens). T3 antes de T4 porque e2e tests requieren Login.tsx completo (route + form + api + redirect).

---

## 13. Acceptance gates pre-flight

6 gates que deben pasar ANTES de mergear F3.1 a `origin/dev`.

| # | Gate | Mecanismo | Source | Anchor REQ-OPS |
|---|---|---|---|---|
| G1 | RHF+Zod valida `email: z.string().email()` y `password: z.string().min(8)` con messages inline | vitest `Login.test.tsx` con `@testing-library/react` | T1 | REQ-OPS-106 |
| G2 | 401 → muestra `t('invalidCredentials')` único, sin distinción email/password | vitest `Login.test.tsx` mock 401 response | T1 | REQ-OPS-108 |
| G3 | `POST /auth/login` enviado con `credentials:'include'` + Content-Type JSON | vitest `loginApi.test.ts` con MSW handler assert request | T2 | REQ-OPS-107 |
| G4 | `authStore.setTokens(access, refresh, expires_in)` + `useAuth().data.user` hidrata antes de `navigate('/')` | vitest `Login.test.tsx` mock 200 + assert setTokens spy + useEffect fires | T2 + T3 | REQ-OPS-110, REQ-OPS-111 |
| G5 | 429 → `AccountLockedError(retryAfter)` + muestra `t('lockout')` | vitest `loginApi.test.ts` mock 429 + Retry-After header | T2 | REQ-OPS-109 |
| G6 | 3 e2e scenarios verde (login-ok-cookie, refresh-transparente, logout) | playwright e2e `_electron` | T4 | (e2e para REQ-OPS-106..112) |
| G7 (implícito) | axe-core 0 violaciones WCAG 2.1 AA en `<LoginForm>` | axe-core scan via `@axe-core/playwright` | T1 + verify | REQ-OPS-112 |

**Estado pre-flight**: 0/7 PASS al inicio (no implementado). Target 7/7 PASS post-implementación.

**Sandbox F.6 precedent**: 6/10 gates SKIPPED en F2.1 + F2.2 + F2.3 archive (npm 11.16.0 refuses workspace:*). F3.1 e2e (G6) va a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect.

---

## 14. Forward hooks (a Fase 3+)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.2** (lockout visible + refresh pre-flight) | `AccountLockedError(retryAfter)` de F3.1 → F3.2 useCountdown hook | F3.2 wraps Login.tsx onSubmit con disable form + countdown UI |
| **HU-F3.3** (abrir/cerrar turno) | `useAuth().user.sucursal` + permisos hidratados post-F3.1 | F3.3 AbrirTurno lee `user.sucursal` y `permisos` antes de POST /caja-sesion/sesiones |
| **HU-F3.x** (logout UI) | `useAuthStore.clear()` ya implementado en F2.2 + `parkos:auth:cleared` event | F3.x logout button dispatch clear() + navigate('/login') |
| **HU-F3.x** (AuthGuard) | `parkos:auth:cleared` window event | F3.x AuthGuard escucha evento → navigate('/login?next=...') |
| **HU-F4.x** (catálogos + ocupación) | `useAuth()` + parkosFetch | F4.x lee `user.sucursal` para scoped queries |
| **HU-F11.x** (sync UI) | useAuth (no directo) | F11.x muestra `user.email` en topbar |
| **PR7 backend** (refresh rotation) | authStore + refresh logic (no F3.1) | Detección de reuse jti claim (F2.2 DEC-FETCH-03 cubre sin rotation; rotación es PR7+) |
| **HU-F5.x+** (impresión térmica) | `useAuth().permisos` filter | F5.x verifica permiso `facturacion.emitir` antes de imprimir |

---

## 15. Out of scope

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
- **OS-level kiosk** — Windows Assigned Access / macOS kiosk mode (FUERA Fase 3).
- **PIN rotation UI** — kiosko PIN pre-shared by F2.3, no rotation UI.

---

## 16. Open questions

**0 KNOWN-MISSING** (pre-flight 10/10 PASS + 0 KNOWN-MISSING en exploration §13). Items a verificar en `sdd-verify`:

1. **tsc clean post-T3** — verificar que `apps/electron-sucursal/tsconfig.*` compila sin errores después de agregar `<Route path="/login">` + `useLoginFlow` + imports nuevos.
2. **axe-core 0 violaciones on LoginForm** — REQ-OPS-112 gate. Verificar que el axe-core scan no reporta violaciones de WCAG 2.1 AA (color contrast, aria-invalid, label htmlFor, tab order).
3. **MSW 2.x setup in loginApi.test.ts** — F3.1 introduce MSW (Mock Service Worker) por primera vez en el repo (F2.2+F2.3 usaron mocks inline). Verificar que el setup MSW no rompe los tests existentes y que el handler MSW captura `POST /api/v1/auth/login` con los headers correctos (`credentials:'include'`, `Content-Type: application/json`).
4. **`useAuthStore.setTokens` atomicy en concurrent renders** — Zustand setState es síncrono pero el SWR key change puede disparar re-renders concurrentes. Verificar que `useAuth().data.user` está definido antes del `useEffect` redirect (sin flash).
5. **`parkosFetch` credentials include default** — DEC-F3.1-03 menciona agregar `credentials: 'include'` default a `parkosFetch`. Verificar que el cambio no rompe e2e existentes (F2.2 `auth/parkos-fetch.spec.ts`).

---

## 17. Appendix: traceability matrix

### 17.1 DEC-F3.1-NN ↔ exploration section ↔ REQ-OPS-NNN

| DEC | Exploration § | REQ-OPS (esta propuesta) | Plan.md anchor |
|---|---|---|---|
| DEC-F3.1-01 (feature folder) | §6.1 | REQ-OPS-112 (WCAG, derivado) | plan.md:1289 |
| DEC-F3.1-02 (Container/Presentational) | §6.2 | REQ-OPS-106 (form RHF+Zod) | plan.md:1289 |
| DEC-F3.1-03 (credentials:'include') | §6.3 | REQ-OPS-107 (POST credentials) | plan.md:1279 |
| DEC-F3.1-04 (HTTP directo NO IPC) | §6.4 | REQ-OPS-107 | plan.md:1279 |
| DEC-F3.1-05 (fetch raw NO parkosFetch) | §6.5 | REQ-OPS-107 | plan.md:1279 |
| DEC-F3.1-06 (Zod local NO parkosFetch schema) | §6.6 | REQ-OPS-106 | plan.md:1291 |
| DEC-F3.1-07 (redirect con data.user) | §6.7 | REQ-OPS-110 (setTokens) + REQ-OPS-111 (redirect) | plan.md:1280 |
| DEC-F3.1-08 (Anti-enumeración) | §6.8 | REQ-OPS-108 (401 invalidCredentials) + REQ-OPS-109 (429 lockout) | plan.md:1281 |
| DEC-F3.1-09 (parkos:auth:cleared) | §6.9 | (forward hook, no REQ) | plan.md:1302 |
| DEC-F3.1-10 (e2e 3 scenarios) | §6.10 | (e2e green gate, no REQ directa) | plan.md:1295 |
| **DEC-F3.1-11 (Spec delta con REQ-OPS-106..112)** | **NUEVA, esta propuesta §5.11** | REQ-OPS-106, REQ-OPS-107, REQ-OPS-108, REQ-OPS-109, REQ-OPS-110, REQ-OPS-111, REQ-OPS-112 | (DEC-F3.1-11 — re-evaluación crítica) |

### 17.2 REQ-OPS-NNN candidate ↔ DEC-F3.1-NN

| REQ-OPS-NNN | Comportamiento observable | Anchor DEC | Gate |
|---|---|---|---|
| REQ-OPS-106 | Login form con RHF + Zod (`email` formato válido + `password` min 8) con validation messages inline | DEC-F3.1-02, DEC-F3.1-06 | G1 |
| REQ-OPS-107 | POST /auth/login con `credentials:'include'` + Content-Type JSON (cookie httpOnly round-trip mandatory) | DEC-F3.1-03, DEC-F3.1-04, DEC-F3.1-05 | G3 |
| REQ-OPS-108 | 401 → mensaje único `errors.invalidCredentials` (anti-enumeración) | DEC-F3.1-08 | G2 |
| REQ-OPS-109 | 429 → `errors.lockout` con `Retry-After: <segundos>` (forward hook F3.2 countdown) | DEC-F3.1-08 | G5 |
| REQ-OPS-110 | `authStore.setTokens(access, refresh, expires_in)` hidrata desde 200 OK | DEC-F3.1-07 | G4 |
| REQ-OPS-111 | Redirect a `/` cuando `useAuth().isAuthenticated && data?.user && !isLoading` (transaccional) | DEC-F3.1-07 | G4 |
| REQ-OPS-112 | WCAG 2.1 AA compliance: axe-core 0 violaciones en `<LoginForm>` (RNF-022) | DEC-F3.1-01 | G7 (implícito) |

### 17.3 Precedentes cruzados

| Precedent | Archivado | Decisión clave | F3.1 sigue / diverge |
|---|---|---|---|
| F2.1 scaffold | 2026-09-15 | DEC-ELEC-10 NO-OP stub (infra-only) | DIVERGE: F3.1 user-facing, NO-OP NO aplica |
| F2.2 parkos-fetch | 2026-09-15 | DEC-FETCH-10 NO-OP stub (HTTP infra) | DIVERGE: F3.1 user-facing, NO-OP NO aplica |
| F2.3 auto-update-kiosko | 2026-09-15 | DEC-UPD-13 NO-OP stub (runtime infra) | DIVERGE: F3.1 user-facing, NO-OP NO aplica |
| **F1.15 login-historico** | **2026-09-15** | **4 new REQ-OPS-102..105 user-facing (login SELECT-only)** | **SIGUE: F3.1 replica patrón con 7 new REQ-OPS-106..112** |

### 17.4 Spec canónico state

- **Último REQ-OPS vigente**: REQ-OPS-105 (F1.15 archivado 2026-09-15).
- **Próximo número disponible**: REQ-OPS-106.
- **F3.1 ocupa**: REQ-OPS-106..112 (7 new requirements).
- **post-F3.1 archive**: REQ-OPS vigente = REQ-OPS-001..112 (112 total).

---

## 18. Referencias

### 18.1 Source of truth

- `plan.md` lines 1274-1305 — HU-F3.1 verbatim con 4 tareas atómicas T1..T4 (T1 Login + LoginForm lines 1289, T2 postLogin line 1292, T3 redirect line 1293, T4 e2e line 1295). Hard constraints: email format + password min 8 (line 1291), anti-enumeration 401 (line 1281), 429 lockout forward (line 1283), cookie httpOnly (line 1279), WCAG compliance (line 1295 — via RNF-022).
- `openspec/changes/hu-f3-1-login-email-password/exploration.md` — 17 secciones, ~755 LOC, 10 DEC-F3.1-01..10 ratified (sección 6), 8 riesgos R1..R8 (sección 7), 4 atomic tasks T1..T4 con budgets (sección 10), 1 cluster C1 (sección 11), 6 acceptance gates G1..G6 (sección 12), pre-flight 10/10 PASS + 0 KNOWN-MISSING (sección 13), out of scope (sección 14), forward hooks (sección 15).

### 18.2 Precedentes archivados

- `openspec/changes/archive/2026-09-15-hu-f2-3-electron-auto-update-kiosko/proposal.md` — 16 secciones, ~795 LOC, layout clonado 1:1 por esta propuesta. DEC-UPD-13 precedent (NO-OP stub infra-only).
- `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/proposal.md` — 16 secciones, ~770 LOC. DEC-FETCH-10 precedent (NO-OP stub HTTP infra).
- `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/proposal.md` — 16 secciones, ~770 LOC. DEC-ELEC-10 precedent (NO-OP stub scaffold).
- `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/proposal.md` — 16 secciones, ~770 LOC. **4 new REQ-OPS-102..105 user-facing precedent** (replica de F3.1 DEC-F3.1-11).
- `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/design.md` — design phase, detail de las 4 new REQ-OPS-102..105 en formato Given/When/Then/And RFC 2119.
- `openspec/changes/archive/bootstrap-monorepo-foundation/proposal.md:9` — workspaces precedent verbatim.

### 18.3 Apps anchors

- `apps/electron-sucursal/electron/main.ts:1-122` — F2.1 minimal app shell + F2.3 single-instance + log-config + updater + api-status + kiosko. F3.1 NO lo modifica.
- `apps/electron-sucursal/electron/preload.ts:1-49` — F2.2 whitelist IPC 8 métodos. F3.1 NO lo modifica.
- `apps/electron-sucursal/electron/bridge.d.ts:1-92` — F2.2 typed BridgeSurface + F2.3 ApiStatus delta. F3.1 NO lo modifica.
- `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` — F2.2 contract test. F3.1 NO lo modifica.
- `apps/electron-sucursal/package.json:22-53` — F2.1+F2.2+F2.3 deps (RHF + Zod + resolvers + Label + Router + i18n + SWR + zustand + bcryptjs + axe). F3.1 NO agrega deps (todo ya está).
- `apps/electron-sucursal/tsconfig.{json,main.json,renderer.json}` — F2.1 strict + noUncheckedIndexedAccess. F3.1 NO lo modifica.
- `apps/electron-sucursal/vite.config.ts` — F2.1 renderer Vite alias `@`. F3.1 NO lo modifica.
- `apps/electron-sucursal/src/renderer/App.tsx:1-37` — F2.1 router placeholder + F2.3 StatusBar mount. F3.1 agrega `<Route path="/login">`.
- `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` — F2.1 10 keys (loginTitle, email, password, submit, invalidCredentials, lockout, etc.). F3.1 agrega 5 validation keys.
- `apps/electron-sucursal/src/renderer/components/ui/{form,input,button}.tsx` — F2.1 shadcn primitives. F3.1 los reusa (no modifica).
- `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` — F2.3 aria-live polite. F3.1 NO lo modifica.
- `apps/ui-kit/src/fetch/parkosFetch.ts:1-212` — F2.2 primitive. F3.1 DEC-F3.1-05 usa raw fetch (NO consume parkosFetch para login).
- `apps/ui-kit/src/store/authStore.ts:1-129` — F2.2 primitive. F3.1 consume `useAuthStore.setTokens`.
- `apps/ui-kit/src/hooks/useAuth.ts:1-87` — F2.2 primitive. F3.1 consume `useAuth()` para hidratación + redirect.
- `apps/ui-kit/src/index.ts` — F2.1 exporta Button + cn + tokens. F3.1 NO modifica.

### 18.4 Backend anchors (HU-F1.2 shipped, NO F3.1 touch)

- `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-307` — `POST /auth/login` con cookie `parkos_session` + 401 anti-enumeration + 429 lockout.
- `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:419-583` — `GET /auth/me` con `AuthMeResponse`.
- `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` — `LoginRequest{email, password min_length:8}`, `TokenPair`, `AuthMeResponse`.
- `modelo_datos_er.mmd:270-289` — `configuracion_seguridad` (max_intentos_login, minutos_bloqueo_login).
- `modelo_datos_er.mmd:558-573` — `prod.login` (L-S lookup).

### 18.5 Documentación

- `docs/01-requisitos/no-funcionales.md:126` — RNF-022 WCAG 2.1 AA gate (axe-core tags).
- `docs/03-desarrollo/setup.md:15` — npm + npm-run-all pattern.
- `docs/03-desarrollo/estandares.md:79-91` — flat ESLint 9 config + convenciones.
- `docs/02-arquitectura/decisiones-tecnicas.md` — agregar DEC-F3.1-01..11 (resumen) post-archive. Referenciar este proposal.md para detalle.

### 18.6 Specs y roadmap

- `openspec/specs/operations/spec.md:1-4446` — canonical 112 REQ-OPS-001..105 vigentes. F3.1 AGREGA REQ-OPS-106..112 (7 new).
- `openspec/specs/operations/spec.md:3951` — REQ-OPS-XR6 canonical 5-layer defense (REFERENCE, F3.1 NO crea new XR).
- `openspec/specs/operations/spec.md:4386` — F1.15 DEC-XR7 NOT-CREATED precedent (también user-facing que NO creó new XR).
- `openspec/_meta/roadmap.md:38-273` — IT-1..IT-10 web_sucursal consumer map.
- `openspec/CHANGELOG.md` — Entrada: "2026-09-15 — HU-F3.1 login email+password archived (7 new REQ-OPS-106..112 user-facing)".

### 18.7 Convenciones

- Conventional commits (sin Co-authored-by, sin AI trailers por convención global).
- Author: `Parkos Dev <dev@parkos.local>` (verbatim F2.1 precedent).
- TDD estricto: tests rojos primero, luego código que los hace verde.
- Defense in depth 5 capas (XR6 pattern + engineering variant).
- RFC 2119 MUST/SHOULD/MAY key words en DEC-F3.1-NN + REQ-OPS-106..112.
- BDD Given/When/Then/And format en acceptance gates.

---

**End of proposal.**