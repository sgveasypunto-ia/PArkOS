# Delta Spec — HU-F3.2 Lockout visible (countdown) + refresh transparente (50min auto + pre-flight)

> **Phase**: spec (sdd-spec) · **Status**: ready for sdd-design (parallel) + sdd-tasks
> **HU ID**: HU-F3.2 (Fase 3 — segunda HU; Autenticación y turno de caja, hardening UX + lifecycle del `access_token`)
> **Change**: `hu-f3-2-lockout-refresh-pre-flight`
> **Spec canonical**: `openspec/specs/operations/spec.md` (v: post-F3.1, 112 REQ-OPS-001..112)
> **Delta type**: MATERIALIZED con 6 new REQ-OPS-113..118 (user-facing behavior per F3.1 + F1.15 precedent)
> **DEC-F3.2-08 + DEC-F3.2-11 verdict**: DELTA stub (NOT NO-OP) — F3.2 IS user-facing behavior observable (countdown visual decreciente + form disabled + pre-flight gate + refresh 50min + Mutex preserved + WCAG 2.1 AA countdown).

---

## 0. Metadata

- **HU**: HU-F3.2
- **Fase**: 3 (Autenticación y turno de caja — segunda HU; hardening UX + lifecycle del `access_token`)
- **Spec delta type**: MATERIALIZED DELTA (NOT NO-OP stub)
- **New REQ-OPS**: 6 (REQ-OPS-113..118)
- **Author**: Parkos Dev <dev@parkos.local>
- **Date**: 2026-09-15
- **Precedente directo**: F3.1 (Login email+password) archivado 2026-09-15 con 7 new REQ-OPS-106..112 user-facing (`openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/specs/operations/spec.md`). Precedente histórico: F1.15 (login histórico) archivado 2026-09-15 con 4 new REQ-OPS-102..105.
- **Spec canonical vigente**: 112 REQ-OPS (REQ-OPS-001..112) + 6 XR (REQ-OPS-XR1..XR6) post-F3.1 archive.
- **Numeración monotónica verificada**: 112 → 113 → 114 → 115 → 116 → 117 → 118 (0 gaps, sin duplicados). Materialization al canonical `operations/spec.md` ocurre en `sdd-archive` phase, NO en spec phase.

---

## 1. Purpose

Esta delta cierra los **3 gaps UX críticos** que F3.1 archivado 2026-09-15 dejó abiertos en el lifecycle del `access_token`, completando el primer consumer end-to-end del patrón "kiosko desatendido, sesión robusta" exigido por `plan.md:418` (DEC-SUC-03 — "Refresh transparente cada 50 minutos y antes de escrituras críticas (pago, arqueo)"). A diferencia de F2.1/F2.2/F2.3 (infra-only con NO-OP stub per `DEC-ELEC-10`, `DEC-FETCH-10`, `DEC-UPD-13`), F3.2 ES user-facing behavior observable en cuatro dimensiones: (a) countdown visual decreciente cada 1000ms (clock visible al operador que agotó `max_intentos_login`); (b) form disabled durante lockout (interacción observable — previene reintentos hostiles que devuelven 401 antes del Retry-After); (c) pre-flight gate que evita 401 mid-write en POST `/facturacion/*` + POST `/caja/arqueo` (latency + correctness observable — el operador ve una operación fluida en lugar de un 401 transitorio); (d) refresh 50min automático contra `ACCESS_TOKEN_TTL = 3600` (session longevity observable — 10min safety margin vs F2.2 baseline de 5min × 12/hora desperdicio).

`DEC-F3.2-08` + `DEC-F3.2-11` (introducidos en `proposal.md §4.8 + §4.11`) **rompen** el precedent NO-OP de F2.x y adoptan precedent F1.15 + F3.1: ambas HU user-facing materializaron `REQ-OPS-NNN` dentro del spec canónico. Las 6 new REQ-OPS-113..118 documentan el comportamiento observable al operador en formato Given/When/Then/And RFC 2119, con anchor links explícitos a `DEC-F3.2-NN` ratificados en `exploration.md §7` + `proposal.md §4`. Las decisiones técnicas viven en `proposal.md` (qué hace cada componente, layout, archivos), las requirements viven en este spec (qué comportamiento debe ser verdadero post-cambio).

Adicionalmente, F3.2 entrega **`useCountdown`** como primer hook genuinely reusable del feature `auth` — `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` se exporta para forward consumers F4.x (retry buttons con `useRetryWithCountdown`) + F11.x (reintentos de sync con `useSyncRetryCountdown` + exponential backoff). El pre-flight gate `refreshIfExpiringSoon()` se invoca antes de POST críticos per DEC-SUC-03 y reusa el Mutex `refreshAccessToken` de F2.2 (`DEC-FETCH-03` invariant preserved) — cero doble refresh ante 401 reactivo concurrente. Defense in depth XR6 contribution: F3.2 suma la capa a11y (countdown WCAG 2.1 AA) + retry-budget proactiva (pre-flight) sobre la base sentada por F2.2 (refresh-once reactivo).

---

## 2. Scope of the delta

### 2.1 In scope (6 new REQ-OPS)

| REQ-OPS | Comportamiento observable |
|---|---|
| **REQ-OPS-113** | `useCountdown(retryAfterSeconds, options?)` hook con `Date.now()` baseline (drift-resistant) + `setInterval(1000)` + cleanup en unmount + `onComplete` callback |
| **REQ-OPS-114** | `<LoginForm>` aplica `disabled={true}` a `<Input>` + `<Button type="submit">` mientras `useCountdown().secondsLeft > 0` + renderiza `<p role="status" aria-live="polite">` con countdown mm:ss |
| **REQ-OPS-115** | Auto re-enable del form cuando `useCountdown().isExpired === true` — `<Login>` container resetea `errorState` a `null` + foco al primer input |
| **REQ-OPS-116** | `parkosFetch` pre-flight gate `refreshIfExpiringSoon()` invocado antes de POST matcheando `PRE_FLIGHT_PATHS = /\/facturacion(\/\|$)\|\/caja\/arqueo/` cuando `expiresAt - now < PRE_FLIGHT_THRESHOLD_MS (5 * 60 * 1000)`, Mutex shared con handle401 F2.2 |
| **REQ-OPS-117** | `useAuth.refreshInterval: REFRESH_INTERVAL_MS = 50 * 60 * 1000` (constante exportada) — refresh transparente cada 50min vs `ACCESS_TOKEN_TTL = 3600` (10min safety margin) |
| **REQ-OPS-118** | WCAG 2.1 AA compliance: axe-core 0 violaciones en `<LoginForm>` durante lockout state (RNF-022, extiende REQ-OPS-112 F3.1 precedent) |

### 2.2 Out of scope (deferred a Fase 3+)

- **Backend cambios** — `configuracion_seguridad.max_intentos_login` + `minutos_bloqueo_login` ya shipped Fase 1 (HU-F1.2); `Retry-After` header ya implementado en `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:219-228`. F3.2 NO modifica backend.
- **Refresh-token rotation con `jti` reuse detection** — PR7 backend (forward hook `pending.md §5`); F3.2 consume Mutex F2.2 sin modification.
- **AuthGuard component** — `parkos:auth:cleared` event listener → `navigate('/login?next=...')` es F3.3+ (forward hook).
- **Logout button UI** — F3.3+ placeholder o HU posterior.
- **Recuperación de password / 2FA / WebAuthn / biometric** — fuera Fase 3 (futuro).
- **Multi-tab login UI** — kiosko single-tab per F2.3 `requestSingleInstanceLock` (DEC-UPD-07).
- **Turno abrir/cerrar** — F3.3 (`features/caja/pages/{AbrirTurno,CerrarTurno}.tsx`).
- **Countdown styling library externa** — `formatTime` helper inline (`mm:ss`), NO librería externa (mantener bundle size small — kiosko desatendido, RAM limitada).
- **Toast notifications** — out of scope Fase 3 (forward a F11.x sync UI).
- **OS-level kiosk PIN rotation** — F2.3 kiosko mode baseline, no F3.2 touch.
- **Sucursal selector UI** — JWT ya pinea sucursal (DEC-SUC-01 single-branch kiosko).
- **`rememberMe` / `forgotPassword` keys** — pre-existentes en `auth.json:10-11` pero F3.2 NO las usa (kiosko desatendido).
- **`REFRESH_INTERVAL_MS` configurable via UI** — hardcoded a 50min per DEC-SUC-03; configurabilidad via env (`PARKOS_REFRESH_INTERVAL_MS`) es forward hook F3.x.
- **Pre-flight para otros endpoints** — T3 cubre solo `/facturacion/*` + `/caja/arqueo*` per `plan.md:1311` + DEC-SUC-03. Otros POST críticos futuros se agregan via DEC-F3.2-10 (`PRE_FLIGHT_PATHS_EXTENDED` o env var).
- **Zod schema validation en boundary via `parkosFetch<T>(url, schema)`** — `DEC-FETCH-05` optional, F3.2 NO exige.
- **Per-account countdown state persistence** — countdown es ephemeral (vive solo durante lockout active). Post-unmount, state GC'd. NO persist a electron-store.
- **i18n plurals para countdown** — `mm:ss` suficiente (max 99:59 = 2h, suficiente para `minutos_bloqueo_login` default 10min × max configurable 60min per `auth.py`).
- **`POST /auth/login` pre-flight** — `/auth/login` es anónimo (DEC-F3.1-05). Si por error matchea `/facturacion`, NO hay daño porque `expiresAt` es null pre-login → pre-flight skip.
- **Pre-flight en GET requests** — 401 retry cubre (handle401 F2.2). Pre-flight solo mutacionales POST.
- **Countdown para retry buttons (forward use)** — `useCountdown` se reusa en F4.x/F11.x, pero F3.2 solo lo integra en Login.

---

## 3. ADDED Requirements

### REQ-OPS-113 — `useCountdown(retryAfterSeconds, options?)` hook con `Date.now()` baseline (DEC-F3.2-01)

**Source**: HU-F3.2 (`plan.md:1311` + `DEC-F3.2-01` Date.now baseline + R1 mitigation drift resistance) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El hook `useCountdown(retryAfterSeconds: number, options?: { onComplete?: () => void }): { secondsLeft: number; isExpired: boolean }` MUST computar `endTime = Date.now() + retryAfterSeconds * 1000` en mount (wall clock anchor) y recalcular `secondsLeft = Math.max(0, Math.ceil((endTime - Date.now()) / 1000))` en cada tick de `setInterval(1000)` (NO accumulator pattern `secondsLeft--` — R1 mitigation contra drift si tab inactive + system sleep pause `setInterval`). El hook MUST limpiar el interval via `clearInterval(intervalId)` retornado en `useEffect` cleanup (R4 mitigation — unmount no deja memory leak ni late callbacks). Cuando `Date.now() >= endTime`, el hook MUST retornar `{secondsLeft: 0, isExpired: true}` e invocar `onComplete()` callback si fue provisto (exactly once). El hook MUST exportarse desde `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` para forward consumption (F4.x retry buttons + F11.x sync reintentos).

**Rationale**: Accumulator pattern (`secondsLeft--`) acumula drift cuando el browser throttle `setInterval` durante tab inactive o system sleep (60s+ intervals compressed). `Date.now()` baseline es drift-resistant — siempre recalcula desde wall clock. El hook se reutiliza cross-feature (F4.x retry buttons, F11.x sync reintentos) — primer hook genuinely reusable del feature `auth`.

**Source**: `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (NEW, T1 ~40 LOC — `Date.now()` baseline + `setInterval(1000)` + cleanup + `onComplete`); `apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts` (NEW, T1 ~50 LOC — U1 baseline + U2 cleanup + U3 onComplete + U4 drift resistance via `vi.advanceTimersByTime(2000)`); R1 risk + R4 risk en `exploration.md §8`.

**Scenario 1: Mount con retryAfterSeconds=600 → secondsLeft decreciente 1Hz**
- **Given** el operador está en lockout state con `retryAfterSeconds: 600` (10 minutos)
- **When** el hook `useCountdown(600, { onComplete })` se monta en `<LoginForm>`
- **Then** el primer render MUST retornar `{secondsLeft: 600, isExpired: false}` (`endTime = Date.now() + 600_000ms`)
- **And** cada tick de 1000ms MUST recalcular `secondsLeft = Math.max(0, Math.ceil((endTime - Date.now()) / 1000))`
- **And** tras 3 ticks verificados con `vi.advanceTimersByTime(3000)`, `secondsLeft` MUST ser `597` (NO `600 - 3 = 597` accidental accumulator — el test verifica el wall-clock path).

**Scenario 2: Drift resistance — tab inactive 30s + recovery recalcula desde wall clock**
- **Given** `useCountdown(600)` está activo con `endTime = Date.now() + 600_000ms`
- **When** el tab se vuelve inactive por 30s (browser throttle `setInterval` a >1000ms intervals)
- **Then** cuando el tab recupera foco, el primer tick post-recovery MUST recalcular `secondsLeft` desde `Date.now()` baseline, NO desde accumulator pausado
- **And** el display MUST saltar al valor real (e.g., `570` si pasaron 30s wall clock), NO al valor pausado (`597`).

**Scenario 3: Cleanup en unmount — clearInterval se ejecuta**
- **Given** `useCountdown(600)` está activo en `<LoginForm>`
- **When** el componente se desmonta (`navigate('/')` post-success, o `<LoginForm>` unmount por tree change)
- **Then** el `useEffect` cleanup MUST ejecutar `clearInterval(intervalId)`
- **And** NO MUST haber late callbacks del interval después de unmount (R4 mitigation).

**Scenario 4: onComplete callback fires cuando secondsLeft llega a 0**
- **Given** `useCountdown(600, { onComplete: spy })` está activo y `endTime` está a <1000ms en el futuro
- **When** el tick handler detecta `Date.now() >= endTime`
- **Then** el hook MUST retornar `{secondsLeft: 0, isExpired: true}`
- **And** `spy` MUST ser invocado exactamente una vez (not twice — el interval se limpia post-isExpired).

---

### REQ-OPS-114 — `<LoginForm>` renderiza countdown visible + aplica `disabled` durante lockout (DEC-F3.2-02 + DEC-F3.2-05 + DEC-F3.2-06)

**Source**: HU-F3.2 (`plan.md:1309` + `DEC-F3.2-02` form disabled + `DEC-F3.2-05` axe-core WCAG + `DEC-F3.2-06` 3 i18n keys) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<LoginForm>` MUST consumir `useCountdown(error.retryAfterSeconds)` cuando `error?.kind === 'lockout'` y renderizar `<p role="status" aria-live="polite" data-testid="login-countdown" aria-label={t('lockoutLabel', {time: formatTime(secondsLeft)})}>{t('lockoutCountdown', {time: formatTime(secondsLeft)})}</p>` ENTRE el `<p role="alert">{t('lockout')}</p>` (mensaje estático F3.1) y los inputs. Mientras `error?.kind === 'lockout' && !isExpired`, los `<Input>` y `<Button type="submit">` MUST renderizarse con `disabled={true}` + `aria-disabled="true"` (DEC-F3.2-02 — `disabled` previene submit + typing; `readonly` rejected por UX inconsistente). El helper `formatTime(secondsLeft)` MUST retornar string `mm:ss` (e.g., `"09:47"` para 587 segundos; max display `99:59`). Las 3 i18n keys MUST agregarse a `apps/electron-sucursal/src/renderer/i18n/locales/auth.json`: `lockoutCountdown` ("Reintento disponible en {{time}}"), `lockoutReEnable` ("El formulario se ha reactivado. Puedes intentar de nuevo."), `lockoutLabel` ("Tiempo restante para reintentar: {{time}}").

**Rationale**: F3.1 REQ-OPS-109 surfacea texto estático "Cuenta bloqueada. Intenta de nuevo en N minutos." sin countdown — el operador no sabe cuánto falta. F3.2 entrega UX profesional con countdown decreciente + form disabled. WCAG 2.1 AA compliance: `role="status"` + `aria-live="polite"` anuncia cambios a screen readers (NO `aria-live="assertive"` — interruptivo). `aria-label` describe el countdown contextualmente.

**Source**: `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (MODIFY F3.2 T2 +25 LOC — consume `useCountdown`, renderiza countdown display, aplica `disabled`); `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (MODIFY F3.2 T2 +3 keys); `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` (MODIFY F3.2 T2 +25 LOC — U8 lockout disables form, U9 countdown decrements); F3.1 `LoginForm.tsx:120-124` (texto estático precedent — F3.2 reemplaza por countdown); R6 risk en `exploration.md §8`.

**Scenario 1: lockout state activo → countdown visible + form disabled**
- **Given** `<LoginForm>` recibe `error: { kind: 'lockout', retryAfterSeconds: 587 }`
- **When** el hook `useCountdown(587)` retorna `{secondsLeft: 587, isExpired: false}`
- **Then** el componente MUST renderizar `<p role="status" aria-live="polite" data-testid="login-countdown">{t('lockoutCountdown', {time: '09:47'})}</p>`
- **And** los `<Input name="email">` + `<Input name="password">` MUST estar `disabled={true}` + `aria-disabled="true"`
- **And** el `<Button type="submit">` MUST estar `disabled={true}` + `aria-disabled="true"`.

**Scenario 2: Countdown decrementa visible 1Hz — `09:47` → `09:46` tras 1 tick**
- **Given** el countdown display muestra `"09:47"` (`secondsLeft: 587`)
- **When** `vi.advanceTimersByTime(1000)` ejecuta el siguiente tick
- **Then** el componente MUST re-renderizar con `<p data-testid="login-countdown">{t('lockoutCountdown', {time: '09:46'})}</p>`
- **And** el screen reader (axe-core scan) MUST detectar 0 violaciones (RNF-022 compliance).

**Scenario 3: form NO submitea durante lockout (defense anti-retry)**
- **Given** el form está en lockout state con `secondsLeft > 0`
- **When** el operador presiona Enter o click submit (forzado vía DOM)
- **Then** el form MUST NO invocar `onSubmit` (HTML `disabled` previene submit)
- **And** el backend MUST NO recibir un POST `/auth/login` con credenciales (defense contra retry hostil antes del Retry-After).

**Scenario 4: `formatTime(587)` retorna `"09:47"` (mm:ss con zero-padding)**
- **Given** `secondsLeft: 587` (9 minutos 47 segundos)
- **When** `formatTime(587)` ejecuta
- **Then** el retorno MUST ser el string `"09:47"` (mm padded con cero + `:` + ss padded con cero)
- **And** `formatTime(0)` MUST ser `"00:00"` (boundary inferior)
- **And** `formatTime(5999)` MUST ser `"99:59"` (boundary superior — max 99:59 para `minutos_bloqueo_login` configurable hasta 60min per `auth.py`).

---

### REQ-OPS-115 — Countdown auto re-enable al llegar a 0 (DEC-F3.2-02)

**Source**: HU-F3.2 (`plan.md:1315` + `DEC-F3.2-02` form re-enable + `DEC-F3.2-06` i18n `lockoutReEnable` notice) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<Login>` (container) MUST detectar cuando `useCountdown().isExpired === true` y resetear `errorState` a `null` para re-habilitar el form (inputs + submit vuelven a `disabled={false}`). Tras el reset, el componente MUST aplicar foco automático al primer input (`<Input name="email">`) vía `inputRef.current?.focus()` para que el operador pueda tipear inmediatamente. Opcionalmente, el componente MUST mostrar `<p role="status" aria-live="polite">{t('lockoutReEnable')}</p>` por ~3000ms antes de ocultarlo (DEC-F3.2-06 — UX feedback "El formulario se ha reactivado. Puedes intentar de nuevo."). El `useEffect` MUST tener deps `[isExpired, onResetErrorState]` para evitar loops infinitos.

**Rationale**: Sin auto re-enable, el operador queda atrapado en lockout state para siempre (o hasta refresh manual). El countdown llegando a 0 MUST trigger un cleanup completo: interval cleanup + errorState reset + foco ready para retry. UX profesional: el operador ve el feedback "reactivado" y sabe que puede intentar de nuevo.

**Source**: `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY F3.2 T2 +10 LOC — wire `useCountdown.isExpired` reset `errorState`); `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (MODIFY F3.2 T2 — `disabled` prop ahora depende de `!isExpired` además de `error.kind === 'lockout'`); `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (MODIFY F3.2 T2 +15 LOC — U10 isExpired resets errorState); R7 risk en `exploration.md §8` (429 sin Retry-After → `useCountdown(0)` retorna inmediato `{secondsLeft: 0, isExpired: true}` → form re-enabled sin display numérico).

**Scenario 1: isExpired true → errorState reset a null + form re-enabled**
- **Given** `<Login>` está en lockout state con `errorState = { kind: 'lockout', retryAfterSeconds: 10 }`
- **When** `useCountdown(10)` retorna `{secondsLeft: 0, isExpired: true}` (post-`vi.advanceTimersByTime(10_000)`)
- **Then** el `useEffect([isExpired])` MUST disparar `setErrorState(null)` (reset atómico)
- **And** el form MUST re-renderizar con `<Input>` + `<Button>` en `disabled={false}`
- **And** el foco MUST estar en `<Input name="email">` (auto-focus para retry inmediato).

**Scenario 2: Auto re-enable notice (`lockoutReEnable`) visible 3s**
- **Given** `isExpired === true` acaba de disparar
- **When** `<LoginForm>` renderiza el notice
- **Then** MUST aparecer `<p role="status" aria-live="polite" data-testid="lockout-re-enable">{t('lockoutReEnable')}</p>`
- **And** tras `vi.advanceTimersByTime(3000)`, el notice MUST desaparecer (cleanup state local)
- **And** NO MUST quedar el notice permanentemente (UX: el operador ya sabe que puede reintentar).

**Scenario 3: 429 sin Retry-After → `useCountdown(0)` inmediato re-enable**
- **Given** el backend anomaly omite el header `Retry-After` (R7 risk)
- **And** `loginApi.parseRetryAfter` retorna 0 (fallback)
- **When** `<Login>` recibe `AccountLockedError(retryAfterSeconds: 0)`
- **Then** `useCountdown(0)` MUST retornar inmediato `{secondsLeft: 0, isExpired: true}`
- **And** el componente MUST NO renderizar el countdown display (`secondsLeft === 0` se omite)
- **And** el componente MUST mostrar solo `<p role="alert">{t('lockout')}</p>` (texto estático fallback sin "N minutos")
- **And** el form MUST re-enabled inmediato (sin esperar).

---

### REQ-OPS-116 — `parkosFetch` pre-flight gate antes de POST críticos (DEC-F3.2-03 + DEC-F3.2-07 + DEC-FETCH-03 invariant)

**Source**: HU-F3.2 (`plan.md:1311` + `DEC-F3.2-03` regex path match + `DEC-F3.2-07` latency budget ≤200ms + `DEC-FETCH-03` Mutex preserved) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
La función `parkosFetchRaw(url, init)` MUST invocar `refreshIfExpiringSoon()` ANTES del `fetch` cuando se cumplen TODAS las condiciones: (1) `init.method === 'POST'`, (2) `url.match(PRE_FLIGHT_PATHS)` donde `PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/` (regex módulo-level, NO recompilar per request), (3) `useAuthStore.expiresAt !== null`, (4) `Date.parse(useAuthStore.expiresAt) - Date.now() < PRE_FLIGHT_THRESHOLD_MS` donde `PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000` (5min). La función `refreshIfExpiringSoon()` MUST invocar `useAuthStore.getState().refreshAccessToken()` (Mutex singleton F2.2 — `DEC-FETCH-03` invariant preserved) y NO retornar hasta que la promesa resuelva (success O failure). Si `refreshAccessToken()` falla, el request MUST continuar con el token existente (graceful degradation — `handle401` cubre 401 post-refresh). El pre-flight MUST NO triggerearse en GET requests (idempotentes, 401 retry cubre). El pre-flight MUST NO triggerearse en `POST /auth/login` (anónimo, `expiresAt === null` skip automático per R7 mitigation). Latency budget p95 MUST ser ≤200ms (DEC-F3.2-07 — soft target, no hard fail).

**Rationale**: Si el access_token expira JUSTO en el medio de un POST crítico (e.g., emisión de factura con payload >100KB que tarda >2s en serializar), el backend responde 401 → handle401 reactivo → refresh → retry. Esto causa race correctness donde el backend recibe el POST original (¿se procesa dos veces?) y el operador ve error transitorio. El pre-flight gate verifica `expiresAt` proactivamente y refresca ANTES de que el POST viaje, garantizando token fresco. El Mutex F2.2 preserva el invariant de single refresh incluso si 401 reactivo dispara concurrent.

**Source**: `apps/ui-kit/src/fetch/parkosFetch.ts` (MODIFY F3.2 T3 +20 LOC — `PRE_FLIGHT_PATHS` regex + `PRE_FLIGHT_THRESHOLD_MS` const + `refreshIfExpiringSoon()` internal function + integration en `parkosFetchRaw` antes del fetch); `apps/ui-kit/src/store/authStore.ts:71-128` (F2.2 READ ONLY — `setTokens` + `clear` + `refreshAccessToken` Mutex; F3.2 consume as-is); `apps/ui-kit/src/fetch/parkosFetch.ts:119-140` (F2.2 `handle401` Mutex — F3.2 invariant preserved); `apps/ui-kit/src/fetch/parkosFetch.test.ts` (MODIFY F3.2 T3 +60 LOC — U5 expiring soon triggers refresh, U6 not expiring skips refresh, U7 GET no triggerea, U8 refresh failure graceful degradation, U9 Mutex shared with 401 path); `backend/.../auth.py:21,71-72,279,285,297,306,343,348` (READ ONLY — `ACCESS_TOKEN_TTL = 3600`, `REFRESH_TOKEN_TTL = 7d`); R2 risk + R5 risk en `exploration.md §8`.

**Scenario 1: POST `/facturacion/*` con expiresAt < 5min → pre-flight triggerea refresh**
- **Given** `useAuthStore.expiresAt = new Date(Date.now() + 60_000).toISOString()` (60s, < 5min threshold)
- **And** el operador submita `POST /api/v1/facturacion/emision` con payload de factura
- **When** `parkosFetchRaw('/api/v1/facturacion/emision', { method: 'POST', body })` ejecuta
- **Then** ANTES del `fetch`, MUST invocar `refreshIfExpiringSoon()` → `await useAuthStore.getState().refreshAccessToken()`
- **And** el `POST /facturacion/emision` MUST viajar con el `Authorization: Bearer <nuevo_access>` header (post-refresh)
- **And** la request MUST NO recibir 401 (porque el token está fresco).

**Scenario 2: POST `/facturacion/*` con expiresAt > 5min → pre-flight SKIP**
- **Given** `useAuthStore.expiresAt = new Date(Date.now() + 600_000).toISOString()` (10min, > 5min threshold)
- **And** el operador submita `POST /api/v1/facturacion/emision`
- **When** `parkosFetchRaw` ejecuta
- **Then** `refreshIfExpiringSoon()` MUST retornar sin invocar `refreshAccessToken` (skip optimization)
- **And** el `POST` MUST viajar con el `Authorization: Bearer <access_vigente>` (no refresh necesario).

**Scenario 3: GET requests NO triggerean pre-flight (idempotentes)**
- **Given** `useAuthStore.expiresAt < 5min from now` (expira soon)
- **And** el operador carga `GET /api/v1/facturacion/ocupacion`
- **When** `parkosFetchRaw('/api/v1/facturacion/ocupacion', { method: 'GET' })` ejecuta
- **Then** el pre-flight MUST NO triggerearse (`method !== 'POST'`)
- **And** la GET MUST proceder normal; si el token expira durante la request, `handle401` cubre.

**Scenario 4: POST `/auth/login` anónimo → pre-flight skip (expiresAt null)**
- **Given** `useAuthStore.expiresAt === null` (estado pre-login)
- **And** el operador submita `POST /api/v1/auth/login` (anonymous, NO matchea `PRE_FLIGHT_PATHS`)
- **When** `parkosFetchRaw` ejecuta
- **Then** el pre-flight MUST NO triggerearse (path doesn't match — `/auth/login` not in regex; even if it did, `expiresAt === null` short-circuits)
- **And** `loginApi.postLogin` MUST usar `fetch` raw (DEC-F3.1-05 — pre-login NO usa parkosFetch).

**Scenario 5: Refresh failure durante pre-flight → graceful degradation**
- **Given** `expiresAt < 5min` y `useAuthStore.getState().refreshAccessToken` rechaza con error (backend 5xx)
- **When** `refreshIfExpiringSoon()` ejecuta
- **Then** el error MUST ser capturado (try/catch)
- **And** el `POST /facturacion` MUST continuar con el token existente (graceful degradation)
- **And** si el backend responde 401 post-refresh-failure, `handle401` cubre el retry-once.

**Scenario 6: Mutex shared entre pre-flight + 401 reactivo (no doble refresh)**
- **Given** un POST `/facturacion` está en pre-flight awaiting `refreshAccessToken`
- **When** concurrentemente, otra request recibe 401 y dispara `handle401` que también awaits `refreshAccessToken`
- **Then** ambas llamadas MUST compartir la MISMA promesa Mutex (F2.2 `DEC-FETCH-03`)
- **And** el backend MUST recibir UN solo `POST /auth/refresh` (no dos).

---

### REQ-OPS-117 — `useAuth.refreshInterval: 50min` alineado con `ACCESS_TOKEN_TTL = 3600` (DEC-F3.2-04 + DEC-SUC-03)

**Source**: HU-F3.2 (`plan.md:1311, 418` + `DEC-F3.2-04` constante exportada + `DEC-SUC-03` 50min verbatim) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El hook `useAuth()` (SWR) MUST setear `refreshInterval: REFRESH_INTERVAL_MS` donde `REFRESH_INTERVAL_MS = 50 * 60 * 1000` (3_000_000ms). La constante `REFRESH_INTERVAL_MS` MUST estar exportada desde `apps/ui-kit/src/hooks/useAuth.ts` para testabilidad determinista (vitest puede importarla y verificar el valor sin magic numbers). El JSDoc del hook MUST documentar el safety margin: `ACCESS_TOKEN_TTL (3600s) - REFRESH_INTERVAL_MS (3000s) = 600s = 10min` — si un refresh falla, el operador tiene 10min antes de 401 forzado. El SWR MUST disparar `parkosFetch('/auth/me')` cada 50 minutos para hidratar `useAuthStore` con `user`, `sucursal`, `permisos[]`, `expiresAt`. SWR's `refreshInterval` MUST coexistir con `revalidateOnFocus: true` (F2.2 baseline) — un focus event refetcha inmediato sin esperar el interval. `REFRESH_INTERVAL_MS` MUST NO ser configurable via UI (DEC-SUC-03 verbatim — hardcoded para kiosko desatendido; env var `PARKOS_REFRESH_INTERVAL_MS` es forward hook F3.x).

**Rationale**: F2.2 baseline (`refreshInterval: 5 * 60 * 1000` = 12 refreshes/hora) es 12x bandwidth waste vs `ACCESS_TOKEN_TTL = 3600` (1 refresh/hora es suficiente con safety margin). 50min deja 10min safety margin vs TTL — si un refresh falla, el operador tiene 10min para retry antes de que `expiresAt` expire y `useAuth()` emita `parkos:auth:cleared`. Constante exportada permite tests deterministas sin magic numbers.

**Source**: `apps/ui-kit/src/hooks/useAuth.ts` (MODIFY F3.2 T3 line 60 — `refreshInterval: 5 * 60 * 1000` → `REFRESH_INTERVAL_MS = 50 * 60 * 1000` + JSDoc update); `apps/ui-kit/src/hooks/useAuth.test.ts` (MODIFY F3.2 T3 +10 LOC — verify `REFRESH_INTERVAL_MS = 50 * 60 * 1000`); `apps/ui-kit/src/fetch/parkosFetch.ts:92-96` (F2.2 READ ONLY — `Authorization: Bearer` injection automático, refresh NO toca este path); `plan.md:418` (DEC-SUC-03 verbatim "Refresh transparente cada 50 minutos y antes de escrituras críticas"); R3 risk en `exploration.md §8` (SWR refresh coincide con active request — SWR mutation isolation + non-blocking, NO conflicto).

**Scenario 1: `useAuth()` se monta → SWR configura refreshInterval 50min**
- **Given** el operador está autenticado con `accessToken !== null` post-login
- **When** el componente destino (e.g., `<LoginPage>` redirect a `/`) monta `<Routes>` que consumen `useAuth()`
- **Then** SWR MUST configurar `refreshInterval: 50 * 60 * 1000`
- **And** SWR MUST disparar el primer `parkosFetch('/auth/me')` inmediatamente (key change)
- **And** tras 50min, SWR MUST disparar el siguiente `parkosFetch('/auth/me')` (refresh automático).

**Scenario 2: Constante `REFRESH_INTERVAL_MS` exportada y testeable**
- **Given** `useAuth.test.ts` importa `REFRESH_INTERVAL_MS` desde `apps/ui-kit/src/hooks/useAuth.ts`
- **When** el test ejecuta `expect(REFRESH_INTERVAL_MS).toBe(50 * 60 * 1000)`
- **Then** el assertion MUST pasar (50 * 60 * 1000 = 3_000_000ms exact)
- **And** el test MUST NO usar magic numbers (cero `expect(refreshInterval).toBe(3_000_000)` hardcoded).

**Scenario 3: Safety margin 10min — refresh falla + operador tiene 10min antes de 401**
- **Given** `accessToken` emitió a T0 con `expiresAt = T0 + 3600s`
- **And** SWR refresh scheduled at T0 + 3000s (50min)
- **When** el refresh a T0 + 3000s falla (backend 5xx transitorio)
- **Then** el operador puede continuar usando el `accessToken` hasta T0 + 3600s (TTL expiration)
- **And** entre T0 + 3000s y T0 + 3600s hay 600s = 10min de safety margin
- **And** el próximo SWR refresh scheduled at T0 + 6000s (100min) puede recuperar la sesión.

**Scenario 4: SWR refresh coincide con active request POST — NO conflicto**
- **Given** SWR tiene un refresh scheduled a T+50min
- **And** a T+50min, el operador submita `POST /facturacion/emision` concurrentemente
- **When** ambos requests ejecutan en paralelo
- **Then** SWR MUST ejecutar `parkosFetch('/auth/me')` con el MISMO `accessToken` (read at request start)
- **And** el `POST /facturacion` MUST ejecutar con el MISMO `accessToken`
- **And** MUST NO haber interference (SWR mutation isolation + non-blocking fetch).

---

### REQ-OPS-118 — WCAG 2.1 AA compliance via axe-core 0 violaciones en `<LoginForm>` durante lockout state (DEC-F3.2-05)

**Source**: HU-F3.2 (`plan.md:1315` + `DEC-F3.2-05` axe-core countdown state + `RNF-022` WCAG 2.1 AA + REQ-OPS-112 F3.1 precedent) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<LoginForm>` MUST pasar el scan `axe-core` (vía `@axe-core/playwright` extension) con 0 violaciones de WCAG 2.1 AA durante lockout state (countdown activo). Cobertura mandatory: (1) `<p role="status" aria-live="polite" data-testid="login-countdown">` con `aria-label` descriptivo (`t('lockoutLabel')`); (2) `<Input>` + `<Button>` con `aria-disabled="true"` durante lockout; (3) `<p role="alert">{t('lockout')}</p>` (mensaje estático F3.1) — countdown display NO debe duplicar role=alert (R6 risk — interruptivo); (4) tab order secuencial preservado durante lockout (foco pasa por inputs disabled pero el orden es consistente); (5) contraste de color mínimo 4.5:1 entre countdown display foreground y background (CSS tokens de `apps/ui-kit/src/tokens.ts` — F2.1 baseline); (6) NO errores de axe-core sobre `aria-live="polite"` mal usado (el `<p>` debe tener contenido textual). El e2e test `apps/electron-sucursal/e2e/auth/lockout.spec.ts` MUST incluir un test `axe-core scan on /login during lockout state` que ejecute el analyzer post-render del countdown (E1 mockea 429 + Retry-After → countdown visible → A1 ejecuta axe-core).

**Rationale**: RNF-022 (`docs/01-requisitos/no-funcionales.md:126`) exige WCAG 2.1 AA compliance para todas las pantallas transaccionales. F3.1 sentó el patrón a11y para LoginForm (REQ-OPS-112, axe-core 0 violaciones en estado normal). F3.2 extiende al lockout state — el countdown display + form disabled deben pasar el scan con 0 violaciones. Si axe-core reporta violaciones, el kiosko desatendido pierde la cobertura a11y que el operador en piso necesita.

**Source**: `apps/electron-sucursal/package.json:55-56` (`@playwright/test@^1.48.0` + `@axe-core/playwright@^4.10.0` — F2.1 baseline); `docs/01-requisitos/no-funcionales.md:126` (RNF-022 anchor); `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` (F2.1 axe-core pattern precedent — F3.2 replica el patrón en `e2e/auth/lockout.spec.ts`); REQ-OPS-112 F3.1 (precedent verbatim pattern); R6 risk en `exploration.md §8`.

**Scenario 1: axe-core scan durante countdown state — 0 violaciones**
- **Given** el operador accede a `/login` y la e2e mockea un 429 con `Retry-After: 600` (10min)
- **And** `<LoginForm>` renderiza el countdown display `<p role="status" aria-live="polite" data-testid="login-countdown" aria-label="Tiempo restante para reintentar: 10:00">{t('lockoutCountdown', {time: '10:00'})}</p>`
- **And** los inputs + submit están `disabled={true}` + `aria-disabled="true"`
- **When** `e2e/auth/lockout.spec.ts::test_axe_core_lockout` ejecuta `new AxeBuilder({page}).analyze()` con tags `wcag2a, wcag2aa, wcag21a, wcag21aa`
- **Then** el array `result.violations` MUST estar vacío (length === 0)
- **And** el test MUST pasar verde (no skip en CI).

**Scenario 2: axe-core scan post auto re-enable — 0 violaciones**
- **Given** el countdown llegó a 0 (`isExpired === true`) y el form re-enabled
- **And** `<LoginForm>` ya no muestra countdown (cleanup state local)
- **When** `e2e/auth/lockout.spec.ts::test_axe_core_re_enable` ejecuta axe-core scan
- **Then** el array `result.violations` MUST estar vacío
- **And** el form MUST pasar WCAG 2.1 AA en estado normal (sin countdown — REQ-OPS-112 F3.1 regression check).

**Scenario 3: `role="status"` + `aria-live="polite"` semánticamente correctos**
- **Given** el countdown display renderiza con `role="status" aria-live="polite"`
- **When** axe-core valida el patrón (rules `aria-roles`, `aria-valid-attr-value`)
- **Then** MUST haber 0 violaciones sobre los atributos ARIA
- **And** el `<p>` MUST contener contenido textual (`{t('lockoutCountdown', {time: formatTime(secondsLeft)})}`) — axe-core rechaza `aria-live` regions vacías.

---

## 4. Cross-reference table

| REQ-OPS | DEC-F3.2 anchor | Plan.md line | Precedent directo |
|---|---|---|---|
| REQ-OPS-113 | DEC-F3.2-01 | 1311 | F2.2 DEC-FETCH-04 (useAuth SWR refreshInterval precedent — F3.2 entrega hook reusable nuevo) |
| REQ-OPS-114 | DEC-F3.2-02, DEC-F3.2-05, DEC-F3.2-06 | 1309, 1315 | F3.1 REQ-OPS-109 (lockout estático F3.1 — F3.2 reemplaza por countdown dinámico) |
| REQ-OPS-115 | DEC-F3.2-02, DEC-F3.2-06 | 1315 | F3.1 REQ-OPS-111 (transaccional state reset precedent — F3.2 replica pattern) |
| REQ-OPS-116 | DEC-F3.2-03, DEC-F3.2-07 | 1311 | F2.2 DEC-FETCH-03 (Mutex refreshAccessToken — F3.2 invariant preserved) + F2.2 handle401 (F3.2 layer retry-budget proactiva sobre reactiva) |
| REQ-OPS-117 | DEC-F3.2-04, DEC-SUC-03 | 418, 1311 | F2.2 useAuth.ts:60 (refreshInterval baseline 5min — F3.2 cambia a 50min) |
| REQ-OPS-118 | DEC-F3.2-05, RNF-022 | 1315 | F3.1 REQ-OPS-112 (axe-core LoginForm precedent — F3.2 extiende a lockout state) |

**Nota**: F3.2 NO crea un nuevo REQ-OPS-XR (cross-cutting requirement). Las 6 new REQ-OPS-113..118 son SPECIFIC al lockout countdown + refresh lifecycle. REQ-OPS-XR6 de F1.13 (5-layer defense in depth) sigue siendo el canonical cross-cutting contract; F3.2 contribuye a las capas a11y (countdown WCAG) + retry-budget (pre-flight) sin formalizar un XR7 (precedent F1.15 `DEC-XR7 NOT-CREATED` en `operations/spec.md:4386` + F3.1 NO crea XR en spec).

---

## 5. Acceptance criteria for sdd-verify

| # | Criterion | Test source | Type |
|---|---|---|---|
| AC-1 | `useCountdown(retryAfterSeconds, options?)` retorna `{secondsLeft, isExpired}` con `Date.now()` baseline + setInterval(1000) + cleanup + onComplete callback (REQ-OPS-113) | `useCountdown.test.ts` (T1, ~50 LOC, 4 tests: U1 baseline Date.now, U2 cleanup on unmount, U3 onComplete fires at 0, U4 drift resistance via fake timers) | Unit (vitest + @testing-library/react) |
| AC-2 | `<LoginForm>` aplica `disabled={true}` + `aria-disabled="true"` durante lockout + renderiza `<p role="status" aria-live="polite" data-testid="login-countdown">` con countdown mm:ss (REQ-OPS-114) | `LoginForm.test.tsx` (T2, +25 LOC, 2 tests: U8 lockout disables form, U9 countdown decrements) | Unit (vitest + @testing-library/react) |
| AC-3 | `formatTime(secondsLeft)` helper retorna mm:ss con zero-padding para 0..5999 (REQ-OPS-114 Scenario 4) | `LoginForm.test.tsx` (T2, embedded unit test) | Unit (vitest) |
| AC-4 | `<Login>` container resetea `errorState` a null cuando `useCountdown().isExpired === true` + foco automático al primer input + notice `lockoutReEnable` visible 3s (REQ-OPS-115) | `Login.test.tsx` (T2, +15 LOC, U10 isExpired resets errorState) | Unit (vitest + @testing-library/react) |
| AC-5 | `parkosFetch` pre-flight gate `refreshIfExpiringSoon()` triggerea refresh antes de POST `/facturacion/*` + `/caja/arqueo*` cuando `expiresAt - now < 5min` (REQ-OPS-116) | `parkosFetch.test.ts` (T3, +60 LOC, 5 tests: U5 expiring soon triggers refresh, U6 not expiring skips refresh, U7 GET no triggerea, U8 refresh failure graceful degradation, U9 Mutex shared with 401 path) | Unit (vitest + MSW) |
| AC-6 | `useAuth.refreshInterval === REFRESH_INTERVAL_MS = 50 * 60 * 1000` constante exportada (REQ-OPS-117) | `useAuth.test.ts` (T3, +10 LOC — verify `REFRESH_INTERVAL_MS` constant + JSDoc) | Unit (vitest) |
| AC-7 | axe-core 0 violaciones WCAG 2.1 AA en `<LoginForm>` durante lockout state (REQ-OPS-118) | `lockout.spec.ts::test_axe_core_lockout` (T4, embedded) | E2E (playwright + axe-core) |
| AC-8 | 4 e2e scenarios verde (countdown display + decrement + re-enable + axe-core) | `e2e/auth/lockout.spec.ts` (T4, ~80 LOC — E1 4 intentos → 429 + countdown visible, E2 countdown decrementa, E3 form re-enable al 0, A1 axe-core WCAG 2.1 AA) | E2E (playwright _electron) |
| AC-9 | (transversal) i18n `auth.json` agrega 3 keys (`lockoutCountdown`, `lockoutReEnable`, `lockoutLabel`) | snapshot test del JSON (T2) | Unit (vitest snapshot) |

**Sandbox F.6 caveat**: AC-8 puede SKIP en sandbox F.6 (npm 11.16.0 refuses `workspace:*` resolution — F2.1 + F2.2 + F2.3 + F3.1 archive precedent G8). Unit tests AC-1..AC-6 + AC-9 + AC-7 axe-core source-level SÍ corren. Documentado como deviation D-env en `verify-report.md`, NO project defect.

---

## 6. Forward hooks (Fase 3+ consumer map)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.3** (Abrir/Cerrar turno) | pre-flight gate automático para `POST /caja-sesion/*` si F3.3 decide agregar al path match (forward — no obligatorio) | DEC-F3.2-10: extender `PRE_FLIGHT_PATHS` regex para incluir `/caja-sesion/*` via constante módulo-level `PRE_FLIGHT_PATHS_EXTENDED` o env var |
| **HU-F3.3** | `useAuth().user.sucursal` + `permisos[]` hidratados post-F3.1 (F3.2 NO toca `useAuth` shape) | F3.3 consume via SWR data — refresh 50min aplica transparentemente |
| **HU-F3.x** (logout button UI) | `useAuthStore.clear()` ya implementado en F2.2 + `parkos:auth:cleared` window event | F3.3+ logout button dispatch `clear()` + `navigate('/login')` |
| **HU-F3.x** (AuthGuard component) | `parkos:auth:cleared` window event | F3.3+ `<AuthGuard>` envuelve `<Routes>` excepto `/login` → `navigate('/login?next=...')` |
| **HU-F4.x** (catálogos + ocupación) | `useCountdown` para retry buttons con countdown visual | F4.x export `useRetryWithCountdown` pattern que envuelve `useCountdown` con retry-exponential-backoff |
| **HU-F4.x** | `parkosFetch` pre-flight gate — F4.x hereda automáticamente (T3 cubre `/facturacion/*`) | Cero cambios F4.x |
| **HU-F5.x** (facturación) | pre-flight gate automático (`/facturacion/*` ya cubierto) + `useAuth.refreshInterval: 50min` | Cero cambios F5.x |
| **HU-F5.x** | `useCountdown` para retry buttons post-409 conflicto | F5.x export `useRetryWithCountdown` |
| **HU-F11.x** (sync UI + alertas CU-07/14) | `useCountdown` para reintentos de sync con countdown visual + exponential backoff | F11.x export `useSyncRetryCountdown` que envuelve `useCountdown` |
| **HU-F11.x** | `useAuth` 50min refresh — F11.x hereda automáticamente | Cero cambios F11.x |
| **PR7 backend** (refresh-token rotation) | `refreshAccessToken` Mutex F2.2 + pre-flight F3.2 → rotación con `jti` reuse detection | PR7 backend: detectar reuse de `jti` claim y revocar cadena. F3.2 ya provee Mutex infrastructure + pre-flight gate ready para integrar rotation. |

---

## 7. Out of scope (verbatim de `exploration.md §17`)

F3.2 NO incluye (explícitamente deferido a Fase 3+):

- **Backend cambios**: `configuracion_seguridad.max_intentos_login` ya shipped Fase 1 (HU-F1.2); F3.2 consume via `parseRetryAfter`. NO modifica backend.
- **Refresh-token rotation**: PR7 backend. F3.2 consume Mutex F2.2 sin modification.
- **AuthGuard component**: F3.3+ (intercept `parkos:auth:cleared` → `navigate('/login?next=...')`).
- **Logout button UI**: F3.3+ placeholder.
- **Recuperación de password / forgotPassword**: fuera Fase 3 (futuro).
- **2FA / WebAuthn / biometric**: fuera Fase 3 (futuro).
- **Multi-tab login UI**: kiosko single-tab per F2.3 `requestSingleInstanceLock` (DEC-UPD-07).
- **Turno abrir/cerrar**: F3.3 (`AbrirTurno` + `CerrarTurno` + `useSesionActiva` en `features/caja/`).
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

---

## 8. DoD checklist

- [ ] 6 REQ-OPS-113..118 materializadas en `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md` (este archivo)
- [ ] Given/When/Then/And format RFC 2119 per F3.1 + F1.15 precedent verbatim
- [ ] Anchor links explícitos a `DEC-F3.2-NN` ratificados en `proposal.md §4` + `exploration.md §7`
- [ ] Cross-reference table completa (§4) — 6 rows con precedent column
- [ ] Acceptance criteria verificables para `sdd-verify` (§5) — 9 criterios
- [ ] Forward hooks documentados para F3.3, F4.x, F5.x, F11.x, PR7 backend (§6) — 11 hooks
- [ ] Out of scope verbatim de `exploration.md §17` (§7)
- [ ] NO-OP stub NO aplicado — DELTA stub con 6 new REQ-OPS confirmado (per `DEC-F3.2-08` + `DEC-F3.2-11`)
- [ ] Numeración monotónica verificada (REQ-OPS-112 vigente post-F3.1; F3.2 ocupa REQ-OPS-113..118)
- [ ] Spanish neutro profesional per F1.15 + F3.1 precedent + global contract
- [ ] Author: `Parkos Dev <dev@parkos.local>` (F2.1 + F3.1 verbatim precedent)
- [ ] No "Co-authored-by" attribution per `CLAUDE.md` global rules
- [ ] RFC 2119 MUST/SHOULD/MAY keywords consistentes en las 6 REQ-OPS

---

## CHANGELOG

- **(2026-09-15)** F3.2 spec delta complete — 6 REQ-OPS-113..118 materializadas en Given/When/Then/And format RFC 2119. DELTA stub (NOT NO-OP) per critical re-evaluación en `proposal.md §4.11` (DEC-F3.2-11). F3.2 ES user-facing behavior observable: countdown visual decreciente cada 1000ms + form disabled durante lockout + pre-flight gate evita 401 mid-write en `/facturacion/*` + `/caja/arqueo/*` + refresh 50min automático contra `ACCESS_TOKEN_TTL = 3600` (10min safety margin) + Mutex `refreshAccessToken` F2.2 preserved + WCAG 2.1 AA countdown (extiende REQ-OPS-112 F3.1). Precedente directo: F3.1 archivado 2026-09-15 con 7 new REQ-OPS-106..112 + F1.15 archivado 2026-09-15 con 4 new REQ-OPS-102..105. Numeración monotónica: REQ-OPS-112 vigente post-F3.1; F3.2 ocupa REQ-OPS-113..118 (continuación, 0 gaps). Ready for `sdd-design` (parallel) + `sdd-tasks`.

---

**End of delta spec — HU-F3.2.**