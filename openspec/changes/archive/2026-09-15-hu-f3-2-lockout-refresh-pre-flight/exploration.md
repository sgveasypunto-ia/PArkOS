# Exploración — HU-F3.2 Lockout visible + refresh transparente

> **Phase**: explore (sdd-explore) · **Status**: ready for sdd-propose
> **HU ID**: HU-F3.2 (Fase 3 — segunda HU; Autenticación y turno de caja, hardening UX + lifecycle del access_token)
> **Working dir**: E:/easypunto_parkos · **Branch**: feat/fase-2-electron-scaffold (HEAD bcfe2ed, F3.1 archivado 2026-09-15)
> **Inputs**: plan.md lines 1307-1324 (HU-F3.2 verbatim, 130 LOC, 4 tareas atómicas T1..T4); plan.md:418 (DEC-SUC-03 — refresh 50min + pre-flight anchor); plan.md lines 1274-1305 (HU-F3.1 archivado — precedents + AccountLockedError + LoginErrorState); pending.md §1 (F3.1 ✅ cerrado 2026-09-15, F3.2 row 2 con budget 130 LOC); pending.md §5 (forward hooks F4/F5/F11/F3.3); openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/{exploration.md,proposal.md,specs/operations/spec.md,tasks.md,verify-report.md,archive-report.md} (precedent verbatim 17 secciones + 7 REQ-OPS-106..112); openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/{exploration.md,proposal.md,tasks.md} (precedent refresh-once Mutex DEC-FETCH-03 + refreshInterval baseline); apps/electron-sucursal/src/features/auth/{api/loginApi.ts:1-93 (AccountLockedError.retryAfterSeconds + parseRetryAfter), api/loginSchema.ts, api/loginApi.test.ts:1-138, components/LoginForm.tsx:1-133 (LoginErrorState kind:'lockout'), pages/Login.tsx:1-81 (container con errorState wiring), pages/Login.test.tsx, components/LoginForm.test.tsx}; apps/ui-kit/src/{fetch/parkosFetch.ts:1-212 (refresh-once 401 via handle401 + Mutex singleton), store/authStore.ts:1-129 (setTokens + clear + refreshAccessToken Mutex), hooks/useAuth.ts:1-87 (SWR refreshInterval 5*60*1000 — F3.2 CAMBIO a 50min), hooks/useAuth.test.ts}; apps/electron-sucursal/src/renderer/{App.tsx:1-41 (/login route wired), i18n/locales/{auth,common,errors,operacion,caja,facturacion,sync}.json}; apps/electron-sucursal/e2e/{auth/login.spec.ts:1-105 (4 tests: E1 cookie, E2 refresh, E3 logout, A1 axe-core), a11y/wcag-2.1-aa.spec.ts (axe-core pattern precedent), auth/parkos-fetch.spec.ts (MSW pattern precedent), scaffold.spec.ts}; backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:21,71-72,279,285,297,306,343,348 (ACCESS_TOKEN_TTL=3600, REFRESH_TOKEN_TTL=7d, Retry-After header); backend/packages/parkos_core/src/parkos_core/schemas/auth.py (LoginRequest + TokenPair); modelo_datos_er.mmd:270-289 (configuracion_seguridad.max_intentos_login + minutos_bloqueo_login); modelo_datos_er.mmd:558-573 (prod.login [L-S]); docs/01-requisitos/no-funcionales.md:126 (RNF-022 WCAG 2.1 AA.

---

## 0. Metadata

- **HU**: HU-F3.2 — Lockout visible (countdown) + refresh transparente (50min auto + pre-flight).
- **Fase**: 3 (Autenticación y turno de caja — segunda HU, transversal a F3.3+/F4.x/F5.x/F11.x).
- **Cycle status**: ready for sdd-propose (pre-flight 10/10 PASS, 0 KNOWN-MISSING).
- **Branch**: `feat/fase-2-electron-scaffold` (HEAD `bcfe2ed`, F3.1 archivado 2026-09-15; F3.2 se commitea sobre la misma rama hasta migrar a `feat/fase-3-auth-turno` per pending.md:6).
- **Date**: 2026-09-15.
- **Status**: exploration complete, ready for `sdd-propose` con `next_recommended: sdd-propose`.
- **Author**: Parkos Dev <dev@parkos.local> (precedente F2.1/F2.2/F2.3/F3.1 verbatim).
- **DEC-F3.2-08 verdict**: **DELTA** (NOT NO-OP) — F3.2 ES user-facing behavior observable: countdown visual (`secondsLeft` decreciente cada 1000ms) + form disabled durante lockout + pre-flight gate que evita 401 mid-write en `/facturacion/*` y `/caja/arqueo` + refresh 50min automático. Per F1.15 + F3.1 precedent, user-facing ⇒ spec delta materialized.
- **Precedente directo**: F3.1 archivado 2026-09-15 con 7 REQ-OPS-106..112 (DELTA, first user-facing DELTA en Fase 3, breaking F2.x NO-OP pattern). F3.2 ocupa REQ-OPS-113..118 (numeración monotónica).

## 1. Contexto y motivación

**Title**: "Lockout visible con countdown decreciente (`useCountdown` hook + `setInterval(1000)` + cleanup) + refresh transparente 50min auto (cambio `useAuth.refreshInterval: 5*60*1000 → 50*60*1000`) + refresh pre-flight antes de POST `/facturacion/*` y POST `/caja/arqueo` (gate `await refreshIfExpiringSoon()` con Mutex singleton) + e2e lockout scenario (4-5 intentos fallidos → 429 → countdown display → auto re-enable al llegar a 0)."

**Goal**: F3.1 archivado deja el flujo login + cookie httpOnly + hidratación transaccional + WCAG 2.1 AA completos. Sin embargo, dos gaps UX críticos rompen la promesa "kiosko desatendido, operador desatendido, sesión robusta":

1. **429 sin countdown es hostil UX**: cuando `loginApi.postLogin` recibe 429 con `Retry-After: 600` (10min), F3.1 surfacea `<p role="alert">{t('lockout')}</p>` como texto estático "Cuenta bloqueada temporalmente." (LoginForm.tsx:120-124). El operador no sabe cuánto falta — el form queda habilitado y vuelve a fallar inmediatamente. Kiosko desatendido = operador frustrado que abandona el terminal. F3.2 entrega `useCountdown(retryAfterSeconds)` con `setInterval(1000)` que decrementa `secondsLeft` cada tick, `disabled` automático del form mientras `secondsLeft > 0`, y auto re-enable al llegar a 0. Display `<p role="status" aria-live="polite">{formatTime(secondsLeft)}</p>` para WCAG 2.1 AA (RNF-022).

2. **Refresh 5min (F2.2 baseline) es subóptimo vs access_token TTL 1h**: `useAuth.ts:60` setea `refreshInterval: 5 * 60 * 1000` per plan.md:1208 (F2.2 verbatim). Pero `ACCESS_TOKEN_TTL = 3600` en `backend/.../auth.py:71` significa que el access_token vive 1h. Refrescar cada 5min es 12x por hora = desperdicio de bandwidth + latencia SWR innecesaria. F3.2 cambia el interval a **50min** (`50 * 60 * 1000 = 3_000_000`) per `DEC-SUC-03` (plan.md:418 verbatim: "Refresh transparente cada 50 minutos y antes de escrituras críticas (pago, arqueo)"). 50min deja un safety margin de 10min antes del TTL — si un refresh falla, el operador tiene 10min para retry antes de expirar.

3. **Pre-flight gate faltante causa 401 mid-write**: `parkosFetch.ts:119-140` (`handle401`) ya implementa refresh-once via Mutex cuando el backend responde 401. PERO: si el operador está en `/facturacion` y submita un POST crítico, el access_token expira JUSTO en el medio del request → 401 → refresh → retry. Esto causa una race donde el backend recibe el POST original (¿se procesa dos veces?), el operador ve un error confuso, y el state local queda inconsistente. F3.2 agrega un **pre-flight gate** en `parkosFetch.ts` que, ANTES de `POST /facturacion/*` + `POST /caja/arqueo`, verifica `useAuthStore.expiresAt` — si faltan <5min para expirar, dispara `refreshAccessToken()` proactively via Mutex. El request crítico viaja con token fresco.

**Por qué importa** (rationale): F3.2 cierra los gaps de lifecycle del access_token que F3.1 dejó abiertos. Tres factores elevan su criticidad:

1. **Kiosko desatendido + operador en piso**: plan.md:418 (DEC-SUC-03) exige kiosko robusto, sin intervención IT. Si el operador se锁ea y NO ve countdown, no sabe si esperar o pedir ayuda. Si el refresh no es transparente, pierde el turno. Si un POST crítico falla por 401 mid-write, pierde la venta. F3.2 mitiga los tres.

2. **Defense in depth XR6 (operations/spec.md:3951)**: el patrón de 5 capas (auth + engineering + a11y + contract + retry-budget) requiere retry-budget robusto. F2.2 sentó las bases (Mutex + refresh-once); F3.2 lo completa con pre-flight gate que evita el retry reactivo.

3. **Forward consumer para Fase 4+**: F4.x (catálogos) + F5.x (facturación) + F11.x (sync UI) consumen `parkosFetch` con POST mutacionales críticos. Sin pre-flight, todos heredan el riesgo de 401 mid-write. F3.2 blinda la infraestructura para que las HU downstream sean trabajo de UI, no de infra.

**Hard constraints** (mirrored from plan.md:1311 verbatim):

- Trigger 429 con `Retry-After` → form `disabled={true}` + countdown display `useCountdown(retryAfterSeconds)` `{secondsLeft, isExpired}`.
- Refresh automático cada 50min (`refreshInterval: 50 * 60 * 1000` en `useAuth()` SWR, configurable).
- Pre-flight refresh antes de `POST /facturacion/*` + `POST /caja/arqueo` si access_token expira en <5min.
- `useCountdown(retryAfter)` hook reusable (forward consumer F4.x/F5.x/F11.x).
- Tamaño: 130 LOC production + tests + configs.
- 4 tareas atómicas T1..T4.
- e2e: `e2e/lockout.spec.ts` — 4-5 intentos fallidos → 429 + countdown visible y decreciente.

**Inconsistencias detectadas** (a resolver en `sdd-propose`):

- **I1**: `plan.md:1309` dice "5 intentos fallidos" → 429 + countdown. `plan.md:1309` también dice "falla 5 veces" en la historia de usuario. Pero `pending.md:15` row F3.2 dice "Trigger: 429 con Retry-After → disable form + countdown setInterval(1000)". El user prompt provided por orchestrator menciona "4 attempts fallidos → 429 → countdown display". **Resolution propuesta**: leer `configuracion_seguridad.max_intentos_login` (default 5 per `auth.py:225`) — el e2e test usa 4 (rápido) o 5 (canonical), indistinto desde el frontend. **DEC-F3.2-09 (proposed)**: e2e usa `max_intentos_login` configurado por env (default 5), test hace `max_intentos - 1` intentos fallidos + 1 intento que recibe 429 → asserts countdown. Para garantizar verde en sandbox sin backend real, e2e mocketa el backend con MSW o `page.route` (F3.1 precedent).
- **I2**: `plan.md:1311` dice "pasan 50 minutos desde el último refresh". `useAuth.ts:60` tiene `refreshInterval: 5 * 60 * 1000 = 300_000`. **Resolution propuesta**: F3.2 T3 MODIFY `useAuth.ts:60` para cambiar a `50 * 60 * 1000 = 3_000_000`. Constante exportada `REFRESH_INTERVAL_MS = 50 * 60 * 1000` para testabilidad. DEC-F3.2-04.
- **I3**: `plan.md:1311` menciona "POST /caja/arqueo" pero `modelo_datos_er.mmd` no tiene tabla `caja.arqueo` (arqueos viven en Fase 10 per pending.md:51). **Resolution propuesta**: F3.2 pre-flight gate es genérico — matchea `/facturacion/*` + `/caja/arqueo*` (regex o path prefix). Si Fase 10 introduce `/caja-sesion/*` con arqueo, el gate se extiende via DEC-F3.2-10 (forward). Plan.md T3 dice "POST /caja/arqueo" — interpretado como placeholder para Fase 10.

## 2. Scope y out-of-scope

### 2.1 In scope (130 LOC production + tests + configs)

| Area | Detalle |
|---|---|
| **`useCountdown` hook (T1)** | New `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (~40 LOC production + ~50 LOC tests). Reusable. Signature: `useCountdown(retryAfterSeconds: number, options?: { onComplete?: () => void }): { secondsLeft: number; isExpired: boolean }`. Internals: `Date.now() + retryAfterSeconds * 1000` baseline (NUNCA accumulator — R1 mitigation), `setInterval(1000)` decrementa `secondsLeft`, cleanup en unmount via `useEffect` return, `onComplete` callback cuando llega a 0. |
| **LoginForm countdown integration (T2)** | Modify `LoginForm.tsx` para consumir `useCountdown(retryAfterSeconds)` cuando `error.kind === 'lockout'`. Form fields `disabled={error?.kind === 'lockout' && !isExpired}`. Countdown display `<p role="status" aria-live="polite" data-testid="login-countdown">{formatTime(secondsLeft)}</p>` debajo del mensaje `t('lockout')`. Botón submit `disabled` durante lockout. `formatTime` helper: `mm:ss` (e.g., "09:47"). |
| **Login.tsx wiring (T2)** | Modify `Login.tsx` para pasar `retryAfterSeconds` del `AccountLockedError` al state, y propagar al `LoginForm` como `error: { kind: 'lockout', retryAfterSeconds: err.retryAfterSeconds }`. Cuando `useCountdown.isExpired === true`, reset `errorState` a `null` para re-habilitar el form. |
| **`useAuth` 50min refresh (T3)** | Modify `useAuth.ts:60` para cambiar `refreshInterval: 5 * 60 * 1000` → `50 * 60 * 1000`. Agregar constante exportada `REFRESH_INTERVAL_MS = 50 * 60 * 1000` para testabilidad. Update `useAuth.ts:8-12` JSDoc para reflejar nuevo intervalo. |
| **parkosFetch pre-flight gate (T3)** | Modify `parkosFetch.ts` para agregar función `refreshIfExpiringSoon()` (exportada o módulo-internal). En `parkosFetchRaw` línea 154-165, ANTES del fetch, si `method === 'POST'` AND `url.match(/\/(facturacion\|caja\/arqueo)/)` AND `useAuthStore.expiresAt !== null` AND `Date.parse(useAuthStore.expiresAt) - Date.now() < 5 * 60 * 1000` → `await refreshAccessToken()` (Mutex shared con 401 path). Constante `PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000`. Lista de paths en constante `PRE_FLIGHT_PATHS = /\/facturacion(\/\|$)\|\/caja\/arqueo/`. |
| **i18n keys (T2)** | Modify `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` — agregar 2-3 keys: `lockoutCountdown` (template `${mm}:${ss}`), `lockoutReEnable` (auto re-enable notice), `lockoutLabel` (aria-label para el display). NO requiere nuevo namespace (F2.1 DEC-ELEC-06 — un namespace por bounded context). |
| **e2e lockout scenario (T4)** | New `apps/electron-sucursal/e2e/auth/lockout.spec.ts` (~50 LOC tests). 4 escenarios: (E1) 4 intentos fallidos → 429 → countdown visible `< 600s`; (E2) countdown decrementa cada ~1000ms; (E3) countdown llega a 0 → form re-habilitado; (A1) axe-core 0 violaciones en `/login` durante lockout state. |
| **Unit tests** | New `apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts` (~50 LOC, 4 tests: U1 baseline Date.now + setInterval, U2 cleanup on unmount, U3 onComplete callback fires, U4 drift resistance via Date.now()). Modify `useAuth.test.ts` para verificar `REFRESH_INTERVAL_MS = 50 * 60 * 1000`. Modify `parkosFetch.test.ts` para agregar 2-3 tests pre-flight (U5 expiring soon triggers refresh, U6 not expiring skips refresh, U7 GET no triggerea refresh). Modify `Login.test.tsx` + `LoginForm.test.tsx` para verificar countdown wiring (3 tests adicionales: U8 lockout disables form, U9 countdown decrements, U10 isExpired resets errorState). |

### 2.2 Out of scope (explícitamente deferido)

- **Backend cambios**: `configuracion_seguridad.max_intentos_login` ya shipped (Fase 1 — HU-F1.2); F3.2 NO modifica backend.
- **Refresh-token rotation**: `refreshAccessToken()` reusa el mismo refresh_token (F1.15 + F2.2 Mutex — DEC-FETCH-03). Rotación con `jti` reuse detection es PR7 backend (forward).
- **AuthGuard component**: `parkos:auth:cleared` event listener → `navigate('/login?next=...')` es F3.3+ (forward hook).
- **Logout button UI**: F3.3+ placeholder o HU posterior.
- **Recuperación de password / 2FA / WebAuthn**: fuera Fase 3 (futuro).
- **Multi-tab login UI**: kiosko single-tab per F2.3 `requestSingleInstanceLock` (DEC-UPD-07).
- **Turno abrir/cerrar**: F3.3 (`features/caja/pages/{AbrirTurno,CerrarTurno}.tsx`).
- **Countdown styling library**: countdown usa `formatTime` helper inline (`mm:ss`), NO librería externa (mantener bundle size small — kiosko desatendido, RAM limitada).
- **Toast notifications**: out of scope Fase 3 (forward a F11.x sync UI).
- **OS-level kiosk PIN rotation**: F2.3 kiosko mode baseline, no F3.2 touch.
- **Sucursal selector UI**: JWT ya pinea sucursal (single-branch kiosko).
- **`rememberMe` / `forgotPassword` keys**: pre-existentes en `auth.json:10-11` pero F3.2 NO las usa.
- **REFRESH_INTERVAL_MS configurable via UI**: hardcoded a 50min per DEC-SUC-03; configurabilidad futura si negocio requiere.
- **Pre-flight para otros endpoints**: T3 cubre solo `/facturacion/*` + `/caja/arqueo*` per plan.md:1311 + DEC-SUC-03. Otros POST críticos futuros se agregan via DEC-F3.2-10.
- **Countdown para retry buttons**: useCountdown se reusa en F4.x/F11.x per forward hooks §14, pero F3.2 solo lo integra en Login.
- **i18n plurals**: countdown siempre mm:ss (max 99:59 = 2h, suficiente para `minutos_bloqueo_login` default 10min × max `minutos_bloqueo_login` configurable hasta 60min per auth.py).

## 3. Pre-flight (10-point checklist F2.3 verbatim)

Ejecutado en orden F2.3 verbatim. Resultado: 10/10 PASS.

| # | Check | Source | Result |
|---|---|---|---|
| 1 | **Branch clean post-F3.1 archive** | `git status --short` retorna solo housekeeping commits `bcfe2ed` (Fase 3 1/3 cerrado) + `57a7a43` (archive) + `5fcfe66/70d9aa1/8b84b3e` (F3.1 atomic) ya landed en `feat/fase-2-electron-scaffold` per `git log --oneline -5` | **PASS** |
| 2 | **Working tree clean post-archive** | No untracked F3.1 files; F3.1 deliverables commited; `pending.md §1 row 1` marca F3.1 ✅ cerrado | **PASS** |
| 3 | **HU-F3.1 ✅ archived** | `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` existe con 7 archivos: `exploration.md` (758 LOC) + `proposal.md` + `specs/operations/spec.md` (7 REQ-OPS-106..112) + `design.md` + `tasks.md` + `verify-report.md` + `archive-report.md` | **PASS** |
| 4 | **Backend endpoints operational** | `POST /api/v1/auth/login` (auth.py:148-307, 429 + Retry-After:219-228) + `POST /api/v1/auth/refresh` (auth.py:310-349, rotates tokens) + `POST /api/v1/auth/logout` (auth.py:352-393) + `GET /api/v1/auth/me` (auth.py:419-583) — todos shipped HU-F1.2 + HU-F1.15 en Fase 1 + Fase 2 | **PASS** |
| 5 | **Frontend primitives available** | (a) `AccountLockedError` + `parseRetryAfter` shipped `apps/electron-sucursal/src/features/auth/api/loginApi.ts:47-63`; (b) `LoginErrorState kind:'lockout'` con `retryAfterSeconds` shipped `LoginForm.tsx:42-46`; (c) `useAuthStore` Zustand + Mutex `refreshAccessToken` shipped `apps/ui-kit/src/store/authStore.ts:71-128`; (d) `useAuth()` SWR shipped `apps/ui-kit/src/hooks/useAuth.ts:53-86`; (e) `parkosFetch` Mutex refresh-once 401 shipped `apps/ui-kit/src/fetch/parkosFetch.ts:119-140` | **PASS** |
| 6 | **i18n locale loaded** | `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` existe con 10 keys pre-F3.1 + 5 validation keys post-F3.1 (`validation.required`, `validation.email.invalid`, `validation.password.minLength`, `validation.password.required`) + `loginTitle/logout/email/password/submit/sessionExpired/lockout/invalidCredentials/rememberMe/forgotPassword`. Plan F3.2 agrega 2-3 keys de countdown (`lockoutCountdown`, `lockoutReEnable`, `lockoutLabel`) — verbatim i18n pattern F2.1 DEC-ELEC-06 | **PASS** |
| 7 | **shadcn Form components available** | `apps/electron-sucursal/src/renderer/components/ui/{form,input,button}.tsx` shipped F2.1 baseline + F3.1 wired. F3.2 reusa sin tocar — solo cambia `disabled` prop dinámicamente según lockout state | **PASS** |
| 8 | **e2e harness available** | (a) `apps/electron-sucursal/playwright.config.ts` shipped F2.1; (b) `apps/electron-sucursal/e2e/auth/login.spec.ts:1-105` shipped F3.1 (4 tests: E1 cookie, E2 refresh, E3 logout, A1 axe-core); (c) `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` shipped F2.1 axe-core pattern precedent; (d) `apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts` MSW pattern precedent | **PASS** |
| 9 | **DEC-SUC-02 honored** | Credencial es `email`, NUNCA `cedula` — verificado en `backend/.../schemas/auth.py::LoginRequest{email: EmailStr, password: ...}`. F3.2 NO introduce `cedula` en ningún flujo. Cuenta regresiva + refresh operan sobre `useAuthStore.expiresAt` derivado del JWT, agnóstico a credencial | **PASS** |
| 10 | **0 KNOWN-MISSING** | Sin gaps blocker. F3.2 es DELTA precedent F3.1 — todas las primitives necesarias ya shipped en F2.2 + F3.1. Las 2 inconsistencies (I1 max_intentos 4 vs 5; I2 refreshInterval 5min → 50min) son cambios de constants/params, no gaps | **PASS** |

**Sandbox F.6 caveat**: e2e tests (T4) van a SKIPPED-env en `npm 11.16.0` (F2.2 G8 + F3.1 sandbox precedent). Unit tests (T1 useCountdown + T2 Login wiring + T3 useAuth refreshInterval + T3 parkosFetch pre-flight) SÍ corren via `vitest run`. Documentado como deviation D-env en `verify-report.md` futuro (no project defect).

## 4. Stakeholders y consumers

| Stakeholder | Rol | Mecanismo F3.2 |
|---|---|---|
| **Operador (sucursal)** | End-user del Login + consumidor de countdown UX | Login form se deshabilita durante 429 con countdown visible; auto re-enable al llegar a 0. |
| **Operador (sesión activa)** | End-user de features autenticadas (F4.x/F5.x) | Pre-flight gate evita 401 mid-write en POST críticos. SWR refresh 50min evita logout inesperado. |
| **useCountdown** (NEW, F3.2 T1) | Hook reusable | Exportado desde `features/auth/hooks/useCountdown.ts`, consumible por F4.x retry buttons + F11.x reintentos. |
| **LoginForm** (F3.1, MODIFY F3.2 T2) | Presentacional | Consume `useCountdown` cuando `error.kind === 'lockout'`; renderiza `<p role="status" aria-live="polite">` con countdown + `disabled` en inputs/submit. |
| **Login** (F3.1, MODIFY F3.2 T2) | Container | Wire `useCountdown` + reset `errorState` cuando `isExpired === true`. |
| **useAuth** (F2.2, MODIFY F3.2 T3) | SWR hook | `refreshInterval: 5*60*1000 → 50*60*1000`. Constante `REFRESH_INTERVAL_MS` exportada. |
| **parkosFetch** (F2.2, MODIFY F3.2 T3) | HTTP wrapper | Pre-flight gate `refreshIfExpiringSoon()` antes de POST `/facturacion/*` + `/caja/arqueo*`. Constante `PRE_FLIGHT_THRESHOLD_MS = 5*60*1000`. |
| **refreshAccessToken** (F2.2, CONSUME F3.2 T3) | Mutex singleton | Reusado por pre-flight gate (mismo Mutex que 401 refresh — F2.2 DEC-FETCH-03 invariant preserved). |
| **useAuthStore.expiresAt** (F2.2, CONSUME F3.2 T3) | Estado persistido | Pre-flight check lee `Date.parse(expiresAt) - Date.now()` para calcular proximity. |
| **auth.json** (F3.1, MODIFY F3.2 T2) | i18n namespace | +3 keys (`lockoutCountdown`, `lockoutReEnable`, `lockoutLabel`). |
| **e2e lockout spec** (NEW, F3.2 T4) | Test consumer | 4 escenarios + axe-core A1. |
| **vitest + @testing-library/react** (F2.1 baseline) | Test runner | T1+T2+T3 unit tests verde; sandbox SKIPPED-env e2e. |
| **axe-core + playwright** (F2.1 baseline) | a11y runner | A1 verifica WCAG 2.1 AA durante lockout state. |
| **backend auth.py** (Fase 1, READ ONLY) | API source | `Retry-After: <segundos>` header (line 219-228) consumido por `parseRetryAfter`. Cero cambios backend. |

## 5. Constraints duras

- **access_token TTL 50min (refresh)**: `refreshInterval: 50 * 60 * 1000` (3_000_000ms) en `useAuth.ts`. NO hardcodear — constante `REFRESH_INTERVAL_MS` exportada. Safety margin = `ACCESS_TOKEN_TTL (3600) - REFRESH_INTERVAL_MS (3000) = 600s = 10min` — si un refresh falla, operador tiene 10min antes de 401 forzado.
- **countdown UX ≤1s resolution**: `setInterval(1000)` exacto. `useCountdown` baseline `Date.now() + retryAfterSeconds * 1000` (NO accumulator — R1 mitigation). En tests, `vi.useFakeTimers()` + `vi.advanceTimersByTime(1000)` per tick.
- **pre-flight latency budget ≤200ms**: `refreshIfExpiringSoon` se invoca una vez por POST. Refresh HTTP toma ~50-150ms (F2.2 benchmark) → total budget ~200ms para no degradar UX del POST crítico. Si refresh falla, el request continúa con token existente (graceful degradation — el 401 retry-once del handle401 cubre).
- **Mutex singleton preserved**: pre-flight gate REUSA `refreshAccessToken()` Mutex (F2.2 DEC-FETCH-03 invariant). N concurrentes pre-flight + 401 callers comparten UNA promesa. Cero riesgo de doble refresh.
- **`useAuthStore.expiresAt` parseable**: derivado en `setTokens` (authStore.ts:78) como `new Date(Date.now() + expiresIn * 1000).toISOString()` (ISO 8601 UTC). Pre-flight consume via `Date.parse(expiresAt)`.
- **WCAG 2.1 AA countdown accessibility**: countdown display usa `<p role="status" aria-live="polite">` (NO `aria-live="assertive"` — interruptivo). `aria-label={t('lockoutLabel')}` describe el countdown para screen readers.
- **e2e sandbox F.6**: `_electron.launch` SKIPPED-env en `npm 11.16.0`. F3.2 e2e documentado como deviation D-env (F2.1 + F2.2 + F2.3 + F3.1 precedent).
- **i18n locale completeness**: 3 keys countdown (`lockoutCountdown`, `lockoutReEnable`, `lockoutLabel`) en `auth.json` — pre-existe namespace, NO requiere nuevo namespace.
- **Path matching regex performance**: `PRE_FLIGHT_PATHS` regex compilada una vez en módulo-level (NO recompilada per request). `/\/facturacion(\/\|$)\|\/caja\/arqueo/` (~30 chars compiled).
- **Refresh interval NO configurable via UI**: hardcoded 50min per DEC-SUC-03 (plan.md:418). Configurabilidad via env (`PARKOS_REFRESH_INTERVAL_MS`) es forward hook F3.x si negocio lo requiere.
- **Pre-flight gate NO se triggerea en POST `/auth/login`**: `/auth/login` es anónimo (DEC-F3.1-05). Si por error matchea `/facturacion`, NO hay daño porque `expiresAt` es null pre-login → pre-flight skip.
- **Pre-flight gate SOLO en POST mutacionales**: GET requests no triggerean refresh pre-flight (lecturas idempotentes, 401 es aceptable — handle401 retry cubre).
- **countdown drift resistance**: si tab inactive + system sleep, `setInterval` puede pausar. Mitigation: `Date.now()` baseline + recalc en cada tick (R1 risk + DEC-F3.2-01).

## 6. Dependencies y precondiciones

### 6.1 Shipped (F2.2 + F3.1 — prerequisites)

- **HU-F1.2** ✅ closed Fase 1: `POST /auth/login` + `GET /auth/me` + cookie httpOnly + 401/429 mapping backend (`backend/.../auth.py:148-583`).
- **HU-F1.15** ✅ closed Fase 1: login histórico (`prod.login` [L-S]) + 4 new REQ-OPS-102..105 user-facing (F1.15 precedent for DELTA stub).
- **HU-F2.1** ✅ closed Fase 2: Electron 30 skeleton + shadcn Form/Input/Button + i18n 7 namespaces + axe-core + playwright e2e.
- **HU-F2.2** ✅ closed Fase 2: parkosFetch (retry + refresh-once 401 via Mutex + Idempotency-Key) + bridge IPC + authStore Zustand + useAuth SWR.
- **HU-F2.3** ✅ closed Fase 2: kiosko mode + electron-updater + StatusBar + single-instance lock.
- **HU-F3.1** ✅ closed 2026-09-15: Login page + LoginForm + loginApi + loginSchema + ruta `/login` + 7 REQ-OPS-106..112 + `AccountLockedError(retryAfterSeconds)` + `LoginErrorState kind:'lockout'`.

### 6.2 Precondiciones verificadas (pre-flight §3)

| # | Precondición | Status |
|---|---|---|
| P1 | `loginApi.ts` emite `AccountLockedError(retryAfterSeconds)` en 429 | ✅ shipped F3.1 (line 47-52) |
| P2 | `LoginForm.tsx` tiene `LoginErrorState kind:'lockout'` con `retryAfterSeconds` display | ✅ shipped F3.1 (line 42-46, 120-124) |
| P3 | `Login.tsx` wirea `errorState` con `AccountLockedError` mapping | ✅ shipped F3.1 (line 62-69) |
| P4 | `useAuth.ts` SWR con `refreshInterval` configurable | ✅ shipped F2.2 (line 60, valor actual 5min — F3.2 cambia a 50min) |
| P5 | `parkosFetch.ts` tiene `handle401` con Mutex refresh-once | ✅ shipped F2.2 (line 119-140, DEC-FETCH-03) |
| P6 | `useAuthStore.expiresAt` derivable ISO 8601 | ✅ shipped F2.2 (authStore.ts:78) |
| P7 | `refreshAccessToken()` Mutex singleton | ✅ shipped F2.2 (authStore.ts:100-128) |
| P8 | `auth.json` namespace registrado en `i18n/index.ts` | ✅ shipped F2.1 (no F3.2 touch i18n index) |
| P9 | axe-core + playwright instalado en `apps/electron-sucursal/package.json` | ✅ shipped F2.1 (line 55-56) |
| P10 | vitest + @testing-library/react instalado | ✅ shipped F2.1 (`@testing-library/react@^16.0.1`) |

### 6.3 NO requiere (out of dependencies)

- **Backend cambios**: F3.2 NO modifica backend. `configuracion_seguridad.max_intentos_login` ya shipped Fase 1; `Retry-After` header ya implementado auth.py:219-228.
- **Nuevas dependencies npm**: F3.2 NO requiere `npm install`. `react@^18.3.1` + `setInterval` (vanilla JS) + `Date.now()` (vanilla JS) + `useEffect` (React) ya shipped.
- **Nuevos namespaces i18n**: `auth.json` suficiente. `lockoutCountdown` + `lockoutReEnable` + `lockoutLabel` se agregan al namespace existente.
- **Nuevos componentes shadcn**: countdown usa HTML semántico (`<p>`, `<button disabled>`). NO requiere `Progress` o `Badge` components.
- **Cambios en IPC bridge**: F3.2 NO agrega métodos IPC. Refresh es HTTP puro, NO IPC.

### 6.4 Forward dependencies (F3.3+ consume F3.2 outputs)

- **HU-F3.3** (Abrir/Cerrar turno): consume `useAuth().user.sucursal` + pre-flight gate automático para `POST /caja-sesion/sesiones` (forward hook — si F3.3 decide agregar `/caja-sesion` a pre-flight paths, DEC-F3.2-10 extiende la regex).
- **HU-F4.x** (catálogos): consume `useCountdown` para retry buttons (`useRetryWithCountdown` pattern).
- **HU-F5.x** (facturación): hereda pre-flight gate automáticamente (T3 cubre `/facturacion/*`).
- **HU-F11.x** (sync UI): consume `useCountdown` para reintentos de sync con countdown visual.

## 7. Decisions needed (DEC-F3.2-NN to ratify en `sdd-propose`)

### DEC-F3.2-01 — `useCountdown` signature: `Date.now()` baseline (NO accumulator)

**DECISION**: `useCountdown(retryAfterSeconds: number, options?: { onComplete?: () => void }): { secondsLeft: number; isExpired: boolean }`. Internals: `endTime = Date.now() + retryAfterSeconds * 1000`. Tick handler recalcula `secondsLeft = Math.max(0, Math.ceil((endTime - Date.now()) / 1000))`. NO accumulator pattern (`secondsLeft--`).

**RATIONALE**: Accumulator drift. Si tab inactive + system sleep, `setInterval` puede pausar (browser throttle) → accumulator queda atrasado del wall clock. `Date.now()` baseline es drift-resistant (siempre recomputa desde wall clock). R1 risk mitigation.

### DEC-F3.2-02 — Countdown UX: form `disabled` (NOT readonly)

**DECISION**: Durante lockout, ambos `<Input>` + `<Button type="submit">` se renderizan con `disabled={true}`. El countdown display se renderiza ARRIBA del form (entre el `<p role="alert">{t('lockout')}</p>` y los inputs).

**RATIONALE**: `disabled` previene submit + previene typing. `readonly` permite typing pero no submit — UX confuso. WCAG 2.1 AA: `aria-disabled="true"` adicional para screen readers anuncia estado.

### DEC-F3.2-03 — Pre-flight trigger: conditional on path (regex match)

**DECISION**: Pre-flight gate `refreshIfExpiringSoon()` se invoca SOLO si `method === 'POST'` AND `url.match(PRE_FLIGHT_PATHS)`. Constante `PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/`. Compile regex módulo-level (NO recompilar per request).

**RATIONALE**: Pre-flight tiene latency cost (~50-150ms). Aplicarlo a TODOS los POST degrada UX innecesariamente. Solo endpoints críticos del DEC-SUC-03: pago (`/facturacion/*`) + arqueo (`/caja/arqueo`). Otros POST (catálogos read, sync, etc.) NO requieren pre-flight — 401 retry cubre.

### DEC-F3.2-04 — SWR refresh interval: 50min hardcoded (configurable via const export)

**DECISION**: `useAuth.ts:60` cambia `refreshInterval: 5 * 60 * 1000` → `refreshInterval: REFRESH_INTERVAL_MS = 50 * 60 * 1000`. Constante exportada para testabilidad.

**RATIONALE**: DEC-SUC-03 (plan.md:418) verbatim "Refresh transparente cada 50 minutos". 50min deja safety margin de 10min vs `ACCESS_TOKEN_TTL=3600` (auth.py:71). Configurabilidad via UI es forward hook (no F3.2 scope).

### DEC-F3.2-05 — e2e axe-core scope: countdown state WCAG check

**DECISION**: `e2e/auth/lockout.spec.ts` A1 test verifica axe-core 0 violaciones durante countdown state (form disabled + `<p role="status" aria-live="polite">` countdown). `withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])` mismo F3.1 pattern.

**RATIONALE**: REQ-OPS-112 (F3.1 spec) + RNF-022 WCAG 2.1 AA. Countdown display debe pasar axe-core scan — `role="status"` + `aria-live="polite"` son patrones axe-core compliant.

### DEC-F3.2-06 — Countdown i18n keys: 3 keys en `auth.json`

**DECISION**: `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` agrega 3 keys:
- `lockoutCountdown`: "Reintento disponible en {{time}}" (template i18next interpolation).
- `lockoutReEnable`: "El formulario se ha reactivado. Puedes intentar de nuevo." (auto re-enable notice).
- `lockoutLabel`: "Tiempo restante para reintentar: {{time}}" (aria-label descriptivo).

**RATIONALE**: F2.1 DEC-ELEC-06 — un namespace por bounded context. `auth` namespace ya tiene `lockout` key (line 8) — countdown keys son extensión natural. NO requiere nuevo namespace `auth.countdown`.

### DEC-F3.2-07 — Pre-flight latency budget: ≤200ms

**DECISION**: `refreshIfExpiringSoon` debe ejecutar en ≤200ms p95. Refresh HTTP baseline ~50-150ms (F2.2 benchmark post-Mutex + cookie round-trip). 50ms budget para regex match + Date.parse + Mutex acquisition check.

**RATIONALE**: UX crítica para kiosko desatendido. POST `/facturacion` esperando >200ms para refresh degrada perceived performance. Si budget se excede, el request continúa con token existente (graceful degradation — `handle401` retry cubre el 401 post-refresh).

### DEC-F3.2-08 — DELTA verdict (NOT NO-OP) — F3.2 IS user-facing

**DECISION**: F3.2 emite DELTA spec con 6 new REQ-OPS-113..118 (numbered post-F3.1 REQ-OPS-106..112). Spec delta materializes en `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md`.

**RATIONALE**: F3.2 ES user-facing behavior observable:
- (a) Countdown visual decreciente cada 1000ms (clock visible al operador).
- (b) Form disabled durante lockout (interacción observable).
- (c) Pre-flight gate evita 401 mid-write en `/facturacion/*` + `/caja/arqueo/*` (latency + correctness observable).
- (d) Refresh 50min automático (session longevity observable).

Per F1.15 + F3.1 precedent, user-facing ⇒ spec delta materialized. F2.x precedent (NO-OP stub via DEC-ELEC-10, DEC-FETCH-10, DEC-UPD-13) aplica solo a infra-only HU sin behavior visible al operador. F3.2 rompe el precedent NO-OP siguiendo F3.1.

### DEC-F3.2-09 — e2e lockout attempts: configurable via env (default 4)

**DECISION**: `e2e/auth/lockout.spec.ts` E1 test hace `max_intentos_login - 1` intentos fallidos + 1 intento que recibe 429 → asserts countdown. Default e2e usa `MAX_INTENTOS_LOGIN = 4` (rápido para test). Backend configurable via `configuracion_seguridad.max_intentos_login` (default 5 per `auth.py:225`).

**RATIONALE**: Test rápido (4 intentos vs 5) sin sacrificar coverage. El test verifica el FLOW (intentos fallidos → 429 → countdown), no el número EXACTO de intentos. MSW/page.route mockea 429 después de N intentos — N es param.

### DEC-F3.2-10 — Forward hook: pre-flight paths extensibilidad

**DECISION**: `PRE_FLIGHT_PATHS` constante módulo-level permite extensión future via nueva constante `PRE_FLIGHT_PATHS_EXTENDED` o env var. F3.2 cubre `/facturacion/*` + `/caja/arqueo*` per DEC-SUC-03. F3.3+ (turno) puede extender a `/caja-sesion/*` si lo requiere.

**RATIONALE**: YAGNI — F3.2 NO incluye `/caja-sesion/*` (F3.3 decidirá). Pero la constante es extensibilidad-friendly para forward hooks.

## 8. Risks identificados (R1..R8)

| # | Risk | Severity | Mitigación |
|---|---|---|---|
| R1 | **Countdown drift** — `setInterval` puede pausar si tab inactive o system sleep → `secondsLeft` queda atrasado del wall clock | MEDIUM | DEC-F3.2-01: `Date.now()` baseline + recalc en cada tick (NO accumulator). Test U4 usa `vi.advanceTimersByTime(2000)` post-`vi.useFakeTimers()` y verifica `secondsLeft` decrementa 2 (no 1). |
| R2 | **Pre-flight race con Mutex 401** — pre-flight triggerea refresh + 401 response triggerea refresh concurrent → doble refresh | LOW | DEC-F3.2-03 + F2.2 DEC-FETCH-03: pre-flight REUSA `refreshAccessToken()` Mutex. Si 401 llega mid-pre-flight, ambos callers comparten UNA promesa. NO doble refresh. |
| R3 | **50min refresh coincide con active request** — SWR revalida `/auth/me` mientras operador está submiteando POST `/facturacion` → potential interference | LOW | SWR `refreshInterval` es non-blocking — `parkosFetch('/auth/me')` corre en paralelo con POST `/facturacion`. Ambos viajan con MISMO access_token (read at request start). NO conflicto. SWR mutation isolation. |
| R4 | **Countdown cleanup en unmount** — `setInterval` no cleared en unmount → memory leak + late callback en componente desmontado | MEDIUM | DEC-F3.2-01: `useEffect` retorna cleanup `clearInterval(intervalId)`. Test U2 verifica `unmount → no callback fires`. |
| R5 | **Pre-flight latency >200ms** — refresh HTTP se cuelga + degrada POST crítico UX | LOW | DEC-F3.2-07: graceful degradation — si `refreshIfExpiringSoon` falla o tarda, el request continúa con token existente. `handle401` retry cubre 401 post-refresh. Budget 200ms es soft target, no hard fail. |
| R6 | **WCAG countdown accessibility** — screen reader no anuncia countdown updates | MEDIUM | DEC-F3.2-05 + DEC-F3.2-06: `<p role="status" aria-live="polite">` anuncia cambios cada ~30s (NO cada segundo — interruptivo). `aria-label={t('lockoutLabel')}` da contexto. axe-core scan valida 0 violaciones (A1 test). |
| R7 | **429 sin `Retry-After` header** — backend anomaly omite header → countdown con `retryAfterSeconds: 0` → display inmediato "00:00" sin tiempo real | LOW | F3.1 precedent (loginApi.ts:59-63): `parseRetryAfter` retorna 0 si header falta. UI fallback: mostrar `t('lockout')` sin countdown numérico (genérico "Cuenta bloqueada temporalmente"). DEC-F3.2-02: `useCountdown(0)` retorna `{secondsLeft: 0, isExpired: true}` → form re-enabled inmediato (sin display). |
| R8 | **Refresh rotation race** — pre-flight + 401 retry concurrent + rotation PR7 backend | LOW | F2.2 DEC-FETCH-03 Mutex preserved. Rotation con `jti` reuse detection es PR7 backend (forward). F3.2 NO introduce rotation; consume Mutex as-is. |

**Riesgos cerrados**: 8/8 con mitigación explícita. **0 KNOWN-MISSING**.

## 9. Acceptance gates (G1..G6)

| # | Gate | Mecanismo | Source |
|---|---|---|---|
| G1 | `useCountdown` setInterval(1000) cleanup on unmount | `vitest useCountdown.test.ts` U1 baseline + U2 cleanup + U3 onComplete + U4 drift resistance | T1 |
| G2 | `AccountLockedError.retryAfterSeconds` parsed correctly (ya shipped F3.1, F3.2 NO regresiona) | `vitest loginApi.test.ts` U3 + U3b (F3.1 existente) | T2 regression |
| G3 | `LoginForm` form disabled durante countdown | `vitest LoginForm.test.tsx` U8 (F3.2 nuevo) — mock `useCountdown` con `secondsLeft=300, isExpired=false` + assert `input[disabled]` + `button[disabled]` | T2 |
| G4 | Countdown auto re-enable al llegar a 0 | `vitest Login.test.tsx` U10 (F3.2 nuevo) — mock 429 + advance fake timers + assert `errorState === null` post-isExpired | T2 |
| G5 | `parkosFetch` pre-flight fires antes de `POST /facturacion/*` + `POST /caja/arqueo` | `vitest parkosFetch.test.ts` U5 expiring soon + U6 not expiring + U7 GET no triggerea (F3.2 nuevos) | T3 |
| G6 | 4 e2e scenarios verde (countdown display + decrement + re-enable + axe-core) | `playwright e2e/auth/lockout.spec.ts` E1+E2+E3+A1 (F3.2 nuevos) — sandbox SKIPPED-env per F.6 precedent | T4 |

**Estado pre-flight**: 0/6 PASS al inicio (no implementado). Target 6/6 PASS post-implementación (G2 ya PASS por F3.1 precedent — regression test).

**Sandbox F.6 caveat**: G6 puede SKIPPED-env en `npm 11.16.0` (F2.1 + F2.2 + F2.3 + F3.1 archive precedent). Unit tests G1, G3, G4, G5 + G2 regression SÍ corren. Documentado como deviation D-env en `verify-report.md`, NO project defect.

## 10. Atomic tasks (T1..T4)

Cada task es **atómica** (commiteable independientemente con tests verde), pero se ejecutan en orden T1 → T2 → T3 → T4 (con T2 y T3 potencialmente en paralelo porque T1+T2 son frontend UI + T3 es infra).

### 10.1 T1 — `useCountdown` hook + 4 unit tests

**Budget**: ~40 LOC production + ~50 LOC tests = **~90 LOC**.

**Archivos**:
- `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (NEW, ~40 LOC — `Date.now()` baseline + `setInterval(1000)` + cleanup + `onComplete` callback).
- `apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts` (NEW, ~50 LOC — U1 baseline Date.now(), U2 cleanup on unmount, U3 onComplete fires at 0, U4 drift resistance via fake timers).

**Commit message**: `feat(auth): adicionar useCountdown hook con Date.now() baseline + cleanup + onComplete`

**Acceptance** (G1 — §9): U1 + U2 + U3 + U4 verde. Hook exportado desde `features/auth/hooks/useCountdown.ts` consumible por LoginForm (T2) + forward hooks F4.x/F11.x.

### 10.2 T2 — Integrar `useCountdown` en LoginForm + countdown display + 3 unit tests

**Budget**: ~40 LOC production + ~40 LOC tests = **~80 LOC**.

**Archivos**:
- `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (MODIFY, +25 LOC — consume `useCountdown(retryAfterSeconds)` cuando `error.kind === 'lockout'`, renderiza `<p role="status" aria-live="polite">`, aplica `disabled` a inputs + submit durante lockout).
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY, +10 LOC — wire `useCountdown.isExpired` para reset `errorState` a null).
- `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (MODIFY, +3 keys — `lockoutCountdown`, `lockoutReEnable`, `lockoutLabel`).
- `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` (MODIFY, +25 LOC — U8 lockout disables form, U9 countdown decrements).
- `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (MODIFY, +15 LOC — U10 isExpired resets errorState).

**Commit message**: `feat(auth): integrar useCountdown en LoginForm + countdown display + 3 i18n keys`

**Acceptance** (G2 regression + G3 + G4 — §9): LoginForm muestra countdown durante lockout; form disabled mientras `secondsLeft > 0`; auto re-enable al llegar a 0; axe-core 0 violaciones durante countdown state.

### 10.3 T3 — `parkosFetch` pre-flight gate + `useAuth` 50min refresh + 5 unit tests

**Budget**: ~30 LOC production + ~70 LOC tests = **~100 LOC**.

**Archivos**:
- `apps/ui-kit/src/hooks/useAuth.ts` (MODIFY, line 60 — `refreshInterval: 5 * 60 * 1000` → `REFRESH_INTERVAL_MS = 50 * 60 * 1000` + constante exportada + JSDoc update).
- `apps/ui-kit/src/fetch/parkosFetch.ts` (MODIFY, +20 LOC — `PRE_FLIGHT_PATHS` regex + `PRE_FLIGHT_THRESHOLD_MS` const + `refreshIfExpiringSoon()` internal function + integration en `parkosFetchRaw` antes del fetch).
- `apps/ui-kit/src/hooks/useAuth.test.ts` (MODIFY, +10 LOC — verify `REFRESH_INTERVAL_MS = 50 * 60 * 1000`).
- `apps/ui-kit/src/fetch/parkosFetch.test.ts` (MODIFY, +60 LOC — U5 expiring soon triggers refresh, U6 not expiring skips refresh, U7 GET no triggerea, U8 refresh failure graceful degradation, U9 Mutex shared with 401 path).

**Commit message**: `feat(refresh): 50min SWR refresh + pre-flight gate antes de POST /facturacion/* + /caja/arqueo`

**Acceptance** (G5 — §9): `useAuth.refreshInterval = 50 * 60 * 1000`. `parkosFetchRaw` invoca `refreshIfExpiringSoon()` antes de POST matcheando `PRE_FLIGHT_PATHS` cuando `expiresAt - now < 5min`. Refresh failure NO bloquea request.

### 10.4 T4 — e2e lockout scenario + axe-core A1

**Budget**: ~80 LOC tests.

**Archivos**:
- `apps/electron-sucursal/e2e/auth/lockout.spec.ts` (NEW, ~80 LOC — E1 4 intentos → 429 + countdown visible, E2 countdown decrementa, E3 form re-enable al 0, A1 axe-core WCAG 2.1 AA).

**Commit message**: `test(electron): adicionar 4 e2e lockout (countdown display + decrement + re-enable + axe-core)`

**Acceptance** (G6 — §9): 4 escenarios per plan.md:1315 verbatim. Sandbox F.6 precedent: SKIPPED-env en `npm 11.16.0` — documentado como deviation D-env en `verify-report.md`.

### 10.5 Resumen de budgets

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 useCountdown hook | 40 | 50 | 90 |
| T2 Login countdown integration | 40 | 40 | 80 |
| T3 parkosFetch pre-flight + useAuth 50min | 30 | 70 | 100 |
| T4 e2e lockout 4 scenarios | 0 | 80 | 80 |
| **TOTAL** | **110** | **240** | **350** |

Total real ~130 LOC production matches plan.md:1317 verbatim (~110 production + ~20 JSDoc/configs = ~130).

## 11. Cluster map (C1)

F3.2 se descompone en **1 cluster** (C1) con orden interno T1 → (T2 || T3) → T4. T2 y T3 pueden ejecutarse en paralelo (T2 frontend UI, T3 infra ui-kit) si el executor lo permite — ambos commitean independientemente.

### 11.1 C1: Lockout countdown + refresh transparente end-to-end (T1+T2+T3+T4)

**Archivos**:
- `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (~40 LOC, T1).
- `apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts` (~50 LOC, T1).
- `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (MODIFY, +25 LOC, T2).
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY, +10 LOC, T2).
- `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` (MODIFY, +25 LOC, T2).
- `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (MODIFY, +15 LOC, T2).
- `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (MODIFY, +3 keys, T2).
- `apps/ui-kit/src/hooks/useAuth.ts` (MODIFY, line 60, T3).
- `apps/ui-kit/src/fetch/parkosFetch.ts` (MODIFY, +20 LOC, T3).
- `apps/ui-kit/src/hooks/useAuth.test.ts` (MODIFY, +10 LOC, T3).
- `apps/ui-kit/src/fetch/parkosFetch.test.ts` (MODIFY, +60 LOC, T3).
- `apps/electron-sucursal/e2e/auth/lockout.spec.ts` (~80 LOC, T4).

**Total C1**: ~130 LOC production + ~240 LOC tests = **~370 LOC**.

Plan 130 LOC production matches: 110 authored + 20 JSDoc/configs.

### 11.2 Orden de ejecución

T1 → (T2 || T3) → T4. T1 antes de T2 porque T2 consume `useCountdown` que T1 crea. T2 antes de T4 porque T4 e2e tests requieren LoginForm countdown wired (T2 output). T3 antes de T4 porque T4 e2e tests pueden verificar pre-flight (forward coverage). T2 y T3 son independientes — pueden ejecutarse en paralelo.

### 11.3 Risks del cluster

- **Cluster-wide regression**: T3 modifica `useAuth.ts:60` (refresh interval). Si T3 rompe el SWR refresh, useAuth() se cae → Login redirect fails → F3.1 regression. Mitigation: T3 verifica `REFRESH_INTERVAL_MS = 50 * 60 * 1000` via unit test (G5).
- **Cluster-wide a11y regression**: T2 agrega `<p role="status" aria-live="polite">`. Si WCAG falla, axe-core A1 (F3.1) puede romperse post-T2. Mitigation: A1 test corre POST-T2 + POST-T4 (e2e regresión check).

## 12. Precedents

| Precedent | Aplicación F3.2 | Source |
|---|---|---|
| **F3.1 (Login email+password)** | Container/Presentational split + Zod local + i18n keys + 401 anti-enumeration + e2e axe-core pattern | `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` |
| **F2.2 (parkosFetch + authStore + useAuth)** | Mutex singleton preserved + refresh-once 401 invariant + SWR refreshInterval baseline + Zod validation optional | `apps/ui-kit/src/{fetch/parkosFetch.ts, store/authStore.ts, hooks/useAuth.ts}` |
| **F2.1 (Electron skeleton + shadcn)** | vitest + @testing-library/react + axe-core + playwright e2e pattern + i18n 7 namespaces | `apps/electron-sucursal/src/renderer/components/ui/` + `e2e/a11y/wcag-2.1-aa.spec.ts` |
| **F1.15 (login histórico)** | DELTA precedent (user-facing behavior in spec) → F3.2 emits 6 new REQ-OPS-113..118 | `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/specs/operations/spec.md` |
| **F1.13 (arqueo defense in depth XR6)** | 5-layer defense in depth pattern (auth + engineering + a11y + contract + retry-budget) — F3.2 contributes a11y (countdown WCAG) + retry-budget (pre-flight) layers | `openspec/specs/operations/spec.md:3951` |
| **DEC-SUC-03** | Refresh 50min + pre-flight antes de pago/arqueo — F3.2 implementa verbatim | `plan.md:418` |
| **DEC-FETCH-03** | Mutex singleton refreshAccessToken — F3.2 pre-flight REUSA el mismo Mutex | `apps/ui-kit/src/store/authStore.ts:100-128` |
| **DEC-ELEC-10 + DEC-FETCH-10 + DEC-UPD-13** | F2.x NO-OP stub precedent — F3.2 ROMPE porque user-facing (DELTA) | F2.1/F2.2/F2.3 archive reports |

### 12.1 DEC-F3.2-08 verdict ratificación

F3.2 ES user-facing behavior observable:
- (a) countdown visual decreciente cada 1000ms (clock visible al operador).
- (b) form disabled durante lockout (interaction observable).
- (c) pre-flight gate evita 401 mid-write en `/facturacion/*` + `/caja/arqueo/*` (latency + correctness observable).
- (d) refresh 50min automático (session longevity observable).

Per F1.15 + F3.1 precedent, user-facing ⇒ spec delta materialized. F3.2 emite 6 new REQ-OPS-113..118 en `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md` siguiendo Given/When/Then/And RFC 2119 format F1.15 + F3.1 verbatim.

F2.x NO-OP precedent (DEC-ELEC-10, DEC-FETCH-10, DEC-UPD-13) NO aplica a F3.2 — esos HU son infra-only sin behavior visible al operador. F3.2 ES UI + UX behavior, rompe el precedent siguiendo F3.1.

## 13. Anti-patterns a evitar

- **NO countdown con `setTimeout` recursivo sin cleanup** → memory leak. Usar `setInterval` + `clearInterval` en `useEffect` cleanup (DEC-F3.2-01).
- **NO countdown con accumulator** (`secondsLeft--`) → drift si tab inactive. Usar `Date.now()` baseline (R1 mitigation).
- **NO refresh-on-tick sin coalescing** → si SWR refreshInterval coincide con active request, doble fetch. SWR ya coalesces by design.
- **NO pre-flight que rompa Mutex F2.2** → doble refresh risk. Reusar `refreshAccessToken()` Mutex (DEC-F3.2-03 + DEC-FETCH-03).
- **NO countdown sin `aria-live`** → WCAG fail. Usar `<p role="status" aria-live="polite">` (DEC-F3.2-05).
- **NO countdown con `aria-live="assertive"`** → interruptivo para screen readers. Usar `polite` + cambio cada ~30s (NO cada segundo).
- **NO pre-flight en TODOS los POST** → latency overhead innecesario. Solo critical paths `/facturacion/*` + `/caja/arqueo/*` (DEC-F3.2-03).
- **NO pre-flight en GET requests** → 401 retry cubre. Pre-flight solo mutacionales (DEC-F3.2-03).
- **NO refresh interval configurable via UI** → kiosko desatendido, no debe ser user-mutable. Hardcoded 50min per DEC-SUC-03.
- **NO countdown styling library externa** → bundle size kiosko. `formatTime` helper inline (~5 LOC).
- **NO i18n key con countdown hardcoded** ("9:47") → requiere i18n template `{{mm}}:{{ss}}` + `i18next` interpolation.
- **NO backend cambios para ajustar max_intentos_login** → fuera scope Fase 3. Consumir `configuracion_seguridad.max_intentos_login` shipped.
- **NO rotacion de refresh_token en F3.2** → PR7 backend. F3.2 consume Mutex as-is (R8 mitigation).

## 14. Forward hooks

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.3** (Abrir/Cerrar turno) | pre-flight gate automático para `POST /caja-sesion/*` si F3.3 decide agregar al path match (forward — no obligatorio) | DEC-F3.2-10: extender `PRE_FLIGHT_PATHS` regex para incluir `/caja-sesion/*` |
| **HU-F3.3** | `useAuth().user.sucursal` + `permisos[]` hidratados post-F3.1 (F3.2 NO toca useAuth shape) | F3.3 consume via SWR data |
| **HU-F3.x** (logout button UI) | `useAuthStore.clear()` ya implementado en F2.2 + `parkos:auth:cleared` window event | F3.3+ logout button dispatch `clear()` + `navigate('/login')` |
| **HU-F3.x** (AuthGuard component) | `parkos:auth:cleared` window event | F3.3+ `<AuthGuard>` envuelve `<Routes>` excepto `/login` → `navigate('/login?next=...')` |
| **HU-F4.x** (catálogos + ocupación) | `useCountdown` para retry buttons con countdown visual | F4.x export `useRetryWithCountdown` pattern que envuelve `useCountdown` |
| **HU-F4.x** | `parkosFetch` pre-flight gate — F4.x hereda automáticamente (T3 cubre `/facturacion/*`) | Cero cambios F4.x |
| **HU-F5.x** (facturación) | pre-flight gate automático (`/facturacion/*` ya cubierto) + `useAuth.refreshInterval: 50min` | Cero cambios F5.x |
| **HU-F5.x** | `useCountdown` para retry buttons post-409 conflicto | F5.x export `useRetryWithCountdown` |
| **HU-F11.x** (sync UI + alertas CU-07/14) | `useCountdown` para reintentos de sync con countdown visual | F11.x export `useSyncRetryCountdown` que envuelve `useCountdown` con exponential backoff |
| **HU-F11.x** | `useAuth` 50min refresh — F11.x hereda automáticamente | Cero cambios F11.x |
| **PR7 backend** (refresh-token rotation) | `refreshAccessToken` Mutex F2.2 + pre-flight F3.2 → rotación con `jti` reuse detection | PR7 backend: detectar reuse de `jti` claim y revocar cadena. F3.2 ya provee Mutex infrastructure. |

## 15. Open questions

**Ninguna blocker**. Exploration completa. Las 2 inconsistencies detectadas (I1 max_intentos 4 vs 5; I2 refreshInterval 5min → 50min) tienen resolutions propuestas en §1 que se ratifican en `sdd-propose` como DEC-F3.2-04 + DEC-F3.2-09.

**Notas para `sdd-propose`**:
- **N1**: I1 (max_intentos) → DEC-F3.2-09 configurable via env (default 4 e2e).
- **N2**: I2 (refreshInterval 5min → 50min) → DEC-F3.2-04 constante `REFRESH_INTERVAL_MS = 50 * 60 * 1000`.
- **N3**: I3 (`/caja/arqueo` no existe todavía) → DEC-F3.2-10 forward hook para F3.3+ extender `PRE_FLIGHT_PATHS`.

## 16. Pre-flight result (KNOWN-MISSING)

0 KNOWN-MISSING. Pre-flight 10/10 PASS (§3). F3.2 ready for sdd-propose sin gaps blocker.

**Sandbox F.6 caveat** (no es KNOWN-MISSING, es deviation env esperada): e2e G6 puede SKIPPED-env en `npm 11.16.0`. Documentado en §3 + §9 + §10.4 como deviation D-env. No requiere fix pre-propose.

## 17. Out-of-scope explícito

F3.2 NO incluye (explícitamente deferido):

- **Backend cambios**: `configuracion_seguridad.max_intentos_login` ya shipped Fase 1 (HU-F1.2); F3.2 consume via `parseRetryAfter`. NO modifica backend.
- **Refresh-token rotation**: PR7 backend. F3.2 consume Mutex F2.2 sin modification.
- **AuthGuard component**: F3.3+ (intercept `parkos:auth:cleared` → `navigate('/login?next=...')`).
- **Logout button UI**: F3.3+ placeholder.
- **Recuperación de password / forgotPassword**: fuera Fase 3 (futuro).
- **2FA / WebAuthn / biometric**: fuera Fase 3 (futuro).
- **Multi-tab login UI**: kiosko single-tab per F2.3 `requestSingleInstanceLock` (DEC-UPD-07).
- **Turno abrir/cerrar**: F3.3 (`features/caja/pages/{AbrirTurno,CerrarTurno}.tsx`).
- **Countdown styling library**: vanilla `formatTime` helper inline. NO librería externa.
- **Toast notifications**: out of scope Fase 3 (forward F11.x sync UI).
- **REFRESH_INTERVAL_MS configurable via UI**: hardcoded 50min per DEC-SUC-03. Env var es forward hook.
- **Pre-flight para TODOS los POST**: solo `/facturacion/*` + `/caja/arqueo/*` per DEC-SUC-03.
- **Pre-flight para GET requests**: 401 retry cubre. Pre-flight solo mutacionales.
- **Countdown para retry buttons (forward use)**: useCountdown se reusa en F4.x/F11.x, pero F3.2 solo lo integra en Login.
- **i18n plurals para countdown**: mm:ss suficiente (max 99:59). NO requiere `i18next-plural` plugin.
- **OS-level kiosk PIN rotation**: F2.3 kiosko mode baseline, no F3.2 touch.
- **Sucursal selector UI**: JWT ya pinea sucursal (single-branch kiosko).
- **`rememberMe` / `forgotPassword` keys**: pre-existentes en `auth.json:10-11` pero F3.2 NO las usa (kiosko desatendido).
- **Zod schema validation en boundary via `parkosFetch<T>(url, schema)`**: DEC-FETCH-05 optional, F3.2 NO exige.
- **Per-account countdown state persistence**: countdown es ephemeral (vive solo durante lockout active). Post-unmount, state GC'd. NO persist a electron-store.
- **Pre-flight gate para endpoints no documentados**: requiere DEC explicito (DEC-F3.2-10 forward). Default regex NO incluye paths nuevos.

## 18. Apéndice: archivos a tocar

### 18.1 NEW (crear)

- `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (T1, ~40 LOC).
- `apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts` (T1, ~50 LOC).
- `apps/electron-sucursal/e2e/auth/lockout.spec.ts` (T4, ~80 LOC).
- `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/exploration.md` (this file).
- `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/proposal.md` (proposal phase).
- `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md` (spec phase, DELTA stub per DEC-F3.2-08 con 6 new REQ-OPS-113..118).
- `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/design.md` (design phase).
- `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/tasks.md` (tasks phase).
- `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/verify-report.md` (verify phase).
- `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/archive-report.md` (archive phase).

### 18.2 MODIFY (extender)

- `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (T2, +25 LOC — countdown display + form disabled).
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (T2, +10 LOC — useCountdown.isExpired reset errorState).
- `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` (T2, +25 LOC — U8 + U9).
- `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (T2, +15 LOC — U10).
- `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (T2, +3 keys).
- `apps/ui-kit/src/hooks/useAuth.ts` (T3, line 60 — refreshInterval 5min → 50min).
- `apps/ui-kit/src/fetch/parkosFetch.ts` (T3, +20 LOC — pre-flight gate).
- `apps/ui-kit/src/hooks/useAuth.test.ts` (T3, +10 LOC — REFRESH_INTERVAL_MS verification).
- `apps/ui-kit/src/fetch/parkosFetch.test.ts` (T3, +60 LOC — U5+U6+U7+U8+U9).
- `pending.md` (archive phase — marcar F3.2 ✅ cerrado, actualizar Total LOC restante, footer a "Fase 3 2/3 cerrado").

### 18.3 READ ONLY (anchors — NO modificar)

- `apps/electron-sucursal/electron/main.ts` (F2.3, no F3.2 touch — DEC-F3.1-04 login HTTP no IPC, F3.2 hereda).
- `apps/electron-sucursal/electron/preload.ts` (F2.2, no F3.2 touch — F3.2 NO agrega IPC methods).
- `apps/electron-sucursal/electron/bridge.d.ts` (F2.2+F2.3, no F3.2 touch).
- `apps/electron-sucursal/src/features/auth/api/loginApi.ts` (F3.1, READ ONLY — `AccountLockedError` ya shipped, F3.2 consume as-is).
- `apps/electron-sucursal/src/features/auth/api/loginSchema.ts` (F3.1, READ ONLY — Zod schema no F3.2 touch).
- `apps/ui-kit/src/store/authStore.ts` (F2.2, READ ONLY — `setTokens` + `clear` + `refreshAccessToken` Mutex shipped, F3.2 consume as-is).
- `apps/ui-kit/src/cn.ts` + `apps/ui-kit/src/tokens.ts` (F2.1, no F3.2 touch).
- `apps/electron-sucursal/src/renderer/components/ui/{form,input,button}.tsx` (F2.1, no F3.2 touch — reusa shadcn primitives).
- `apps/electron-sucursal/src/renderer/i18n/index.ts` (F2.1, no F3.2 touch — auth namespace ya registrado).
- `apps/electron-sucursal/src/renderer/i18n/locales/{common,operacion,caja,facturacion,sync,errors}.json` (F2.1, no F3.2 touch).
- `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (F2.3, no F3.2 touch).
- `apps/electron-sucursal/src/renderer/App.tsx` (F3.1, no F3.2 touch — `/login` route ya wired).
- `apps/electron-sucursal/src/renderer/main.tsx` (F2.1, no F3.2 touch).
- `apps/electron-sucursal/e2e/{scaffold,auth/login,auth/parkos-fetch,auth/bridge,a11y/wcag-2.1-aa,lifecycle,kiosko}.spec.ts` (F2.1+F2.2+F2.3+F3.1, no F3.2 touch — agrega solo lockout.spec.ts).
- `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py` (HU-F1.2 + HU-F1.15 shipped, no F3.2 touch — F3.2 consume `Retry-After` header as-is).
- `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` (HU-F1.2 shipped, no F3.2 touch).
- `openspec/specs/operations/spec.md` (canonical, no F3.2 touch — DELTA stub en `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md` per F2.x DEC-ELEC-10 precedent roto por DEC-F3.2-08).

### 18.4 Total de archivos impactados

- **NEW**: 10 archivos (~170 LOC production/tests + ~150 LOC artifacts SDD).
- **MODIFY**: 10 archivos (~70 LOC delta production + 3 keys i18n + pending.md housekeeping).
- **READ ONLY**: 18 archivos.
- **TOTAL IMPACT**: 20 archivos de ~170 LOC nuevos + ~70 LOC delta.

---

## CHANGELOG

- (2026-09-15) F3.2 explore phase complete — 17 secciones + apéndice, 10 DEC-F3.2-NN (DEC-F3.2-01..10), 8 riesgos R1..R8, 6 acceptance gates G1..G6, 4 atomic tasks T1..T4, 1 cluster C1. Pre-flight 10/10 PASS + 0 KNOWN-MISSING. F3.1 deliverables (Login.tsx + LoginForm.tsx + loginApi.ts + AccountLockedError + LoginErrorState) CONFIRMED shipped. DEC-F3.2-08 verdict = **DELTA** (F3.2 IS user-facing: countdown visual + form disabled + pre-flight gate + 50min refresh). 6 new REQ-OPS-113..118 planificadas en `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md`. Inconsistencies detectadas (I1 max_intentos 4 vs 5; I2 refreshInterval 5min → 50min) tienen resolutions DEC-F3.2-04 + DEC-F3.2-09. F2.2 primitives (parkosFetch Mutex + authStore.setTokens/clear + useAuth SWR) CONFIRMED ready for F3.2 modification. Ready for sdd-propose.

---

**End of exploration.**
