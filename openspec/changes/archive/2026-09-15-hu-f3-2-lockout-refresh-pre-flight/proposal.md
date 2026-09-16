# Proposal — HU-F3.2 Lockout visible (countdown) + refresh transparente (50min auto + pre-flight)

> **Change**: `hu-f3-2-lockout-refresh-pre-flight` · **Folder**: `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` (paralelo)
> **HU ID**: HU-F3.2 (Fase 3 — segunda HU; Autenticación y turno de caja, hardening UX + lifecycle del `access_token`)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `bcfe2ed`, F3.1 archivado 2026-09-15 con 7 REQ-OPS-106..112; F3.2 se commitea sobre la misma rama hasta migrar a `feat/fase-3-auth-turno` per `pending.md:6`) · **PR target**: `origin/dev`
> **Inputs**: `plan.md` lines 1307-1324 (HU-F3.2 verbatim, 130 LOC, 4 tareas atómicas T1..T4); `plan.md:418` (DEC-SUC-03 — "Refresh transparente cada 50 minutos y antes de escrituras críticas (pago, arqueo)"); `plan.md:1274-1305` (HU-F3.1 archivado — precedentes + `AccountLockedError` + `LoginErrorState` + cookie httpOnly); `pending.md §1` (F3.1 ✅ cerrado 2026-09-15; F3.2 row 2 con budget 130 LOC); `pending.md §5` (forward hooks F4/F5/F11/F3.3); `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/exploration.md` (~580 LOC, 18 secciones, 10 DEC-F3.2-01..10, 8 riesgos R1..R8, 6 acceptance gates G1..G6, 4 atomic tasks T1..T4, 1 cluster C1, pre-flight 10/10 PASS + 0 KNOWN-MISSING); `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/{exploration.md,proposal.md,specs/operations/spec.md,tasks.md,verify-report.md,archive-report.md}` (precedente verbatim 18 secciones + 7 REQ-OPS-106..112 user-facing DELTA — F3.2 replica el precedent con 6 REQ-OPS-113..118); `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/{exploration.md,proposal.md,tasks.md}` (precedente refresh-once Mutex DEC-FETCH-03 + `refreshInterval` baseline 5min — F3.2 cambia a 50min); `apps/electron-sucursal/src/features/auth/{api/loginApi.ts:1-93 (AccountLockedError.retryAfterSeconds + parseRetryAfter), api/loginSchema.ts, api/loginApi.test.ts:1-138, components/LoginForm.tsx:1-133 (LoginErrorState kind:'lockout' + countdown display 120-124), pages/Login.tsx:1-81 (container con errorState wiring), pages/Login.test.tsx, components/LoginForm.test.tsx}`; `apps/ui-kit/src/{fetch/parkosFetch.ts:1-212 (refresh-once 401 via handle401 + Mutex singleton + isLoginEndpoint skip), store/authStore.ts:1-129 (setTokens + clear + refreshAccessToken Mutex + expiresAt ISO 8601), hooks/useAuth.ts:1-87 (SWR refreshInterval 5*60*1000 — F3.2 CAMBIO a 50min + REFRESH_INTERVAL_MS export), hooks/useAuth.test.ts}`; `apps/electron-sucursal/src/renderer/{App.tsx:1-41 (/login route wired), i18n/locales/{auth,common,errors,operacion,caja,facturacion,sync}.json}`; `apps/electron-sucursal/e2e/{auth/login.spec.ts:1-105 (4 tests: E1 cookie, E2 refresh, E3 logout, A1 axe-core), a11y/wcag-2.1-aa.spec.ts (axe-core pattern precedent), auth/parkos-fetch.spec.ts (MSW pattern precedent), scaffold.spec.ts}`; `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:21,71-72,279,285,297,306,343,348 (ACCESS_TOKEN_TTL=3600, REFRESH_TOKEN_TTL=7d, Retry-After header line 219-228)`; `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` (LoginRequest + TokenPair); `modelo_datos_er.mmd:270-289 (configuracion_seguridad.max_intentos_login + minutos_bloqueo_login)`; `modelo_datos_er.mmd:558-573 (prod.login [L-S])`; `docs/01-requisitos/no-funcionales.md:126 (RNF-022 WCAG 2.1 AA)`.

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F3.2 |
| **Fase** | 3 (Autenticación y turno de caja — segunda HU) |
| **Change name** | `hu-f3-2-lockout-refresh-pre-flight` |
| **Folder** | `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/` |
| **State** | proposed (ready for design + spec) |
| **Branch** | `feat/fase-2-electron-scaffold` |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | F3.1 archivado 2026-09-15 (Login email+password, 4 commits `8961303..5fcfe66`, 7 REQ-OPS-106..112 user-facing DELTA — primer DELTA en Fase 3 rompiendo precedent F2.x NO-OP) |
| **Próximo phase** | sdd-spec + sdd-design (paralelo) |
| **Language** | español neutro profesional |
| **Conventional commits** | `feat(auth)` / `feat(refresh)` / `test(electron)` — sin Co-authored-by |
| **DEC-F3.2-11 verdict** | **DELTA** (NOT NO-OP) — F3.2 ES user-facing behavior observable: countdown visual + form disabled + pre-flight gate + 50min refresh |

---

## 1. Resumen ejecutivo

**Title**: "Lockout visible con countdown decreciente (`useCountdown` hook + `setInterval(1000)` + cleanup) + refresh transparente 50min auto (cambio `useAuth.refreshInterval: 5*60*1000 → 50*60*1000`) + refresh pre-flight antes de POST `/facturacion/*` y POST `/caja/arqueo` (gate `await refreshIfExpiringSoon()` con Mutex singleton) + e2e lockout scenario (4-5 intentos fallidos → 429 → countdown display → auto re-enable al llegar a 0)".

**Goal — el problema que F3.2 cierra**: F3.1 archivado deja el flujo login + cookie httpOnly + hidratación transaccional + WCAG 2.1 AA completos y verificados (5/7 gates source-level PASS + 2/7 SKIPPED-env F.6 precedent). Sin embargo, dos gaps UX críticos rompen la promesa "kiosko desatendido, operador desatendido, sesión robusta" del `plan.md:418` (DEC-SUC-03): (a) cuando `loginApi.postLogin` recibe 429 con `Retry-After: 600`, F3.1 surfacea un texto estático "Cuenta bloqueada temporalmente." sin countdown — el operador no sabe cuánto falta y vuelve a fallar inmediatamente al reintentarlo (F3.1 REQ-OPS-109 explícitamente deferió el countdown UI a F3.2); (b) el `refreshInterval: 5*60*1000` de F2.2 (`useAuth.ts:60`) es 12x por hora contra un `ACCESS_TOKEN_TTL = 3600` — refresca 12 veces por hora cuando una vez cada 50min deja un safety margin de 10min antes del TTL; (c) falta un pre-flight gate que evite 401 mid-write en POST críticos de `/facturacion/*` y `/caja/arqueo` (el `handle401` reactivo de F2.2 cubre el caso pero el operador experimenta una latencia visible y el backend recibe el POST original — race correctness).

**Goal — la solución propuesta**: F3.2 entrega cuatro deliverables end-to-end verificables: (1) `useCountdown(retryAfterSeconds)` hook reusable con `Date.now()` baseline (no accumulator — drift-resistant), `setInterval(1000)` + cleanup en unmount + `onComplete` callback; (2) `LoginForm` consume `useCountdown` cuando `error.kind === 'lockout'`, renderiza `<p role="status" aria-live="polite" data-testid="login-countdown">{formatTime(secondsLeft)}</p>` y aplica `disabled={true}` a inputs + submit mientras `secondsLeft > 0`, con auto re-enable al llegar a 0; (3) `useAuth.refreshInterval` cambia a `REFRESH_INTERVAL_MS = 50 * 60 * 1000` con constante exportada para testabilidad; (4) `parkosFetch.ts` agrega `refreshIfExpiringSoon()` antes de POST matcheando `PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/` cuando `expiresAt - now < PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000`, reusando el Mutex `refreshAccessToken` de F2.2 (zero doble refresh). El escenario e2e `apps/electron-sucursal/e2e/auth/lockout.spec.ts` cubre 4 casos (countdown display + decrement + re-enable + axe-core A1).

**Impacto transversal — por qué importa a Fase 4+**: F3.2 cierra los gaps de lifecycle del `access_token` que F3.1 dejó abiertos. Tres factores elevan su criticidad: (1) kiosko desatendido + operador en piso — `plan.md:418` (DEC-SUC-03) exige kiosko robusto, sin intervención IT; si el operador se lockea sin ver countdown, no sabe si esperar o pedir ayuda; si un POST crítico falla por 401 mid-write, pierde la venta; (2) defense in depth XR6 (`operations/spec.md:3951`) requiere retry-budget robusto — F2.2 sentó las bases (Mutex + refresh-once), F3.2 lo completa con pre-flight gate que evita el retry reactivo; (3) forward consumer para Fase 4+ — F4.x (catálogos) + F5.x (facturación) + F11.x (sync UI) consumen `parkosFetch` con POST mutacionales críticos; sin pre-flight, todos heredan el riesgo de 401 mid-write; F3.2 blinda la infraestructura transversal para que las HU downstream sean trabajo de UI, no de infra. Adicionalmente, `useCountdown` se reusa en F4.x retry buttons y F11.x reintentos de sync con countdown visual — primer hook genuinely reusable del feature `auth`.

**Hard constraints** (mirrored from `plan.md:1311` verbatim + DEC-SUC-03):

- Trigger 429 con `Retry-After` → form `disabled={true}` + countdown display `useCountdown(retryAfterSeconds)` `{secondsLeft, isExpired}`.
- Refresh automático cada 50min (`refreshInterval: 50 * 60 * 1000` en `useAuth()` SWR, configurable via constante exportada).
- Pre-flight refresh antes de `POST /facturacion/*` + `POST /caja/arqueo` si `access_token` expira en <5min.
- `useCountdown(retryAfter)` hook reusable (forward consumer F4.x/F5.x/F11.x).
- Tamaño: 130 LOC production + tests + configs.
- 4 tareas atómicas T1..T4.
- e2e: `e2e/auth/lockout.spec.ts` — 4-5 intentos fallidos → 429 + countdown visible y decreciente.
- WCAG 2.1 AA compliance: axe-core 0 violaciones durante countdown state (RNF-022).

**Scope**: ~130 LOC production + ~240 LOC tests + configs = ~370 LOC total. Plan 130 LOC matches: 110 production authored + 20 JSDoc/configs.

**Numeración REQ-OPS verificada**: el último REQ-OPS vigente en `operations/spec.md` es REQ-OPS-112 (F3.1 archivado 2026-09-15, línea 4626). F3.2 ocupa **REQ-OPS-113..118** (6 new requirements, continuación monotónica). Numeración monotónica verificada: 112 → 113 → 114 → 115 → 116 → 117 → 118 (0 gaps, sin duplicados).

**Por qué importa a nivel spec (re-evaluación crítica desde exploration §12)**: a diferencia de F2.1/F2.2/F2.3 (infra-only, NO-OP stub per DEC-ELEC-10 / DEC-FETCH-10 / DEC-UPD-13), F3.2 ES user-facing behavior observable — cuatro dimensiones: (a) countdown visual decreciente cada 1000ms (clock visible al operador); (b) form disabled durante lockout (interacción observable); (c) pre-flight gate evita 401 mid-write en `/facturacion/*` + `/caja/arqueo/*` (latency + correctness observable); (d) refresh 50min automático (session longevity observable). Esta behavior visible al usuario NO puede vivir solo en DEC-F3.2-NN dentro de `proposal.md` — debe anclarse en REQ-OPS-NNN dentro del spec canónico `operations/spec.md` para que sea verificable, auditable y refactorizable. Precedent directo: F1.15 (login histórico, archivado 2026-09-15) emitió 4 new REQ-OPS-102..105 user-facing; F3.1 emitió 7 new REQ-OPS-106..112 user-facing; F3.2 emite 6 new REQ-OPS-113..118 user-facing — sigue el precedent DELTA y **rompe** el precedent NO-OP de F2.x. Ver `DEC-F3.2-08` y `DEC-F3.2-11` en §4 para el rationale completo.

---

## 2. Contexto y motivación

### 2.1 Pain points UX que F3.2 cierra

Tres user-facing pain points rompen la promesa "kiosko desatendido" del `plan.md:418` (DEC-SUC-03). F3.2 mitiga los tres.

**Pain #1 — 429 sin countdown es hostil UX**: cuando `loginApi.postLogin` recibe 429 con `Retry-After: 600` (10min, configurado por `configuracion_seguridad.minutos_bloqueo_login` per-branch, default 10min per `auth.py:225`), F3.1 surfacea `<p role="alert">{t('lockout')}</p>` como texto estático "Cuenta bloqueada temporalmente." (`LoginForm.tsx:120-124`). El operador NO sabe cuánto falta — el form queda habilitado y vuelve a fallar inmediatamente al reintentarlo. Kiosko desatendido = operador frustrado que abandona el terminal esperando IT. F3.2 entrega `useCountdown(retryAfterSeconds)` con `setInterval(1000)` que decrementa `secondsLeft` cada tick, `disabled` automático del form mientras `secondsLeft > 0`, y auto re-enable al llegar a 0. Display `<p role="status" aria-live="polite" data-testid="login-countdown">{formatTime(secondsLeft)}</p>` para WCAG 2.1 AA (RNF-022).

**Pain #2 — Refresh 5min (F2.2 baseline) es subóptimo vs `access_token` TTL 1h**: `useAuth.ts:60` setea `refreshInterval: 5 * 60 * 1000` per `plan.md:1208` (F2.2 verbatim, `DEC-FETCH-04`). Pero `ACCESS_TOKEN_TTL = 3600` en `backend/.../auth.py:71` significa que el access_token vive 1h. Refrescar cada 5min es 12x por hora = desperdicio de bandwidth + latencia SWR innecesaria + log noise (cada refresh genera un GET `/auth/me` con JWT bearer round-trip). F3.2 cambia el interval a **50min** (`50 * 60 * 1000 = 3_000_000`) per `DEC-SUC-03` (plan.md:418 verbatim). 50min deja un safety margin de 10min vs TTL — si un refresh falla, el operador tiene 10min antes de que `expiresAt` expire y `useAuth()` emita `parkos:auth:cleared`.

**Pain #3 — Pre-flight gate faltante causa 401 mid-write**: `parkosFetch.ts:119-140` (`handle401`) ya implementa refresh-once via Mutex cuando el backend responde 401 (F2.2 `DEC-FETCH-03` invariant). PERO: si el operador está en `/facturacion` y submita un POST crítico (e.g., emisión de factura con payload >100KB que tarda >2s en serializar), el access_token puede expirar JUSTO en el medio del request → 401 → refresh → retry. Esto causa una race donde el backend recibe el POST original (¿se procesa dos veces?), el operador ve un error confuso, y el state local queda inconsistente. F3.2 agrega un **pre-flight gate** en `parkosFetch.ts` que, ANTES de `POST /facturacion/*` + `POST /caja/arqueo`, verifica `useAuthStore.expiresAt` — si faltan <5min para expirar, dispara `refreshAccessToken()` proactively via Mutex. El request crítico viaja con token fresco.

### 2.2 Rationale — defense in depth + forward consumer

**Defense in depth XR6** (`operations/spec.md:3951`): el patrón de 5 capas (auth + engineering + a11y + contract + retry-budget) requiere retry-budget robusto. F2.2 sentó las bases (Mutex + refresh-once); F3.2 lo completa con pre-flight gate que evita el retry reactivo. La capa retry-budget ahora tiene dos líneas de defensa: proactiva (pre-flight F3.2) + reactiva (handle401 F2.2).

**Forward consumer para Fase 4+** (forward hooks `pending.md §5`): F4.x (catálogos) + F5.x (facturación) + F11.x (sync UI) consumen `parkosFetch` con POST mutacionales críticos. Sin pre-flight, todos heredan el riesgo de 401 mid-write. F3.2 blinda la infraestructura transversal para que las HU downstream sean trabajo de UI, no de infra. Adicionalmente, `useCountdown` se reusa en F4.x retry buttons (`useRetryWithCountdown` pattern) y F11.x reintentos de sync con countdown visual — primer hook genuinely reusable del feature `auth` para consumo cross-feature.

**Kiosko desatendido + operador en piso**: el plan enfatiza "operador desatendido, kiosko robusto, sin intervención IT". Si el operador se lockea y NO ve countdown, no sabe si esperar o pedir ayuda. Si el refresh no es transparente, pierde el turno. Si un POST crítico falla por 401 mid-write, pierde la venta. F3.2 mitiga los tres riesgos UX con deliverables verificables end-to-end.

---

## 3. Goals y no-goals

### 3.1 Goals (QUÉ entrega F3.2)

1. **Countdown visible decreciente** — `useCountdown(retryAfterSeconds)` con `Date.now()` baseline + `setInterval(1000)` + cleanup en unmount + `onComplete` callback; renderizado como `<p role="status" aria-live="polite">` en `LoginForm` durante lockout state.
2. **50min SWR refresh** — `useAuth.refreshInterval: 50 * 60 * 1000` (constante `REFRESH_INTERVAL_MS` exportada); 10min safety margin vs `ACCESS_TOKEN_TTL = 3600`.
3. **Pre-flight gate antes de POST críticos** — `refreshIfExpiringSoon()` invocado ANTES de `POST /facturacion/*` + `POST /caja/arqueo` cuando `expiresAt - now < 5min`, reusando el Mutex `refreshAccessToken` de F2.2.
4. **axe-core WCAG 2.1 AA** durante countdown state — countdown display `<p role="status" aria-live="polite">` compliant con `role="status"` + `aria-label` descriptivo; e2e A1 test verifica 0 violaciones con `withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])`.
5. **130 LOC budget** — production ~110 LOC authored + 20 JSDoc/configs ≈ 130 LOC.
6. **4 atomic tasks T1..T4** — `T1 useCountdown hook standalone` → `(T2 LoginForm countdown integration) || (T3 parkosFetch pre-flight + useAuth 50min)` → `T4 e2e lockout scenario`. T2 y T3 pueden ejecutarse en paralelo.
7. **6 new REQ-OPS-113..118** materializadas al canonical `operations/spec.md` en formato Given/When/Then/And RFC 2119 (DEC-F3.2-08 DELTA precedent F3.1).
8. **3 countdown i18n keys** — `lockoutCountdown` + `lockoutReEnable` + `lockoutLabel` agregadas a `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (namespace existente, NO requiere nuevo namespace).
9. **Anti-patterns avoided** — NO accumulator (Date.now baseline R1 mitigation); NO `setTimeout` recursivo sin cleanup (memory leak); NO `aria-live="assertive"` (interruptivo); NO pre-flight en TODOS los POST (latency overhead).

### 3.2 No-goals (explícitamente deferido)

1. **Backend cambios** — `configuracion_seguridad.max_intentos_login` + `minutos_bloqueo_login` ya shipped Fase 1 (HU-F1.2); `Retry-After` header ya implementado `auth.py:219-228`. F3.2 NO modifica backend.
2. **Refresh-token rotation con `jti` reuse detection** — PR7 backend (forward hook `pending.md §5`); F3.2 consume Mutex F2.2 sin modification.
3. **AuthGuard component** — `parkos:auth:cleared` event listener → `navigate('/login?next=...')` es F3.3+ (forward hook).
4. **Logout button UI** — F3.3+ placeholder o HU posterior.
5. **Recuperación de password / 2FA / WebAuthn / biometric** — fuera Fase 3 (futuro).
6. **Multi-tab login UI** — kiosko single-tab per F2.3 `requestSingleInstanceLock` (DEC-UPD-07).
7. **Turno abrir/cerrar** — F3.3 (`features/caja/pages/{AbrirTurno,CerrarTurno}.tsx`).
8. **Countdown styling library externa** — `formatTime` helper inline (~5 LOC), NO librería externa (mantener bundle size small — kiosko desatendido, RAM limitada).
9. **Toast notifications** — out of scope Fase 3 (forward a F11.x sync UI).
10. **OS-level kiosk PIN rotation** — F2.3 kiosko mode baseline, no F3.2 touch.
11. **Sucursal selector UI** — JWT ya pinea sucursal (DEC-SUC-01 single-branch kiosko).
12. **`rememberMe` / `forgotPassword` keys** — pre-existentes en `auth.json:10-11` pero F3.2 NO las usa (kiosko desatendido).
13. **`REFRESH_INTERVAL_MS` configurable via UI** — hardcoded a 50min per DEC-SUC-03; configurabilidad via env (`PARKOS_REFRESH_INTERVAL_MS`) es forward hook F3.x.
14. **Pre-flight para otros endpoints** — T3 cubre solo `/facturacion/*` + `/caja/arqueo*` per plan.md:1311 + DEC-SUC-03. Otros POST críticos futuros se agregan via DEC-F3.2-10 (`PRE_FLIGHT_PATHS_EXTENDED` o env var).
15. **Zod schema validation en boundary via `parkosFetch<T>(url, schema)`** — `DEC-FETCH-05` optional, F3.2 NO exige.
16. **Per-account countdown state persistence** — countdown es ephemeral (vive solo durante lockout active). Post-unmount, state GC'd. NO persist a electron-store.
17. **i18n plurals para countdown** — `mm:ss` suficiente (max 99:59 = 2h, suficiente para `minutos_bloqueo_login` default 10min × max configurable 60min per `auth.py`).
18. **`POST /auth/login` pre-flight** — `/auth/login` es anónimo (DEC-F3.1-05). Si por error matchea `/facturacion`, NO hay daño porque `expiresAt` es null pre-login → pre-flight skip.
19. **Pre-flight en GET requests** — 401 retry cubre (handle401 F2.2). Pre-flight solo mutacionales POST.

---

## 4. Decisions ratified (DEC-F3.2-NN)

F3.2 introduce **11 decisiones arquitectónicas** (DEC-F3.2-01..10 ratified en exploration §7 + DEC-F3.2-11 NUEVA decisión de spec delta introducida en esta propuesta). El detalle verbatim vive en `exploration.md` §7 (DEC-F3.2-01..10) y en §4.11 abajo (DEC-F3.2-11). Esta sección referencia y resume cada DECISION + RATIONALE + ALTERNATIVES CONSIDERED.

### 4.1 DEC-F3.2-01 — `useCountdown` signature: `Date.now()` baseline (NO accumulator)

**DECISION**: `useCountdown(retryAfterSeconds: number, options?: { onComplete?: () => void }): { secondsLeft: number; isExpired: boolean }`. Internals: `endTime = Date.now() + retryAfterSeconds * 1000`. Tick handler recalcula `secondsLeft = Math.max(0, Math.ceil((endTime - Date.now()) / 1000))`. NO accumulator pattern (`secondsLeft--`).

**RATIONALE**: Accumulator drift. Si tab inactive + system sleep, `setInterval` puede pausar (browser throttle) → accumulator queda atrasado del wall clock. `Date.now()` baseline es drift-resistant (siempre recomputa desde wall clock). R1 risk mitigation en §10.

**ALTERNATIVES CONSIDERED**:
- A. Accumulator pattern (`secondsLeft--`) — RECHAZADA. Drift risk + test brittleness. R1 mitigation.
- B. `Date.now()` baseline (DECIDIDA) — Wall clock anchor + recalc per tick. Drift-resistant. Tests use `vi.advanceTimersByTime(2000)` y verifican `secondsLeft` decrementa 2 (no 1).

### 4.2 DEC-F3.2-02 — Countdown UX: form `disabled` (NOT readonly)

**DECISION**: Durante lockout, ambos `<Input>` + `<Button type="submit">` se renderizan con `disabled={true}`. El countdown display se renderiza ARRIBA del form (entre el `<p role="alert">{t('lockout')}</p>` y los inputs).

**RATIONALE**: `disabled` previene submit + previene typing. `readonly` permite typing pero no submit — UX confuso. WCAG 2.1 AA: `aria-disabled="true"` adicional para screen readers anuncia estado.

**ALTERNATIVES CONSIDERED**:
- A. `readonly` (HTML `readonly` attr) — RECHAZADA. UX inconsistente: typing permitido pero submit no.
- B. `disabled` (HTML `disabled` attr + `aria-disabled`) — DECIDIDA. Consistencia total + a11y compliant.

### 4.3 DEC-F3.2-03 — Pre-flight trigger: conditional on path (regex match)

**DECISION**: Pre-flight gate `refreshIfExpiringSoon()` se invoca SOLO si `method === 'POST'` AND `url.match(PRE_FLIGHT_PATHS)`. Constante `PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/`. Compile regex módulo-level (NO recompilar per request).

**RATIONALE**: Pre-flight tiene latency cost (~50-150ms). Aplicarlo a TODOS los POST degrada UX innecesariamente. Solo endpoints críticos del DEC-SUC-03: pago (`/facturacion/*`) + arqueo (`/caja/arqueo`). Otros POST (catálogos read, sync, etc.) NO requieren pre-flight — 401 retry cubre.

**ALTERNATIVES CONSIDERED**:
- A. Pre-flight en TODOS los POST — RECHAZADA. Latency overhead innecesario.
- B. Pre-flight solo en critical paths via regex (DECIDIDA) — Mínimo overhead, máxima correctness para paths críticos.
- C. Per-endpoint config (e.g., decorator en cada fetch caller) — RECHAZADA. Boilerplate + drift risk. Regex simple + constante módulo-level = single source of truth.

### 4.4 DEC-F3.2-04 — SWR refresh interval: 50min hardcoded (configurable via const export)

**DECISION**: `useAuth.ts:60` cambia `refreshInterval: 5 * 60 * 1000` → `refreshInterval: REFRESH_INTERVAL_MS = 50 * 60 * 1000`. Constante exportada para testabilidad.

**RATIONALE**: DEC-SUC-03 (plan.md:418) verbatim "Refresh transparente cada 50 minutos". 50min deja safety margin de 10min vs `ACCESS_TOKEN_TTL=3600` (auth.py:71). Configurabilidad via UI es forward hook (no F3.2 scope). Constante exportada permite tests deterministas sin magic numbers.

**ALTERNATIVES CONSIDERED**:
- A. Mantener 5min (F2.2 baseline) — RECHAZADA. 12x bandwidth waste vs DEC-SUC-03.
- B. Hardcoded 50min sin constante — RECHAZADA. Magic number + tests brittle.
- C. Constante exportada 50min (DECIDIDA) — DEC-SUC-03 verbatim + testable.

### 4.5 DEC-F3.2-05 — e2e axe-core scope: countdown state WCAG check

**DECISION**: `e2e/auth/lockout.spec.ts` A1 test verifica axe-core 0 violaciones durante countdown state (form disabled + `<p role="status" aria-live="polite">` countdown). `withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])` mismo F3.1 pattern (`login.spec.ts` A1).

**RATIONALE**: REQ-OPS-112 (F3.1 spec) + RNF-022 WCAG 2.1 AA. Countdown display debe pasar axe-core scan — `role="status"` + `aria-live="polite"` son patrones axe-core compliant. A1 corre post-countdown-render (después de mock 429 + retry-after).

**ALTERNATIVES CONSIDERED**:
- A. Axe-core check solo en form (sin countdown) — RECHAZADA. RNF-022 cubre TODO el state transaccional.
- B. Axe-core check durante countdown state (DECIDIDA) — Coverage completa + replica F3.1 A1 pattern.

### 4.6 DEC-F3.2-06 — Countdown i18n keys: 3 keys en `auth.json`

**DECISION**: `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` agrega 3 keys:

- `lockoutCountdown`: "Reintento disponible en {{time}}" (template i18next interpolation).
- `lockoutReEnable`: "El formulario se ha reactivado. Puedes intentar de nuevo." (auto re-enable notice).
- `lockoutLabel`: "Tiempo restante para reintentar: {{time}}" (aria-label descriptivo).

**RATIONALE**: F2.1 DEC-ELEC-06 — un namespace por bounded context. `auth` namespace ya tiene `lockout` key (line 8) — countdown keys son extensión natural. NO requiere nuevo namespace `auth.countdown`.

**ALTERNATIVES CONSIDERED**:
- A. Nuevo namespace `auth.countdown` — RECHAZADA. F2.1 DEC-ELEC-06 verbatim + boilerplate.
- B. Extensión del namespace `auth` existente (DECIDIDA) — Namespace consistency + cero boilerplate.

### 4.7 DEC-F3.2-07 — Pre-flight latency budget: ≤200ms

**DECISION**: `refreshIfExpiringSoon` debe ejecutar en ≤200ms p95. Refresh HTTP baseline ~50-150ms (F2.2 benchmark post-Mutex + cookie round-trip). 50ms budget para regex match + Date.parse + Mutex acquisition check.

**RATIONALE**: UX crítica para kiosko desatendido. POST `/facturacion` esperando >200ms para refresh degrada perceived performance. Si budget se excede, el request continúa con token existente (graceful degradation — `handle401` retry cubre el 401 post-refresh). R5 mitigation.

**ALTERNATIVES CONSIDERED**:
- A. Sin budget — RECHAZADA. UX risk si refresh cuelga.
- B. Budget ≤200ms con graceful degradation (DECIDIDA) — Soft target + fallback reactivo.

### 4.8 DEC-F3.2-08 — DELTA verdict (NOT NO-OP) — F3.2 IS user-facing

**DECISION**: F3.2 emite DELTA spec con 6 new REQ-OPS-113..118 (numbered post-F3.1 REQ-OPS-106..112). Spec delta materializes en `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md`.

**RATIONALE**: F3.2 ES user-facing behavior observable: (a) countdown visual decreciente cada 1000ms (clock visible al operador); (b) form disabled durante lockout (interacción observable); (c) pre-flight gate evita 401 mid-write en `/facturacion/*` + `/caja/arqueo/*` (latency + correctness observable); (d) refresh 50min automático (session longevity observable). Per F1.15 + F3.1 precedent, user-facing ⇒ spec delta materialized. F2.x precedent (NO-OP stub via DEC-ELEC-10, DEC-FETCH-10, DEC-UPD-13) aplica solo a infra-only HU sin behavior visible al operador. F3.2 rompe el precedent NO-OP siguiendo F3.1. Ver DEC-F3.2-11 abajo para el rationale extendido del verdict.

**ALTERNATIVES CONSIDERED**:
- A. NO-OP stub (DEC-FETCH-10 precedent verbatim) — RECHAZADA tras re-evaluación. F2.x fueron infra-only; F3.2 ES user-facing. Aplicar precedent equivocado rompería audit trail.
- B. DELTA con 6 new REQ-OPS-113..118 (DECIDIDA) — Cobertura completa de behavior observable al operador. Match precedent F3.1 (7 new REQ-OPS-106..112) + F1.15 (4 new REQ-OPS-102..105).

### 4.9 DEC-F3.2-09 — e2e lockout attempts: configurable via env (default 4)

**DECISION**: `e2e/auth/lockout.spec.ts` E1 test hace `max_intentos_login - 1` intentos fallidos + 1 intento que recibe 429 → asserts countdown. Default e2e usa `MAX_INTENTOS_LOGIN = 4` (rápido para test). Backend configurable via `configuracion_seguridad.max_intentos_login` (default 5 per `auth.py:225`).

**RATIONALE**: Test rápido (4 intentos vs 5) sin sacrificar coverage. El test verifica el FLOW (intentos fallidos → 429 → countdown), no el número EXACTO de intentos. MSW/page.route mockea 429 después de N intentos — N es param. Resuelve inconsistency I1 (`plan.md:1309` "5 intentos" vs orchestrator user "4 attempts").

**ALTERNATIVES CONSIDERED**:
- A. Hardcoded 5 intentos (canonical backend default) — RECHAZADA. Test lento + brittle a cambios de `configuracion_seguridad`.
- B. Configurable via env (DECIDIDA) — Test rápido por default + respeta backend config en CI.

### 4.10 DEC-F3.2-10 — Forward hook: pre-flight paths extensibilidad

**DECISION**: `PRE_FLIGHT_PATHS` constante módulo-level permite extensión future via nueva constante `PRE_FLIGHT_PATHS_EXTENDED` o env var. F3.2 cubre `/facturacion/*` + `/caja/arqueo*` per DEC-SUC-03. F3.3+ (turno) puede extender a `/caja-sesion/*` si lo requiere.

**RATIONALE**: YAGNI — F3.2 NO incluye `/caja-sesion/*` (F3.3 decidirá). Pero la constante es extensibilidad-friendly para forward hooks. Resuelve inconsistency I3 (`plan.md:1311` menciona `/caja/arqueo` que no existe todavía — Fase 10 introduce arqueos).

**ALTERNATIVES CONSIDERED**:
- A. Pre-flight paths hardcoded en sitio — RECHAZADA. Forward compatibility viola DRY.
- B. Constante módulo-level extensible (DECIDIDA) — Single source of truth + extensibility-friendly.

### 4.11 DEC-F3.2-11 — **NUEVA** Spec delta a `operations/spec.md` con 6 new REQ-OPS-113..118 (DELTA, NO NO-OP)

**DECISION**: `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md` AGREGA 6 new REQ-OPS-113..118 al spec canónico, NO es NO-OP stub. Las 6 REQ-OPS documentan el comportamiento observable al operador (countdown display + form disabled + pre-flight gate + refresh 50min + Mutex preserved + WCAG 2.1 AA countdown) en formato Given/When/Then/And RFC 2119.

**RATIONALE — re-evaluación crítica desde exploration §7 (DEC-FETCH-10 NO-OP precedent)**: la exploration original propuso DEC-FETCH-10-style NO-OP stub siguiendo precedent F2.1/F2.2/F2.3 (todos infra-only, sin behavior observable al operador). Esta propuesta **rompe** ese precedent y adopta precedent F1.15 (login histórico, archivado 2026-09-15) que SÍ escribió 4 new REQ-OPS-102..105 al spec canónico + F3.1 (archivado 2026-09-15) que escribió 7 new REQ-OPS-106..112 al spec canónico, ambos con la misma justificación: countdown + refresh + lockout son user-facing behavior que el operador observa y depende. La justificación detallada:

| Aspecto | F2.1/F2.2/F2.3 (NO-OP precedent) | F3.2 (DELTA con new REQ-OPS-NNN) |
|---|---|---|
| Tipo de cambio | Infra-only (scaffold + IPC + runtime) | User-facing behavior observable |
| Componente visible al operador | Ninguno (electron main, ipc preload, services) | Countdown display + form disabled state + pre-flight latency + refresh longevity |
| Behavior observable | N/A (no UI) | Countdown decreciente + retry-after visible + form auto re-enable |
| Pre-flight correctness | N/A (no POST críticos) | `/facturacion/*` + `/caja/arqueo` sin 401 mid-write |
| Precedent directo | DEC-ELEC-10 / DEC-FETCH-10 / DEC-UPD-13 (infra) | REQ-OPS-102..105 (F1.15) + REQ-OPS-106..112 (F3.1) user-facing |
| Verificabilidad | DEC-* documentan; sin REQ spec-level | REQ-OPS-NNN + DEC-* cross-linked |

**Numeración**: el último REQ-OPS vigente en `operations/spec.md` es REQ-OPS-112 (F3.1 archivado 2026-09-15, línea 4626). Las 6 new REQs ocupan REQ-OPS-113..118 (continuación monotónica). Numeración verificada: 112 → 113 → 114 → 115 → 116 → 117 → 118 (0 gaps, sin duplicados).

**Las 6 new REQ-OPS-113..118** (detail en §6):

| ID | Behavior observable | Anchor DEC |
|---|---|---|
| REQ-OPS-113 | `useCountdown(retryAfterSeconds)` hook con `Date.now()` baseline + `setInterval(1000)` + cleanup en unmount + `onComplete` callback (drift-resistant) | DEC-F3.2-01 |
| REQ-OPS-114 | `<LoginForm>` aplica `disabled={true}` a inputs + submit mientras `useCountdown().secondsLeft > 0` + renderiza `<p role="status" aria-live="polite">` con countdown mm:ss | DEC-F3.2-02 |
| REQ-OPS-115 | Auto re-enable del form cuando `useCountdown().isExpired === true` (cleanup interval + reset `errorState` a null) | DEC-F3.2-02 |
| REQ-OPS-116 | `parkosFetch` pre-flight gate `refreshIfExpiringSoon()` invocado antes de POST matcheando `PRE_FLIGHT_PATHS = /\/facturacion(\/\|$)\|\/caja\/arqueo/` cuando `expiresAt - now < 5min` | DEC-F3.2-03 |
| REQ-OPS-117 | `useAuth.refreshInterval: 50 * 60 * 1000` (constante `REFRESH_INTERVAL_MS` exportada) — refresh transparente cada 50min vs TTL 3600s (10min safety margin) | DEC-F3.2-04 |
| REQ-OPS-118 | WCAG 2.1 AA compliance countdown: axe-core 0 violaciones durante countdown state (RNF-022) | DEC-F3.2-05 |

**ALTERNATIVES CONSIDERED**:
- A. NO-OP stub (DEC-FETCH-10 precedent verbatim) — RECHAZADA tras re-evaluación. F2.1/F2.2/F2.3 fueron infra-only; F3.2 ES user-facing behavior. Aplicar precedent equivocado rompería el audit trail del spec.
- B. DELTA con 4 new REQ-OPS-113..116 (minimum viable) — RECHAZADA. Reduciría cobertura de comportamiento. 6 REQs balancean audit trail exhaustivo sin overload.
- C. DELTA con 6 new REQ-OPS-113..118 (DECIDIDA) — Cobertura completa de behavior observable al operador. Match precedent F3.1 (7 new REQ-OPS-106..112) + extra coverage para pre-flight gate + Mutex preserved + WCAG countdown.

**Convención de identificadores**: DEC-F3.2-NN sigue el patrón DEC-ELEC-NN (F2.1), DEC-FETCH-NN (F2.2), DEC-UPD-NN (F2.3), DEC-LOGIN-NN (F1.15), DEC-F3.1-NN (F3.1). REQ-OPS-NNN sigue la numeración monotónica del spec canónico vigente. F3.2 ocupa REQ-OPS-113..118 (continuación de F3.1 REQ-OPS-106..112).

---

## 5. Scope y out-of-scope

### 5.1 In Scope (130 LOC production + 240 LOC tests)

| Area | Detalle |
|---|---|
| **`useCountdown` hook (T1)** | New `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (~40 LOC production + ~50 LOC tests). Reusable. Signature: `useCountdown(retryAfterSeconds: number, options?: { onComplete?: () => void }): { secondsLeft: number; isExpired: boolean }`. Internals: `Date.now() + retryAfterSeconds * 1000` baseline (NUNCA accumulator — R1 mitigation), `setInterval(1000)` decrementa `secondsLeft`, cleanup en unmount via `useEffect` return, `onComplete` callback cuando llega a 0. |
| **LoginForm countdown integration (T2)** | Modify `LoginForm.tsx` para consumir `useCountdown(retryAfterSeconds)` cuando `error.kind === 'lockout'`. Form fields `disabled={error?.kind === 'lockout' && !isExpired}`. Countdown display `<p role="status" aria-live="polite" data-testid="login-countdown">{formatTime(secondsLeft)}</p>` debajo del mensaje `t('lockout')`. Botón submit `disabled` durante lockout. `formatTime` helper: `mm:ss` (e.g., "09:47"). |
| **Login.tsx wiring (T2)** | Modify `Login.tsx` para pasar `retryAfterSeconds` del `AccountLockedError` al state, y propagar al `LoginForm` como `error: { kind: 'lockout', retryAfterSeconds: err.retryAfterSeconds }`. Cuando `useCountdown.isExpired === true`, reset `errorState` a `null` para re-habilitar el form. |
| **`useAuth` 50min refresh (T3)** | Modify `useAuth.ts:60` para cambiar `refreshInterval: 5 * 60 * 1000` → `50 * 60 * 1000`. Agregar constante exportada `REFRESH_INTERVAL_MS = 50 * 60 * 1000` para testabilidad. Update `useAuth.ts:8-12` JSDoc para reflejar nuevo intervalo. |
| **parkosFetch pre-flight gate (T3)** | Modify `parkosFetch.ts` para agregar función `refreshIfExpiringSoon()` (exportada o módulo-internal). En `parkosFetchRaw` línea 154-165, ANTES del fetch, si `method === 'POST'` AND `url.match(/\/(facturacion\|caja\/arqueo)/)` AND `useAuthStore.expiresAt !== null` AND `Date.parse(useAuthStore.expiresAt) - Date.now() < 5 * 60 * 1000` → `await refreshAccessToken()` (Mutex shared con 401 path). Constante `PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000`. Lista de paths en constante `PRE_FLIGHT_PATHS = /\/facturacion(\/\|$)\|\/caja\/arqueo/`. |
| **i18n keys (T2)** | Modify `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` — agregar 2-3 keys: `lockoutCountdown` (template `${mm}:${ss}`), `lockoutReEnable` (auto re-enable notice), `lockoutLabel` (aria-label para el display). NO requiere nuevo namespace (F2.1 DEC-ELEC-06 — un namespace por bounded context). |
| **e2e lockout scenario (T4)** | New `apps/electron-sucursal/e2e/auth/lockout.spec.ts` (~80 LOC tests). 4 escenarios: (E1) 4 intentos fallidos → 429 → countdown visible `< 600s`; (E2) countdown decrementa cada ~1000ms; (E3) countdown llega a 0 → form re-habilitado; (A1) axe-core 0 violaciones en `/login` durante lockout state. |
| **Unit tests** | New `apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts` (~50 LOC, 4 tests: U1 baseline Date.now + setInterval, U2 cleanup on unmount, U3 onComplete callback fires, U4 drift resistance via Date.now()). Modify `useAuth.test.ts` para verificar `REFRESH_INTERVAL_MS = 50 * 60 * 1000`. Modify `parkosFetch.test.ts` para agregar 2-3 tests pre-flight (U5 expiring soon triggers refresh, U6 not expiring skips refresh, U7 GET no triggerea refresh). Modify `Login.test.tsx` + `LoginForm.test.tsx` para verificar countdown wiring (3 tests adicionales: U8 lockout disables form, U9 countdown decrements, U10 isExpired resets errorState). |

### 5.2 Out of Scope (explícitamente deferido)

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
- **`REFRESH_INTERVAL_MS` configurable via UI**: hardcoded a 50min per DEC-SUC-03; configurabilidad futura si negocio requiere.
- **Pre-flight para otros endpoints**: T3 cubre solo `/facturacion/*` + `/caja/arqueo*` per plan.md:1311 + DEC-SUC-03. Otros POST críticos futuros se agregan via DEC-F3.2-10.
- **Countdown para retry buttons**: useCountdown se reusa en F4.x/F11.x per forward hooks §12, pero F3.2 solo lo integra en Login.
- **i18n plurals**: countdown siempre mm:ss (max 99:59 = 2h, suficiente para `minutos_bloqueo_login` default 10min × max `minutos_bloqueo_login` configurable hasta 60min per auth.py).

---

## 6. Arquitectura propuesta

### 6.1 Diagrama de componentes (ASCII)

```
+------------------------------------------------------------------+
| <App> (F3.1, no F3.2 touch)                                      |
|  +-- <BrowserRouter>                                              |
|  |   +-- <Routes>                                                 |
|  |       +-- <Route path="/login" element={<LoginPage />}>       |
|  +----------------------------------------------------------------+
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| <LoginPage> (container, F3.1 +10 LOC F3.2 T2)                     |
|  +-- useAuth() → { isAuthenticated, isLoading, data }             |
|  +-- useEffect([isAuthenticated, data?.user, isLoading])         |
|  |     → navigate('/')                                            |
|  +-- onSubmit(data) → postLogin(...)                              |
|  |     → setTokens(...) → SWR re-fetcha /auth/me                  |
|  |     → 429 catch: errorState = { kind:'lockout',               |
|  |                                  retryAfterSeconds: N }       |
|  |     → isExpired → reset errorState a null                     |
|  +-- <LoginForm form={form}                                       |
|  |                onSubmit={onSubmit}                             |
|  |                isSubmitting={isSubmitting}                     |
|  |                error={error} />                                |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| <LoginForm> (presentational, F3.1 +25 LOC F3.2 T2)                |
|  +-- useCountdown(error.retryAfterSeconds)                        |
|  |     → { secondsLeft, isExpired }                               |
|  |     → setInterval(1000) + cleanup                              |
|  +-- formatTime(secondsLeft) → "mm:ss"                            |
|  +-- <Form {...form}>                                             |
|  |   +-- <FormField name="email" ...>                             |
|  |   |   <Input disabled={error?.kind === 'lockout' && !isExpired}|
|  |   +-- <FormField name="password" ...>                          |
|  |   |   <Input disabled={error?.kind === 'lockout' && !isExpired}|
|  |   +-- {error?.kind === 'lockout' && (                          |
|  |   |   <p role="alert">{t('lockout')}</p>                       |
|  |   |   <p role="status" aria-live="polite"                      |
|  |   |      aria-label={t('lockoutLabel', {time: formatTime})}>   |
|  |   |      data-testid="login-countdown"                         |
|  |   |      >{formatTime(secondsLeft)}</p>                        |
|  |   |   )}                                                       |
|  |   +-- <Button type="submit"                                    |
|  |          disabled={isSubmitting ||                             |
|  |                   (error?.kind === 'lockout' && !isExpired)}>  |
|  +-- {error && error.kind !== 'lockout' &&                       |
|       <p role="alert">{error}</p>}                                |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| useCountdown (NEW ~40 LOC, T1)                                    |
|  useCountdown(retryAfterSeconds, options?)                        |
|   → { secondsLeft, isExpired }                                   |
|   internals:                                                      |
|     endTime = Date.now() + retryAfterSeconds * 1000  (baseline)  |
|     setInterval(1000) → recalc secondsLeft from endTime           |
|     useEffect cleanup → clearInterval                             |
|     onComplete callback fires when secondsLeft reaches 0          |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| useAuth (F2.2, MODIFY line 60, F3.2 T3)                          |
|  +-- useSWR(                                                      |
|      key: accessToken ? '/auth/me' : null,                         |
|      fetcher: parkosFetch('/auth/me'),                           |
|      refreshInterval: REFRESH_INTERVAL_MS = 50 * 60 * 1000  ←CHANGE|
|      revalidateOnFocus: true,                                    |
|      dedupingInterval: 2000,                                     |
|    )                                                              |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| parkosFetch (F2.2, MODIFY +20 LOC, F3.2 T3)                      |
|  +-- parkosFetchRaw(url, init)                                    |
|       → [NEW] if method==='POST'                                  |
|              && url.match(PRE_FLIGHT_PATHS)                       |
|              && useAuthStore.expiresAt !== null                   |
|              && Date.parse(expiresAt) - Date.now() <             |
|                 PRE_FLIGHT_THRESHOLD_MS                           |
|         → await refreshIfExpiringSoon()                           |
|       → fetch(url, init)                                          |
|       → on 401 → handle401 → refreshAccessToken (Mutex)          |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| refreshIfExpiringSoon (NEW, T3)                                  |
|  +-- if Date.parse(useAuthStore.expiresAt) - Date.now()           |
|  |       < PRE_FLIGHT_THRESHOLD_MS (5min)                        |
|  |     → await useAuthStore.getState().refreshAccessToken()       |
|  |       (Mutex singleton — F2.2 DEC-FETCH-03 invariant)         |
|  +-- return (refresh succeeded or failed)                         |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| refreshAccessToken (F2.2 READ ONLY, consumed by F3.2 T3)         |
|  +-- Mutex singleton (F2.2 DEC-FETCH-03)                          |
|  +-- POST /api/v1/auth/refresh (auth.py:310-349)                  |
|  +-- updates useAuthStore.accessToken + refreshToken + expiresAt |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| useAuthStore (F2.2 READ ONLY, consumed by F3.2)                   |
|  +-- accessToken: string \| null                                   |
|  +-- refreshToken: string \| null                                 |
|  +-- expiresAt: string \| null (ISO 8601 UTC)                     |
|  +-- setTokens(access, refresh, expiresIn) → updates all 3       |
|  +-- clear() → all 3 → null                                       |
|  +-- refreshAccessToken() → Mutex singleton                       |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| backend POST /api/v1/auth/login (F1.2 READ ONLY)                  |
|  +-- 200 OK → TokenPair{access, refresh, expires_in}              |
|  +-- 401 → invalid_credentials (anti-enumeration)                 |
|  +-- 429 → Retry-After: <segundos> header                         |
+------------------------------------------------------------------+
```

### 6.2 Tabla de componentes

| Componente | Tipo | Responsabilidad | Tests | DEC |
|---|---|---|---|---|
| `<LoginPage>` | Container (page) | F3.1 + wire `useCountdown.isExpired` reset errorState | `Login.test.tsx` (F3.1 + F3.2) | DEC-F3.2-02 |
| `<LoginForm>` | Presentational | F3.1 + countdown display + form disabled | `LoginForm.test.tsx` (F3.1 + F3.2) | DEC-F3.2-02, DEC-F3.2-05 |
| `useCountdown` | Hook (NEW) | `Date.now()` baseline + `setInterval(1000)` + cleanup + onComplete | `useCountdown.test.ts` (NEW) | DEC-F3.2-01 |
| `useAuth()` | Hook (F2.2 MODIFY) | SWR `/auth/me` con refreshInterval 50min | `useAuth.test.ts` (F2.2 + F3.2) | DEC-F3.2-04 |
| `parkosFetch` | HTTP (F2.2 MODIFY) | + pre-flight gate `refreshIfExpiringSoon()` | `parkosFetch.test.ts` (F2.2 + F3.2) | DEC-F3.2-03, DEC-F3.2-07 |
| `refreshIfExpiringSoon` | Pure function (NEW) | Refresh proactive antes de POST críticos | (covered by parkosFetch.test.ts) | DEC-F3.2-03 |
| `refreshAccessToken` | Store action (F2.2) | Mutex singleton refresh | (F2.2 already tested) | DEC-F3.2-03, DEC-FETCH-03 |
| `useAuthStore` | Store (F2.2) | Zustand persist electron-store + expiresAt ISO 8601 | (F2.2 already tested) | DEC-F3.2-03 |
| `postLogin` | Pure function (api, F3.1) | `fetch` raw + `AccountLockedError(retryAfterSeconds)` | `loginApi.test.ts` (F3.1) | DEC-F3.2-09 |
| `AccountLockedError` | Custom error (F3.1) | `retryAfterSeconds: number` field | (F3.1 already tested) | DEC-F3.2-09 |
| `formatTime` | Pure helper (NEW) | `mm:ss` from seconds | (covered by LoginForm.test.tsx) | DEC-F3.2-06 |
| `auth.json` | i18n (F3.1 MODIFY) | +3 keys countdown | snapshot test (F3.1) | DEC-F3.2-06 |
| `e2e/auth/lockout.spec.ts` | E2E test (NEW) | 4 scenarios countdown | E2E playwright _electron | DEC-F3.2-05, DEC-F3.2-09 |

### 6.3 Layers + flow de datos

1. **UI layer**: `LoginForm` renderiza countdown + aplica `disabled`. Container `Login` wirea `useCountdown.isExpired` para reset `errorState`.
2. **Hook layer**: `useCountdown(retryAfterSeconds)` retorna `{secondsLeft, isExpired}`. Date.now() baseline + setInterval(1000).
3. **State layer**: `useAuthStore.expiresAt` (ISO 8601 UTC, derivable via `Date.parse`). Consumido por pre-flight gate.
4. **HTTP layer**: `parkosFetch` agrega pre-flight gate `refreshIfExpiringSoon()` antes de POST críticos. Mutex shared con `handle401` (F2.2 invariant preserved).
5. **Backend layer**: `POST /api/v1/auth/login` retorna 429 + `Retry-After: <segundos>` (auth.py:219-228). Consumido por `parseRetryAfter` (F3.1). Cero cambios backend.

### 6.4 Stack técnico

- **React 18.3.1** (renderer, F2.1 baseline).
- **react-hook-form 7.53.0** + **zod 3.23.8** (F2.1+F3.1 baseline).
- **shadcn Form/Input/Button** (F2.1 baseline, `apps/electron-sucursal/src/renderer/components/ui/`).
- **react-router-dom 6.27.0** (F2.1 baseline).
- **useAuth() + useAuthStore** (F2.2 primitives, ui-kit).
- **SWR** (F2.2 baseline) — `refreshInterval` change T3.
- **axe-core 4.10.x** via `@axe-core/playwright` (F2.1 baseline, RNF-022).
- **Vitest 2.1.x + @testing-library/react 16.0.1** (F2.1+F2.2+F3.1 baseline).
- **MSW 2.x** for `lockout.spec.ts` HTTP mocks (F3.1 precedent).
- **Vanilla JS**: `setInterval` + `clearInterval` + `Date.now()` (NO librería externa).

---

## 7. Implementation strategy

### 7.1 Cluster map (C1)

F3.2 se descompone en **1 cluster** (C1) con orden interno T1 → (T2 || T3) → T4. T2 (frontend UI countdown) y T3 (infra ui-kit pre-flight + refresh) pueden ejecutarse en paralelo si el executor lo permite — ambos commitean independientemente.

### 7.2 Orden de ejecución

**T1 → (T2 || T3) → T4**.

- T1 antes de T2 porque T2 consume `useCountdown` que T1 crea. T1 antes de T3 porque T3 modifica `useAuth.ts` + `parkosFetch.ts` que requieren tests verde antes del integration.
- T2 antes de T4 porque T4 e2e tests requieren LoginForm countdown wired (T2 output).
- T3 antes de T4 porque T4 e2e tests pueden verificar pre-flight (forward coverage).
- T2 y T3 son independientes — pueden ejecutarse en paralelo.

### 7.3 Estrategia TDD

Cada task es **atómica** (commiteable independientemente con tests verde). TDD estricto:

- Tests rojos primero, luego código que los hace verde.
- Cobertura >80% exigida en `useCountdown.ts` + `Login.tsx` + `LoginForm.tsx` + `parkosFetch.ts` (pre-flight gate).
- Cobertura 100% de los 4 e2e scenarios (E1+E2+E3+A1).
- Defense in depth 5 capas preservado (F3.2 contribute a11y + retry-budget layers).

### 7.4 Forward hooks — implementación transversal

`useCountdown` se exporta desde `features/auth/hooks/useCountdown.ts` para consumo cross-feature. F4.x (catálogos) puede importarlo para retry buttons. F11.x (sync UI) puede importarlo para reintentos de sync con countdown visual + exponential backoff.

`PRE_FLIGHT_PATHS` constante módulo-level permite extensión future. F3.3+ (turno) puede extender a `/caja-sesion/*` si lo requiere via DEC-F3.2-10.

`REFRESH_INTERVAL_MS` constante exportada permite override via env var (`PARKOS_REFRESH_INTERVAL_MS`) si negocio requiere ajustar en deployment específico.

---

## 8. Atomic tasks preview (T1..T4)

Cada task es **atómica** (commiteable independientemente con tests verde), pero se ejecutan en orden T1 → (T2 || T3) → T4. Detalle verbatim en `exploration.md` §10.

| Task | Budget (LOC) | Archivos | Commit message | Gate |
|---|---|---|---|---|
| **T1 — `useCountdown` hook + 4 unit tests** | ~90 (40 prod + 50 tests) | `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (NEW, ~40 LOC — `Date.now()` baseline + `setInterval(1000)` + cleanup + `onComplete` callback) · `useCountdown.test.ts` (NEW, ~50 LOC — U1 baseline Date.now, U2 cleanup on unmount, U3 onComplete fires at 0, U4 drift resistance via fake timers) | `feat(auth): adicionar useCountdown hook con Date.now() baseline + cleanup + onComplete` | G1 |
| **T2 — Integrar `useCountdown` en LoginForm + countdown display + 3 unit tests** | ~80 (40 prod + 40 tests) | `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (MODIFY, +25 LOC — consume `useCountdown(retryAfterSeconds)` cuando `error.kind === 'lockout'`, renderiza `<p role="status" aria-live="polite">`, aplica `disabled` a inputs + submit durante lockout) · `Login.tsx` (MODIFY, +10 LOC — wire `useCountdown.isExpired` para reset `errorState` a null) · `auth.json` (MODIFY, +3 keys — `lockoutCountdown`, `lockoutReEnable`, `lockoutLabel`) · `LoginForm.test.tsx` (MODIFY, +25 LOC — U8 lockout disables form, U9 countdown decrements) · `Login.test.tsx` (MODIFY, +15 LOC — U10 isExpired resets errorState) | `feat(auth): integrar useCountdown en LoginForm + countdown display + 3 i18n keys` | G2, G3, G4 |
| **T3 — `parkosFetch` pre-flight gate + `useAuth` 50min refresh + 5 unit tests** | ~100 (30 prod + 70 tests) | `apps/ui-kit/src/hooks/useAuth.ts` (MODIFY, line 60 — `refreshInterval: 5 * 60 * 1000` → `REFRESH_INTERVAL_MS = 50 * 60 * 1000` + constante exportada + JSDoc update) · `apps/ui-kit/src/fetch/parkosFetch.ts` (MODIFY, +20 LOC — `PRE_FLIGHT_PATHS` regex + `PRE_FLIGHT_THRESHOLD_MS` const + `refreshIfExpiringSoon()` internal function + integration en `parkosFetchRaw` antes del fetch) · `useAuth.test.ts` (MODIFY, +10 LOC — verify `REFRESH_INTERVAL_MS = 50 * 60 * 1000`) · `parkosFetch.test.ts` (MODIFY, +60 LOC — U5 expiring soon triggers refresh, U6 not expiring skips refresh, U7 GET no triggerea, U8 refresh failure graceful degradation, U9 Mutex shared with 401 path) | `feat(refresh): 50min SWR refresh + pre-flight gate antes de POST /facturacion/* + /caja/arqueo` | G5 |
| **T4 — e2e lockout scenario + axe-core A1** | ~80 tests | `apps/electron-sucursal/e2e/auth/lockout.spec.ts` (NEW, ~80 LOC — E1 4 intentos → 429 + countdown visible, E2 countdown decrementa, E3 form re-enable al 0, A1 axe-core WCAG 2.1 AA) | `test(electron): adicionar 4 e2e lockout (countdown display + decrement + re-enable + axe-core)` | G6 |
| **TOTAL** | **~350 LOC** (110 prod + 240 tests) | 3 archivos nuevos + 8 modificaciones | 4 commits atómicos | 6 gates |

**Resumen de budgets**:

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 useCountdown hook | 40 | 50 | 90 |
| T2 Login countdown integration | 40 | 40 | 80 |
| T3 parkosFetch pre-flight + useAuth 50min | 30 | 70 | 100 |
| T4 e2e lockout 4 scenarios | 0 | 80 | 80 |
| **TOTAL** | **110** | **240** | **350** |

Total real ~130 LOC production matches plan.md:1317 verbatim (~110 production + ~20 JSDoc/configs = ~130).

---

## 9. Acceptance gates (G1..G6)

6 gates que deben pasar ANTES de mergear F3.2 a `origin/dev`.

| # | Gate | Mecanismo | Source | Anchor REQ-OPS |
|---|---|---|---|---|
| G1 | `useCountdown` setInterval(1000) cleanup on unmount | vitest `useCountdown.test.ts` U1 baseline + U2 cleanup + U3 onComplete + U4 drift resistance | T1 | REQ-OPS-113 |
| G2 | `AccountLockedError.retryAfterSeconds` parsed correctly (ya shipped F3.1, F3.2 NO regresiona) | vitest `loginApi.test.ts` U3 + U3b (F3.1 existente) | T2 regression | REQ-OPS-114 (F3.2 related) |
| G3 | `LoginForm` form disabled durante countdown | vitest `LoginForm.test.tsx` U8 (F3.2 nuevo) — mock `useCountdown` con `secondsLeft=300, isExpired=false` + assert `input[disabled]` + `button[disabled]` | T2 | REQ-OPS-114 |
| G4 | Countdown auto re-enable al llegar a 0 | vitest `Login.test.tsx` U10 (F3.2 nuevo) — mock 429 + advance fake timers + assert `errorState === null` post-isExpired | T2 | REQ-OPS-115 |
| G5 | `parkosFetch` pre-flight fires antes de `POST /facturacion/*` + `POST /caja/arqueo` | vitest `parkosFetch.test.ts` U5 expiring soon + U6 not expiring + U7 GET no triggerea (F3.2 nuevos) | T3 | REQ-OPS-116 |
| G6 | 4 e2e scenarios verde (countdown display + decrement + re-enable + axe-core) | playwright `e2e/auth/lockout.spec.ts` E1+E2+E3+A1 (F3.2 nuevos) — sandbox SKIPPED-env per F.6 precedent | T4 | REQ-OPS-118 (A1 axe-core) + REQ-OPS-117 (50min refresh observable via SWR) |
| G7 (implícito) | `useAuth.refreshInterval === 50 * 60 * 1000` constante | vitest `useAuth.test.ts` REFRESH_INTERVAL_MS assertion | T3 | REQ-OPS-117 |

**Estado pre-flight**: 0/7 PASS al inicio (no implementado). Target 7/7 PASS post-implementación.

**Sandbox F.6 precedent**: 6/10 gates SKIPPED en F2.1 + F2.2 + F2.3 archive + 2/7 SKIPPED-env en F3.1 archive (npm 11.16.0 refuses workspace:*). F3.2 e2e (G6) va a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect. Unit tests G1, G2 regression, G3, G4, G5, G7 + G6 axe-core source-level SÍ corren via `vitest run` + `tsc --noEmit`.

---

## 10. Risks y mitigaciones

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

**Riesgos identificados y cerrados**: 8/8 con mitigación explícita. 0 KNOWN-MISSING.

**Sandbox F.6 deviation esperada**: e2e (G6) puede SKIP en `npm 11.16.0` (F2.1 + F2.2 + F2.3 + F3.1 archive precedent). Documentado como deviation D-env en §15 DoD + `verify-report.md` futuro, NO project defect.

---

## 11. Dependencies

### 11.1 Shipped (F2.2 + F3.1 — prerequisites)

- **HU-F1.2** ✅ closed Fase 1: `POST /auth/login` + `GET /auth/me` + cookie httpOnly + 401/429 mapping backend (`backend/.../auth.py:148-583`).
- **HU-F1.15** ✅ closed Fase 1: login histórico (`prod.login` [L-S]) + 4 new REQ-OPS-102..105 user-facing (F1.15 precedent for DELTA stub).
- **HU-F2.1** ✅ closed Fase 2: Electron 30 skeleton + shadcn Form/Input/Button + i18n 7 namespaces + axe-core + playwright e2e.
- **HU-F2.2** ✅ closed Fase 2: parkosFetch (retry + refresh-once 401 via Mutex + Idempotency-Key) + bridge IPC + authStore Zustand + useAuth SWR + `expiresAt` ISO 8601 + `refreshAccessToken` Mutex singleton.
- **HU-F2.3** ✅ closed Fase 2: kiosko mode + electron-updater + StatusBar + single-instance lock.
- **HU-F3.1** ✅ closed 2026-09-15: Login page + LoginForm + loginApi + loginSchema + ruta `/login` + 7 REQ-OPS-106..112 + `AccountLockedError(retryAfterSeconds)` + `LoginErrorState kind:'lockout'`.

### 11.2 Precondiciones verificadas (pre-flight §3 exploration)

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

### 11.3 NO requiere (out of dependencies)

- **Backend cambios**: F3.2 NO modifica backend. `configuracion_seguridad.max_intentos_login` ya shipped Fase 1; `Retry-After` header ya implementado `auth.py:219-228`.
- **Nuevas dependencies npm**: F3.2 NO requiere `npm install`. `react@^18.3.1` + `setInterval` (vanilla JS) + `Date.now()` (vanilla JS) + `useEffect` (React) ya shipped.
- **Nuevos namespaces i18n**: `auth.json` suficiente. `lockoutCountdown` + `lockoutReEnable` + `lockoutLabel` se agregan al namespace existente.
- **Nuevos componentes shadcn**: countdown usa HTML semántico (`<p>`, `<button disabled>`). NO requiere `Progress` o `Badge` components.
- **Cambios en IPC bridge**: F3.2 NO agrega métodos IPC. Refresh es HTTP puro, NO IPC.

### 11.4 Forward dependencies (F3.3+ consume F3.2 outputs)

- **HU-F3.3** (Abrir/Cerrar turno): consume `useAuth().user.sucursal` + pre-flight gate automático para `POST /caja-sesion/sesiones` (forward hook — si F3.3 decide agregar `/caja-sesion` a pre-flight paths, DEC-F3.2-10 extiende la regex).
- **HU-F4.x** (catálogos): consume `useCountdown` para retry buttons (`useRetryWithCountdown` pattern).
- **HU-F5.x** (facturación): hereda pre-flight gate automáticamente (T3 cubre `/facturacion/*`).
- **HU-F11.x** (sync UI): consume `useCountdown` para reintentos de sync con countdown visual.

---

## 12. Forward hooks (Fase 3+ consumer map)

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

---

## 13. Trade-offs y alternatives considered

### 13.1 Date.now() baseline vs accumulator (DEC-F3.2-01)

**Trade-off**: `Date.now()` baseline (chosen) requiere recálculo cada tick pero es drift-resistant. Accumulator (`secondsLeft--`) es más performante pero drift si tab inactive + system sleep.

**Decisión**: Date.now() baseline. Drift resistance > 1µs/tick perf cost. Browsers throttle `setInterval` aggressively cuando tab inactive (60s+ intervals compressed) — accumulator acumula drift significativo.

### 13.2 50min refresh vs 30min vs 5min (DEC-F3.2-04)

**Trade-off**: 50min (chosen, DEC-SUC-03) deja 10min safety margin vs TTL 3600s. 30min deja 30min margin (más seguro) pero más refreshes/hora. 5min (F2.2 baseline) es 12x/hora desperdicio.

**Decisión**: 50min per DEC-SUC-03 verbatim (plan.md:418). Safety margin de 10min es aceptable para kiosko desatendido + retries reactivos vía handle401.

### 13.3 Pre-flight regex vs per-endpoint config (DEC-F3.2-03)

**Trade-off**: Regex (chosen) es single source of truth + cero boilerplate. Per-endpoint config (e.g., decorator en cada caller) permite opt-in explícito pero drift risk + boilerplate.

**Decisión**: Regex matchea `/facturacion/*` + `/caja/arqueo*` per DEC-SUC-03. Constante módulo-level `PRE_FLIGHT_PATHS` permite extension via DEC-F3.2-10. Single source of truth.

### 13.4 Pre-flight en todos los POST vs solo críticos

**Trade-off**: Aplicar pre-flight a TODOS los POST garantiza zero 401 mid-write pero degrada UX (~50-150ms overhead en cada request). Solo críticos (chosen) optimiza UX pero requiere whitelist explícito.

**Decisión**: Solo críticos per DEC-SUC-03 (pago + arqueo). `handle401` reactivo cubre los no-críticos (catálogos read, sync, etc.).

### 13.5 Refresh configurable via UI vs hardcoded

**Trade-off**: Hardcoded (chosen) es simple + no surface area. UI configurable permite ajuste por sucursal pero requiere persist + UI surface + drift risk.

**Decisión**: Hardcoded 50min per DEC-SUC-03. Env var `PARKOS_REFRESH_INTERVAL_MS` es forward hook si negocio requiere override en deployment específico.

### 13.6 e2e sandbox F.6 SKIP vs CI override

**Trade-off**: SKIP-env (chosen, F2.x + F3.1 precedent) evita CI rotura pero deja e2e sin coverage local. CI override requiere Docker + npm compatible image.

**Decisión**: SKIP-env documentado como deviation D-env en `verify-report.md`. Unit tests + axe-core source-level SÍ corren. CI con image compatible (npm 11.16+) verde en local dev.

---

## 14. Precedents

| Precedent | Aplicación F3.2 | Source |
|---|---|---|
| **F3.1 (Login email+password)** | Container/Presentational split + Zod local + i18n keys + 401 anti-enumeration + e2e axe-core pattern + DELTA stub precedent | `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` |
| **F2.2 (parkosFetch + authStore + useAuth)** | Mutex singleton preserved + refresh-once 401 invariant + SWR `refreshInterval` baseline (5min F3.2 cambia a 50min) + `expiresAt` ISO 8601 + `setTokens`/`clear`/`refreshAccessToken` Mutex | `apps/ui-kit/src/{fetch/parkosFetch.ts, store/authStore.ts, hooks/useAuth.ts}` |
| **F2.1 (Electron skeleton + shadcn)** | vitest + @testing-library/react + axe-core + playwright e2e pattern + i18n 7 namespaces | `apps/electron-sucursal/src/renderer/components/ui/` + `e2e/a11y/wcag-2.1-aa.spec.ts` |
| **F1.15 (login histórico)** | DELTA precedent (user-facing behavior in spec) → F3.2 emite 6 new REQ-OPS-113..118 | `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/specs/operations/spec.md` |
| **F1.13 (arqueo defense in depth XR6)** | 5-layer defense in depth pattern (auth + engineering + a11y + contract + retry-budget) — F3.2 contributes a11y (countdown WCAG) + retry-budget (pre-flight) layers | `openspec/specs/operations/spec.md:3951` |
| **DEC-SUC-03** | Refresh 50min + pre-flight antes de pago/arqueo — F3.2 implementa verbatim | `plan.md:418` |
| **DEC-FETCH-03** | Mutex singleton `refreshAccessToken` — F3.2 pre-flight REUSA el mismo Mutex | `apps/ui-kit/src/store/authStore.ts:100-128` |
| **DEC-ELEC-10 + DEC-FETCH-10 + DEC-UPD-13** | F2.x NO-OP stub precedent — F3.2 ROMPE porque user-facing (DELTA) | F2.1/F2.2/F2.3 archive reports |
| **F3.1 DEC-F3.1-11** | DELTA verdict precedent (7 new REQ-OPS-106..112) — F3.2 replica con 6 new REQ-OPS-113..118 | `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/proposal.md §5.11` |

### 14.1 DEC-F3.2-08 + DEC-F3.2-11 verdict ratificación

F3.2 ES user-facing behavior observable: (a) countdown visual decreciente cada 1000ms (clock visible al operador); (b) form disabled durante lockout (interacción observable); (c) pre-flight gate evita 401 mid-write en `/facturacion/*` + `/caja/arqueo/*` (latency + correctness observable); (d) refresh 50min automático (session longevity observable).

Per F1.15 + F3.1 precedent, user-facing ⇒ spec delta materialized. F3.2 emite 6 new REQ-OPS-113..118 en `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md` siguiendo Given/When/Then/And RFC 2119 format F1.15 + F3.1 verbatim.

F2.x NO-OP precedent (DEC-ELEC-10, DEC-FETCH-10, DEC-UPD-13) NO aplica a F3.2 — esos HU son infra-only sin behavior visible al operador. F3.2 ES UI + UX behavior, rompe el precedent siguiendo F3.1.

---

## 15. DoD checklist (preliminar)

- [ ] 4 atomic commits landed (`feat(auth): useCountdown hook`, `feat(auth): integrar useCountdown en LoginForm`, `feat(refresh): 50min SWR + pre-flight gate`, `test(electron): 4 e2e lockout`).
- [ ] 6 new REQ-OPS-113..118 materializadas en `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md` (sdd-spec phase).
- [ ] Given/When/Then/And format RFC 2119 per F3.1 precedent verbatim.
- [ ] Anchor links explícitos a DEC-F3.2-NN ratificados en §4.
- [ ] 6 acceptance gates PASS source-level (G1 + G2 regression + G3 + G4 + G5 + G7) + G6 SKIPPED-env documentado como D-env (NO project defect) per F.6 precedent.
- [ ] axe-core 0 violaciones WCAG 2.1 AA en LoginForm durante countdown state (A1 e2e + G3 unit test).
- [ ] useCountdown hook exportado desde `features/auth/hooks/useCountdown.ts` consumible por F4.x/F11.x (forward hooks §12).
- [ ] REFRESH_INTERVAL_MS constante exportada desde `useAuth.ts` (testabilidad).
- [ ] PRE_FLIGHT_PATHS constante módulo-level extensible via DEC-F3.2-10.
- [ ] parkosFetch Mutex singleton preserved (F2.2 DEC-FETCH-03 invariant intacto).
- [ ] useAuthStore.expiresAt ISO 8601 UTC consumible por pre-flight gate.
- [ ] i18n `auth.json` agrega 3 keys countdown (`lockoutCountdown`, `lockoutReEnable`, `lockoutLabel`) — snapshot test verde.
- [ ] 0 KNOWN-MISSING (pre-flight 10/10 PASS exploration §3).
- [ ] Author: `Parkos Dev <dev@parkos.local>` (F2.1 + F3.1 verbatim precedent).
- [ ] Conventional commits sin Co-authored-by, sin AI trailers.
- [ ] Numeración REQ-OPS monotónica verificada (REQ-OPS-112 vigente post-F3.1; F3.2 ocupa REQ-OPS-113..118, 0 gaps).
- [ ] READ-ONLY anchors respetados: backend `auth.py`, `parkos_core` schemas, electron main/preload/bridge, `apps/electron-sucursal/electron/*`, `i18n/index.ts`, `apps/ui-kit/src/{cn,tokens,store/authStore,fetch/parkosFetch (except T3 modifications),hooks/useAuth (except T3 modification)}.ts`.
- [ ] Sandbox F.6 caveat documentado en §10 + §15 como deviation esperada D-env (e2e SKIPPED-env), NO project defect.

---

## 16. Open questions

**Resoluciones de inconsistencies detectadas en exploration §1**:

1. **I1 — `max_intentos_login` 4 vs 5**: `plan.md:1309` dice "5 intentos fallidos". User orchestrator prompt dice "4 attempts". Backend default es 5 per `auth.py:225`. **Resolution** (cerrada en DEC-F3.2-09): e2e usa `max_intentos_login - 1` intentos fallidos + 1 intento que recibe 429, configurable via env con default 4 (rápido para test). MSW/page.route mockea 429 después de N intentos. NO requiere cambio backend.

2. **I2 — `refreshInterval` 5min vs 50min**: `useAuth.ts:60` tiene `5 * 60 * 1000`. `plan.md:1311` dice "pasan 50 minutos desde el último refresh". **Resolution** (cerrada en DEC-F3.2-04): T3 MODIFY `useAuth.ts:60` para cambiar a `50 * 60 * 1000`. Constante exportada `REFRESH_INTERVAL_MS` para testabilidad. Constante exportada permite tests deterministas.

3. **I3 — `/caja/arqueo` no existe todavía**: `plan.md:1311` menciona pre-flight para `/caja/arqueo`. `modelo_datos_er.mmd` no tiene tabla `caja.arqueo` (arqueos viven en Fase 10 per `pending.md:51`). **Resolution** (cerrada en DEC-F3.2-10): pre-flight gate es genérico — matchea `/\/facturacion(\/|$)|\/caja\/arqueo/`. F3.2 cubre `/facturacion/*` que existe post-F1.8 (REQ-OPS-030). `/caja/arqueo*` se incluye en la regex aunque el endpoint aún no exista — cuando Fase 10 introduzca arqueos, el gate ya está cubriendo. Forward extensibility via `PRE_FLIGHT_PATHS_EXTENDED` si F3.3+ decide agregar `/caja-sesion/*`.

**Notas para `sdd-verify`**:

- **N1**: tsc clean post-T3 — verificar que `apps/ui-kit/tsconfig.*` compila sin errores después de modificar `useAuth.ts` + `parkosFetch.ts`.
- **N2**: axe-core 0 violaciones en `<LoginForm>` durante countdown state — REQ-OPS-118 gate. Verificar que el axe-core scan no reporta violaciones de WCAG 2.1 AA (color contrast, aria-live polite, role=status, aria-label).
- **N3**: MSW 2.x setup in lockout.spec.ts — F3.2 introduce MSW mock para 429 response con Retry-After header. Verificar que el setup MSW no rompe los tests existentes (F3.1 `loginApi.test.ts` + `login.spec.ts`).
- **N4**: `useAuthStore.expiresAt` parseable en concurrent renders — Zustand setState es síncrono pero el SWR key change puede disparar re-renders concurrentes. Verificar que `Date.parse(expiresAt)` retorna timestamp válido en pre-flight check.
- **N5**: parkosFetch pre-flight Mutex shared with 401 path — verificar que el mismo `refreshAccessToken()` Mutex es reusado por pre-flight gate + handle401, sin doble refresh.

**0 KNOWN-MISSING** (pre-flight 10/10 PASS + 0 KNOWN-MISSING en exploration §16). Items N1..N5 son verificaciones standard en `sdd-verify`, NO blockers.

---

## CHANGELOG

- (2026-09-15) F3.2 propose phase complete — 16 secciones + CHANGELOG, 11 DEC-F3.2-01..11 (DEC-F3.2-11 NUEVA, esta proposal), 8 riesgos R1..R8, 6 acceptance gates G1..G6, 4 atomic tasks T1..T4, 1 cluster C1. Numeración REQ-OPS monotónica verificada: REQ-OPS-112 vigente post-F3.1 archive; F3.2 ocupa REQ-OPS-113..118 (6 new requirements, 0 gaps). Pre-flight 10/10 PASS + 0 KNOWN-MISSING. DEC-F3.2-08 + DEC-F3.2-11 verdict = **DELTA** (F3.2 IS user-facing: countdown visual + form disabled + pre-flight gate + 50min refresh). 3 inconsistencies (I1 max_intentos 4 vs 5; I2 refreshInterval 5min → 50min; I3 `/caja/arqueo` no existe) cerradas en DEC-F3.2-04, DEC-F3.2-09, DEC-F3.2-10. Sandbox F.6 deviation esperada documentada en §10 + §15 (e2e SKIPPED-env, NO project defect). Precedente directo: F3.1 archivado 2026-09-15 con 7 REQ-OPS-106..112 user-facing DELTA — F3.2 replica pattern con 6 REQ-OPS-113..118. Ready for `sdd-spec` + `sdd-design` (paralelo).

---

**End of proposal — HU-F3.2.**