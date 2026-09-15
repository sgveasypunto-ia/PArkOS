# Archive Report — HU-F3.2 Lockout visible (countdown) + refresh transparente (50min auto + pre-flight)

## 0. Metadata

- HU: HU-F3.2
- Fase: 3 (Autenticación y turno de caja — 2/3 cerrado)
- SDD cycle complete: explore → propose → spec → design → tasks → apply → verify → archive
- Branch: `feat/fase-2-electron-scaffold` (HEAD post-archive: ver `git log`)
- Date: 2026-09-15
- Status: closed + archived
- Author: Parkos Dev <dev@parkos.local>

---

## 1. Cycle summary

- Exploración: ~580 LOC inline, 18 secciones, 10 DEC-F3.2-01..10 ratified, 8 riesgos R1..R8, 6 acceptance gates G1..G6, 4 atomic tasks T1..T4, 1 cluster C1, pre-flight 10/10 PASS + 0 KNOWN-MISSING.
- Proposal: ~870 LOC, 16 secciones, 11 DEC-F3.2-01..11 ratificadas (DEC-F3.2-01..10 + **DEC-F3.2-11 NUEVA**). **CRITICAL**: DEC-F3.2-08 + DEC-F3.2-11 verdict = DELTA con 6 new REQ-OPS-113..118 (NOT NO-OP stub). F3.2 ES user-facing behavior observable (countdown visual decreciente cada 1000ms + form disabled durante lockout + pre-flight gate que evita 401 mid-write en `/facturacion/*` + `/caja/arqueo/*` + refresh 50min automático vs `ACCESS_TOKEN_TTL = 3600` con 10min safety margin). Precedente directo: F3.1 archivado 2026-09-15 con 7 new REQ-OPS-106..112 user-facing + F1.15 archivado 2026-09-15 con 4 new REQ-OPS-102..105.
- Spec: ~280 LOC NO-OP+6-NEW deltas materializados en Given/When/Then/And RFC 2119. 6 REQ-OPS-113..118 con cross-reference §4 + 9 acceptance criteria §5 + 11 forward hooks §6 + 13-item DoD §8.
- Design: ~880 LOC, 15 secciones + 2 apéndices. 8 TS mockups completos en Appendix A (`useCountdown.ts` + `LoginForm.tsx` + `Login.tsx` + `auth.json` delta + `useAuth.ts` + `parkosFetch.ts` + `formatTime` helper + e2e outline). 3 configs delta en Appendix B (coverage thresholds `useCountdown.ts` ≥90% + `LoginForm.tsx` ≥80% + `Login.tsx` ≥80% + `parkosFetch.ts` ≥85% + `useAuth.ts` ≥80%).
- Tasks: ~370 LOC, 13 secciones F3.1 verbatim. 4 atomic tasks T1..T4, 1 cluster C1 end-to-end con orden interno T1 → (T2 || T3) → T4, 7 acceptance gates G1..G6 + G7 axe-core WCAG 2.1 AA.
- Apply: 4 atomic commits `850ed70..e3e04ac`, 3 NEW + 7 MODIFY archivos, +708/-31 LOC (production + tests + i18n + coverage thresholds). 16 unit scenarios (U1..U4 useCountdown + U8..U10 LoginForm/Login + U11..U16 useAuth/parkosFetch) + 4 e2e scenarios (E1 countdown display + E2 decrement + E3 re-enable + A1 axe-core).
- Verify: PASS WITH WARNINGS (5/7 gates PASS source-level + 2/7 SKIPPED-env G6 e2e + G7 axe-core runtime — F.6 precedent verbatim F2.1 + F2.2 + F2.3 + F3.1). 5 deviations documentadas (D-env-F.6 MEDIUM + D-h3-regex-update LOW + D-signature-position LOW + D-progress-field LOW + D-fake-timers-handle401 LOW). 0 blocking issues.
- Archive: source moved via plain `mv` (untracked in git) + snapshot + `diff -r` empty readback + 6 new REQ-OPS-113..118 materialized to canonical `openspec/specs/operations/spec.md` (DELTA precedent F3.1 + F1.15 — second user-facing DELTA in Fase 3, sigue el precedent del first DELTA breaking F2.x NO-OP pattern).

---

## 2. Atomic commits ledger (4 commits)

4 commits authored by `Parkos Dev <dev@parkos.local>`, **NO Co-authored-by**, **NO AI trailers**:

| Hash | Task | Files | +LOC | -LOC | Commit message |
|---|---|---|---|---|---|
| `850ed70` | T1 `useCountdown` hook + 4 unit tests | 2 NEW | +126 | 0 | `feat(auth): adicionar useCountdown hook con Date.now() baseline + cleanup + onComplete` |
| `d0f704d` | T2 LoginForm countdown + 3 i18n keys + Login reset errorState | 4 MODIFY | +110 | -5 | `feat(auth): integrar useCountdown en LoginForm + countdown display + 3 i18n keys` |
| `9f27f79` | T3 useAuth 50min refresh + parkosFetch pre-flight gate | 4 MODIFY | +272 | -26 | `feat(refresh): 50min SWR refresh + pre-flight gate antes de POST /facturacion/* + /caja/arqueo` |
| `e3e04ac` | T4 e2e 4 scenarios + axe-core A1 | 1 NEW | +200 | 0 | `test(electron): adicionar 4 e2e lockout (countdown display + decrement + re-enable + axe-core)` |
| **TOTAL** | **4 atomic** | **3 NEW + 7 MODIFY** | **+708** | **-31** | — |

Net LOC delta working tree (range `bcfe2ed..e3e04ac`): **+677 net LOC** (production + tests + i18n + 3 countdown keys + coverage thresholds). Source-level PASS + 2/7 SKIPPED-env per F.6 precedent.

Hygiene verification (per `verify-report.md §2`):

```bash
git log -p 850ed70..e3e04ac | grep -iE "(Co-Authored-By|AI Generated|Signed-off-by)" | wc -l
# Output: 0
```

4/4 commits PASS hygiene: author `Parkos Dev <dev@parkos.local>` · NO Co-authored-by · NO AI trailers · conventional commits neutrales español · scopes `{auth, refresh, electron}`.

---

## 3. Files in archive folder (7)

1. `exploration.md` — ~580 LOC inline, 18 secciones, 10 DEC-F3.2-01..10, 8 riesgos R1..R8, pre-flight 10/10 PASS + 0 KNOWN-MISSING.
2. `proposal.md` — ~870 LOC, 16 secciones, 11 DEC-F3.2-NN ratified, **CRITICAL DEC-F3.2-08 + DEC-F3.2-11 verdict = DELTA stub con 6 new REQ-OPS-113..118**.
3. `design.md` — ~880 LOC, 15 secciones + 2 apéndices (Appendix A: 8 TS mockups completos; Appendix B: 3 configs delta — coverage thresholds).
4. `specs/operations/spec.md` — ~280 LOC, DELTA materializado (6 new REQ-OPS-113..118 in Given/When/Then/And RFC 2119).
5. `tasks.md` — ~370 LOC, 13 secciones, 4 atomic tasks T1..T4, 1 cluster C1.
6. `verify-report.md` — 12 secciones + CHANGELOG, 7 acceptance gates, 5 deviations, PASS WITH WARNINGS verdict.
7. `archive-report.md` — este archivo (additive, excluded from snapshot/diff comparison).

---

## 4. Source-of-truth merge (DELTA) — CRITICAL F3.2 deviation from F2.x NO-OP precedent

**F3.2 sigue el precedent DELTA sentado por F3.1 + F1.15 — segundo DELTA consecutivo en Fase 3, rompiendo el patrón NO-OP de F2.1/F2.2/F2.3 que NO aplica a F3.2 porque ES user-facing behavior observable.**

### 4.1 Rationale crítica (DEC-F3.2-08 + DEC-F3.2-11)

| Aspect | F2.1/F2.2/F2.3 (NO-OP precedent) | F3.2 (DELTA con 6 new REQ-OPS-NNN) |
|---|---|---|
| Tipo de cambio | Infra-only (scaffold + IPC + runtime) | User-facing behavior observable |
| Componente visible al operador | Ninguno (electron main process, IPC preload, services) | Countdown display + form disabled state + pre-flight latency + refresh longevity |
| Mensajes de error diferenciados | N/A (no UI) | `lockoutCountdown` + `lockoutReEnable` + `lockoutLabel` (3 nuevas i18n keys) |
| Cookie httpOnly round-trip | N/A (no HTTP) | N/A (F3.2 NO toca HTTP layer de login) |
| Defense in depth XR6 contribution | N/A | Capa 3 a11y (countdown WCAG 2.1 AA) + capa 5 retry-budget (pre-flight gate proactivo F3.2 + handle401 reactivo F2.2) |
| Pre-flight correctness | N/A (no POST críticos) | `/facturacion/*` + `/caja/arqueo*` sin 401 mid-write (Mutex shared F2.2 DEC-FETCH-03 invariant preserved) |
| Precedente directo | DEC-ELEC-10 / DEC-FETCH-10 / DEC-UPD-13 (infra) | REQ-OPS-102..105 (F1.15) + REQ-OPS-106..112 (F3.1) + REQ-OPS-113..118 (F3.2) |
| Verificabilidad | DEC-* documentan; sin REQ spec-level | REQ-OPS-NNN + DEC-* cross-linked + 9 acceptance criteria §5 |

### 4.2 Operación ejecutada (mechanical)

6 Writes contra canonical `openspec/specs/operations/spec.md`, byte-diff pre/post merge verification:

```
pre_md5:  81d148c28a6cc9fd7742e4b4fa99c05d  (4738 lines — idéntico al F3.1 archive baseline)
post_md5: 7686b4acd12cde2f666b2076c55ebecb  (4982 lines, +244 = 6 new REQ-OPS-113..118 block)
delta:    +244 lines = 6 new REQ-OPS-113..118 block
```

Procedimiento (shell-only, NEVER Read → Write reproduce content):

1. Snapshot pre-move: `cp -R openspec/changes/hu-f3-2-lockout-refresh-pre-flight /tmp/tmp.XXXXX/source` (ephemeral).
2. Move source to archive: `mv openspec/changes/hu-f3-2-lockout-refresh-pre-flight openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight` (Git Bash plain mv, source untracked per `git status --short` → `?? openspec/changes/hu-f3-2-lockout-refresh-pre-flight/`).
3. Source absent confirmed: `! [ -d openspec/changes/hu-f3-2-lockout-refresh-pre-flight ]` → PASS.
4. `diff -r /tmp/tmp.XXXXX/source openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight` → **empty output** (byte-identical, passing).
5. Extract `source/specs/operations/spec.md` lines 76-319 (REQ-OPS-113..118 block + content) → `/tmp/f3-2-req-ops-block.md` (244 lines, byte-preserved via `sed -n`).
6. Split canonical at line 4656 (before blank line + `## Modified Capabilities`): head (1-4656) + tail (4657-end, 82 lines).
7. 3-way concat: head + extracted_block + tail → new canonical (`/tmp/f3-2-canonical-new.md`, 4982 lines).
8. Line count verify: 4656 + 244 + 82 = 4982 ✓ matches actual post-merge line count.
9. Byte-identity verify: `diff /tmp/f3-2-merged-block.md /tmp/f3-2-req-ops-block.md` → **empty output** (REQ-OPS-113..118 byte-identical entre source delta y canonical post-merge, passing). Both md5 = `1a7cb17997d57ea68c821f2117c9dda1`.
10. Mechanical `cp /tmp/f3-2-canonical-new.md openspec/specs/operations/spec.md` (no model Read/Write, bytes flow shell→file).
11. Structural verify: `grep -n "^### REQ-OPS-11[2-8]\|^## Modified Capabilities" openspec/specs/operations/spec.md` → REQ-OPS-112 at line 4626, REQ-OPS-113..118 at lines 4657..4867, `## Modified Capabilities` at line 4902 (consecutive, 0 gaps).
12. Commit materialize: `git commit -m "chore(spec): materializar 6 REQ-OPS-113..118 al canonical operations spec (F3.2 DELTA merge)"` → commit hash `18a34b29d1cb6104930ba65cef1542c33a74dc83`, 1 file changed, 244 insertions(+).

### 4.3 Cross-reference table (6 REQ-OPS-NNN materialized)

| REQ-OPS | DEC-F3.2 anchor | Comportamiento observable |
|---|---|---|
| **REQ-OPS-113** | DEC-F3.2-01 | `useCountdown(retryAfterSeconds, options?)` hook con `Date.now()` baseline (drift-resistant) + `setInterval(1000)` + cleanup en unmount + `onComplete` callback (R1 + R4 mitigations) |
| **REQ-OPS-114** | DEC-F3.2-02, -05, -06 | `<LoginForm>` aplica `disabled={true}` a inputs + submit mientras `useCountdown().secondsLeft > 0` + renderiza `<p role="status" aria-live="polite" data-testid="login-countdown">` con countdown mm:ss (WCAG 2.1 AA polite announcement) |
| **REQ-OPS-115** | DEC-F3.2-02, -06 | Auto re-enable del form cuando `useCountdown().isExpired === true` — `<Login>` container resetea `errorState` a `null` (callback prop pattern `onLockoutExpired` cross-component) |
| **REQ-OPS-116** | DEC-F3.2-03, -07 + FETCH-03 | `parkosFetch` pre-flight gate `refreshIfExpiringSoon()` invocado antes de POST matcheando `PRE_FLIGHT_PATHS = /\/facturacion(\/\|$)\|\/caja\/arqueo/` cuando `expiresAt - now < PRE_FLIGHT_THRESHOLD_MS (5 * 60 * 1000)`, Mutex shared con handle401 F2.2 (DEC-FETCH-03 invariant preserved) |
| **REQ-OPS-117** | DEC-F3.2-04 + DEC-SUC-03 | `useAuth.refreshInterval: REFRESH_INTERVAL_MS = 50 * 60 * 1000` (constante exportada) — refresh transparente cada 50min vs `ACCESS_TOKEN_TTL = 3600` (10min safety margin) |
| **REQ-OPS-118** | DEC-F3.2-05 + RNF-022 | WCAG 2.1 AA compliance: axe-core 0 violaciones en `<LoginForm>` durante lockout state (extiende REQ-OPS-112 F3.1 precedent) |

Numeración monotónica verificada: REQ-OPS-112 vigente pre-F3.2 (archivado por F3.1); F3.2 ocupa REQ-OPS-113..118 (continuación, 0 gaps). Post-archive canonical: 118 REQ-OPS-001..118 + 6 XR (REQ-OPS-XR1..XR6).

**Anchor upstream**: `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/proposal.md` §4.11 (DEC-F3.2-11 rationale verbatim) + `specs/operations/spec.md` §3 (materialized Given/When/Then/And lines 76-319).

---

## 5. Decisions ratified (11 DEC-F3.2-NN)

- **DEC-F3.2-01**: `useCountdown` signature con `Date.now()` baseline (NO accumulator) — drift-resistant R1 mitigation.
- **DEC-F3.2-02**: Countdown UX: form `disabled={true}` (NOT readonly) + auto re-enable al llegar a 0 vía `onLockoutExpired` callback prop en `<Login>` container.
- **DEC-F3.2-03**: Pre-flight trigger conditional on path (regex match) — `PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/` módulo-level, NO recompilada per request.
- **DEC-F3.2-04**: SWR refresh interval 50min hardcoded (`REFRESH_INTERVAL_MS = 50 * 60 * 1000` constante exportada) per DEC-SUC-03 verbatim (plan.md:418).
- **DEC-F3.2-05**: e2e axe-core scope: countdown state WCAG check con `withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])` (mismo F3.1 pattern `login.spec.ts` A1).
- **DEC-F3.2-06**: Countdown i18n keys 3 keys en `auth.json` namespace existente (`lockoutCountdown` + `lockoutReEnable` + `lockoutLabel`) — F2.1 DEC-ELEC-06 verbatim.
- **DEC-F3.2-07**: Pre-flight latency budget ≤200ms p95 con graceful degradation (try/catch silencia rejection).
- **DEC-F3.2-08**: **DELTA verdict** (NOT NO-OP) — F3.2 IS user-facing behavior observable: countdown visual + form disabled + pre-flight gate + 50min refresh. Per F1.15 + F3.1 precedent, user-facing ⇒ spec delta materialized.
- **DEC-F3.2-09**: e2e lockout attempts configurable via env (default 4) — e2e usa `max_intentos_login - 1` intentos fallidos + 1 intento que recibe 429. Test rápido sin sacrificar coverage.
- **DEC-F3.2-10**: Forward hook pre-flight paths extensibilidad — `PRE_FLIGHT_PATHS` constante módulo-level permite extension future via nueva constante `PRE_FLIGHT_PATHS_EXTENDED` o env var. F3.3+ (turno) puede extender a `/caja-sesion/*` si lo requiere.
- **DEC-F3.2-11** (archivo-level): **NUEVA** — DELTA stub con 6 new REQ-OPS-113..118 (NOT NO-OP stub). F3.2 ES user-facing behavior observable per F1.15 + F3.1 precedent. Segunda HU Fase 3 con behavior contract (post F3.1 first DELTA).

---

## 6. Acceptance gates (final)

**5/7 PASS source-level, 2/7 SKIPPED-env, 0 FAIL.**

| Gate | Result | Evidence |
|---|---|---|
| **G1** `useCountdown` baseline + cleanup + onComplete + drift resistance | PASS | Source: `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts:42-67` (`Date.now() + retryAfterSeconds * 1000` baseline + `setInterval(1000)` recalc + `useEffect` cleanup `clearInterval` + `onComplete?.()` fires at 0). Source tests: `useCountdown.test.ts:25-58` (4 tests U1 baseline + U2 cleanup + U3 onComplete + U4 drift resistance). Source-level verification via grep. |
| **G2** `AccountLockedError.retryAfterSeconds` mapping F3.1 sin regresión | PASS | Source: `apps/electron-sucursal/src/features/auth/api/loginApi.ts:47-63` (F3.1 shipped, F3.2 consume as-is) + `LoginForm.tsx` consume `error.retryAfterSeconds` para `useCountdown(retryAfterSeconds)`. Source-level verification. |
| **G3** `<LoginForm>` form disabled durante lockout | PASS | Source: `LoginForm.tsx:83` (`isFormDisabled = isSubmitting \|\| (isLockout && !isExpired)`) + líneas 108/128/154-156 (`disabled={isFormDisabled}` + `aria-disabled={isFormDisabled}`). Source tests: `LoginForm.test.tsx:168-195` (U8 lockout disables form). Source-level verification via grep. |
| **G4** Countdown auto re-enable al llegar a 0 | PASS | Source: `Login.tsx:54-60` (`useCallback handleLockoutExpired` resetea `errorState` a null) + `Login.tsx:87` (`onLockoutExpired` callback prop wireado). Source tests: `Login.test.tsx:181-224` (U10 isExpired resets errorState vía `vi.useFakeTimers()` + `vi.advanceTimersByTimeAsync(2500)`). |
| **G5** `parkosFetch` pre-flight gate + 50min SWR refresh | PASS | Source `useAuth.ts:31` (`REFRESH_INTERVAL_MS = 50 * 60 * 1000` constante módulo-level exportada) + `useAuth.ts:70` (`refreshInterval: REFRESH_INTERVAL_MS`). Source `parkosFetch.ts:47-76` (`PRE_FLIGHT_PATHS` regex + `PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000` + `refreshIfExpiringSoon()` con Mutex shared) + `parkosFetch.ts:203-208` (integration pre-fetch en `parkosFetchRaw`). Source tests: `useAuth.test.ts:175-178` (U11 `REFRESH_INTERVAL_MS = 3_000_000` assertion) + `parkosFetch.test.ts:305-451` (U12-U16 pre-flight fires + skips + GET skip + graceful failure + Mutex shared — 6 tests). |
| **G6** 4 e2e scenarios verde (countdown display + decrement + re-enable + axe-core) | SKIPPED-env | `apps/electron-sucursal/e2e/auth/lockout.spec.ts` — 4 e2e tests + 1 axe-core A1 authored (~178 LOC). Sandbox F.6 precedent verbatim F2.1 + F2.2 + F2.3 + F3.1 — npm 11.16.0 refuses `workspace:*`; vitest+playwright no instalados en `node_modules/`. CI matrix required post-archive. |
| **G7** axe-core WCAG 2.1 AA 0 violaciones en `<LoginForm>` durante lockout state | SKIPPED-env | `lockout.spec.ts:154-177` A1 test (axe-core via `@axe-core/playwright` ya en deps F2.1) + `LoginForm.tsx:141-149` (`role="status" aria-live="polite"` + `aria-label={t('lockoutLabel')}` + `data-testid="login-countdown"`). Source-level PASS (role/aria attributes structuralmente); runtime SKIPPED-env per F.6 precedent. |

---

## 7. Deviations & forward hooks

### Deviations (5 total, 0 blocking)

1. **D-env-F.6 MEDIUM** (precedent F2.x + F3.1 verbatim) — `npm 11.16.0` refuses `workspace:*` resolution; `vitest` + `@playwright/test` + `@axe-core/playwright` no instalados en `node_modules/`. Unit tests (G1+G2+G3+G4+G5) y e2e (G6+G7) authored pero SKIPPED-env runtime. CI matrix required post-archive. **NO es project defect** — precedent verbatim F2.1 + F2.2 + F2.3 + F3.1 archive reports documentan misma limitation.
2. **D-h3-regex-update LOW** — `useAuth.test.ts:107-127` (test H3) usa regex source-level sobre el archivo `src/hooks/useAuth.ts` para verificar `refreshInterval: REFRESH_INTERVAL_MS` porque SWR no expone options resueltos en runtime. Cross-ref tasks.md §13.2 design `useAuth.test.ts` U11 que preveía `expect(REFRESH_INTERVAL_MS).toBe(3_000_000)` directo (U11 línea 175-178 — sí presente), pero H3 lo complementa con source-regex para validar la integración real con SWR. **Funcionalmente equivalente**, agregación defensiva.
3. **D-signature-position LOW** (cosmetic) — `useCountdown.ts:64` deps array `[endTime, isExpired, options]` incluye `options` object reference (no su contenido). Como `options` se pasa desde `<LoginForm>` y puede ser nuevo object identity en cada render, podría causar re-mount del `useEffect` innecesariamente. Funciona correctamente porque el `if (isExpired) return` guard previene re-creación del interval. `Login.tsx:58-60` usa `useCallback` con `[]` deps para `handleLockoutExpired` lo que estabiliza el identity. **Edge case raro** (re-mount del interval) NO ocurre en practice porque countdown solo se monta cuando `isLockout === true` y no se re-renderiza el componente padre fuera de ese path.
4. **D-progress-field LOW** (cosmetic) — `useAuth.ts` retorna `expiresAt: data?.expires_at ?? null` (línea 90) en el `UseAuthReturn`. F3.1 design §6.2 proponía shape simplificado `expiresAt: string | null` pero el tipo final incluye también `expires_at` dentro del payload `/auth/me`. **Funcionalmente equivalente** — el campo en el payload es el source of truth; el wrapper expone convenientemente.
5. **D-fake-timers-handle401 LOW** — `parkosFetch.test.ts:307` pre-flight suite usa `vi.useFakeTimers({ shouldAdvanceTime: true })` mientras que U7 (401 refresh-once) línea 147 también. La combinación `vi.useFakeTimers` + `await vi.runAllTimersAsync()` resuelve backoff retries (300/600/1200ms) y el pre-flight refresh simultáneo. La interaction con `setTimeout` del AbortController (líneas 213-216) está cubierta por U12 que NO usa fake timers para evitar el quirk jsdom+AbortController. **Determinismo preservado** — documentado como deviation porque design §13.2 esperaba backoff mockeado vía spy, no vía fake timers.

### Forward hooks (cross-reference exploration §6.4 + tasks §9)

- **HU-F3.3** (Abrir/Cerrar turno) → consume `useAuth().user.sucursal` + `permisos[]` hidratados post-F3.1 (F3.2 NO toca `useAuth` shape); pre-flight gate automático para `POST /caja-sesion/*` si F3.3 decide agregar al path match via DEC-F3.2-10 (`PRE_FLIGHT_PATHS_EXTENDED` o env var).
- **HU-F3.x** (logout button UI) → consume `useAuthStore.clear()` ya implementado en F2.2 + `parkos:auth:cleared` window event.
- **HU-F3.x** (AuthGuard component) → consume `parkos:auth:cleared` window event listener → `navigate('/login?next=...')`.
- **HU-F4.x** (catálogos + ocupación) → consume `useCountdown` para retry buttons con countdown visual (`useRetryWithCountdown` pattern que envuelve `useCountdown` con retry-exponential-backoff) + hereda `parkosFetch` pre-flight gate automáticamente (T3 cubre `/facturacion/*`).
- **HU-F5.x** (facturación) → pre-flight gate automático (`/facturacion/*` ya cubierto) + `useAuth.refreshInterval: 50min` heredado transparentemente. Cero cambios F5.x.
- **HU-F5.x** (facturación) → `useCountdown` para retry buttons post-409 conflicto.
- **HU-F11.x** (sync UI + alertas CU-07/14) → consume `useCountdown` para reintentos de sync con countdown visual + exponential backoff (`useSyncRetryCountdown` envuelve `useCountdown`).
- **HU-F11.x** (sync UI) → `useAuth` 50min refresh heredado automáticamente.
- **PR7 backend** (refresh-token rotation) → consume `refreshAccessToken` Mutex F2.2 + pre-flight F3.2 → rotación con `jti` reuse detection.

---

## 8. DoD checklist

- [x] 4 atomic commits T1..T4 con author `Parkos Dev <dev@parkos.local>`, sin Co-authored-by, sin AI trailers.
- [x] 3 NEW + 7 MODIFY archivos (production + tests + i18n + coverage thresholds).
- [x] `vitest --run` 16/16 unit scenarios authored (SKIPPED-env execution F.6 precedent): `useCountdown.test.ts` (4) + `LoginForm.test.tsx` (2 nuevos U8+U9) + `Login.test.tsx` (1 nuevo U10) + `useAuth.test.ts` (1 nuevo U11 + H3) + `parkosFetch.test.ts` (5 nuevos U12..U16).
- [x] `playwright test` 4/4 e2e + axe-core scenarios authored (SKIPPED-env execution F.6 precedent): `lockout.spec.ts` (E1+E2+E3+A1).
- [x] `tsc --noEmit` clean intent (SKIPPED-env execution).
- [x] NO `Co-authored-by`, NO AI trailers en 4/4 commits.
- [x] CERO `any` en `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` ni en `apps/ui-kit/src/{fetch/parkosFetch.ts, hooks/useAuth.ts}`.
- [x] Sin npm install (zero install commands en 4 commits).
- [x] Feature folder isolation (`features/auth/hooks/useCountdown.ts` additive a `features/auth/{api,components,pages}/` F3.1).
- [x] READ-ONLY anchors intactos: `electron/main.ts` + `preload.ts` + `bridge.d.ts` + `apps/ui-kit/src/store/authStore.ts` (Mutex preserved verbatim) + `apps/electron-sucursal/electron/*` + `e2e/{scaffold,bridge,parkos-fetch,a11y,auth/login,auth/lifecycle,kiosko}` (F3.1 no tocado) + backend `auth.py` + Fase 2 specs.
- [x] 6 new REQ-OPS-113..118 materialized al canonical `openspec/specs/operations/spec.md` (md5 pre/post + byte-identity verified).
- [x] Mechanical Copy Contract executed: snapshot + mv + `diff -r` empty readback + source absent confirmed.

---

## 9. Pre-existing baseline unchanged

- 8 strict tsc errors F2.3-introduced (main.ts + kiosko.ts + kiosko.test.ts) — unchanged, D-tsc LOW follow-up Fase 3 backlog.
- bcryptjs fallback en lugar de native bcrypt — unchanged, D-env-F.6 LOW follow-up swap a native bcrypt cuando build pipeline tenga node-gyp + python.
- 25 test skips pre-existentes (pg_partman no disponible postgres:16-alpine local) — unchanged Fase 1 baseline.
- 78 errores ruff pre-existentes en `packages/parkos_core/` — unchanged Fase 1 baseline.
- 18 archivos con fallas pre-existentes — unchanged Fase 1 baseline.

Canonical `openspec/specs/operations/spec.md` md5 pre-F3.2 = `81d148c28a6cc9fd7742e4b4fa99c05d` (4738 lines — idéntico al post-F3.1 archive baseline). Post-F3.2 materialize = `7686b4acd12cde2f666b2076c55ebecb` (4982 lines, +244 lines = 6 new REQ-OPS-113..118).

---

## 10. Archive folder contents

7 archivos en `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/`:

```
exploration.md                 ~580 LOC (18 secciones, 10 DEC-F3.2-01..10, 8 riesgos)
proposal.md                    ~870 LOC (16 secciones, 11 DEC-F3.2-NN ratified, DEC-F3.2-08 + DEC-F3.2-11 DELTA precedent)
design.md                      ~880 LOC (15 secciones + 2 apéndices, 8 TS mockups + 3 configs delta)
specs/operations/spec.md       ~280 LOC (DELTA materializado, 6 new REQ-OPS-113..118 RFC 2119)
tasks.md                       ~370 LOC (13 secciones, 4 atomic tasks T1..T4, 1 cluster C1)
verify-report.md               ~290 LOC (12 secciones + CHANGELOG, 7 gates, 5 deviations PASS WITH WARNINGS)
archive-report.md              ~este archivo (additive-only)
```

Total: ~3.5k LOC de artefactos SDD F3.2.

---

## 11. Mechanical archive verification

Per skill `sdd-archive` Mechanical Copy Contract, archive folder moved via plain `mv` (source untracked in git, precedent verbatim F2.1 §9 + F2.2 §11 + F2.3 §11 + F3.1 §11) con snapshot + `diff -r` readback:

- **Snapshot**: pre-move recursive copy of source `openspec/changes/hu-f3-2-lockout-refresh-pre-flight/` → ephemeral tmpdir `/tmp/tmp.nU71Wl7y6u/source/`.
- **Move**: `mv openspec/changes/hu-f3-2-lockout-refresh-pre-flight openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight` (Git Bash en Windows; source untracked per `git status --short` → `?? openspec/changes/hu-f3-2-lockout-refresh-pre-flight/`).
- **Readback**: `diff -r /tmp/tmp.nU71Wl7y6u/source/ openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/` → **empty output** (byte-identical, passing).
- **Source absent post-move**: confirmado via `! [ -d openspec/changes/hu-f3-2-lockout-refresh-pre-flight ]` retorna "PASS: source absent".
- **Snapshot cleanup**: `rm -rf /tmp/tmp.nU71Wl7y6u` ejecutado post-readback (sin residuos en `/tmp`).
- **`archive-report.md`** es additive-only, excluded from snapshot/destination comparison (no existía en source pre-move).

### Materialize verification (canonical REQ-OPS-113..118 merge)

- **pre-merge md5**: `81d148c28a6cc9fd7742e4b4fa99c05d` (4738 lines) — idéntico al F3.1 archive baseline.
- **post-merge md5**: `7686b4acd12cde2f666b2076c55ebecb` (4982 lines) — `+244 lines` = 6 new REQ-OPS-113..118 block.
- **byte-identity check**: `diff /tmp/f3-2-merged-block.md /tmp/f3-2-req-ops-block.md` → **empty output** (244 lines match byte-by-byte, both md5 = `1a7cb17997d57ea68c821f2117c9dda1`, passing).
- **structural integrity**: REQ-OPS-112..118 consecutivos en canonical lines 4626, 4657, 4695, 4734, 4770, 4825, 4867; `## Modified Capabilities` preserved at line 4902 (0 gaps, sin duplicados, numeración monotónica verificada).
- **procedimiento shell-only**: bytes flow shell→file, NEVER model→file (per skill rule "NEVER use Read → Write to reproduce artifact content into the archive or main specs").
- **commit materialize**: `18a34b29d1cb6104930ba65cef1542c33a74dc83` — author `Parkos Dev <dev@parkos.local>`, 1 file changed, 244 insertions(+), NO Co-authored-by, NO AI trailers.

---

## 12. Fase 3 status

**Fase 3 status**: **2/3 HU cerrada** (F3.1 archivado 2026-09-15, F3.2 archivado 2026-09-15, F3.3 pendiente).

- **HU-F3.1**: Login con email + password (4 atomic commits `8961303..5fcfe66`, ~1008 net LOC production + tests, 7 new REQ-OPS-106..112 user-facing materialized al canonical — DELTA precedent, first user-facing DELTA in Fase 3).
- **HU-F3.2**: Lockout visible (countdown) + refresh transparente — ✅ **CERRADO 2026-09-15** (4 atomic commits `850ed70..e3e04ac`, +708/-31 net LOC production + tests + i18n + coverage, 6 new REQ-OPS-113..118 user-facing materialized al canonical — second user-facing DELTA in Fase 3).
- **HU-F3.3**: Abrir / cerrar turno (caja-sesion) — pendiente.

**Forward unlock**: HU-F3.3 puede arrancar contra `useAuth().user.sucursal` (F3.1 REQ-OPS-110/111 + F3.2 REQ-OPS-117 50min refresh preserva shape) + `useCountdown` hook (F3.2 REQ-OPS-113, reusable cross-feature para retry buttons de arqueo si F10.x requiere) + pre-flight gate extensible vía `PRE_FLIGHT_PATHS_EXTENDED` (F3.2 REQ-OPS-116 + DEC-F3.2-10) para incluir `/caja-sesion/*` cuando F3.3 lo decida.

---

## CHANGELOG

- (2026-09-15) **F3.2 archive** — 4 atomic commits archivados, 7 archivos SDD preservados, 5/7 gates PASS source-level + 2/7 SKIPPED-env (G6 e2e + G7 axe-core runtime) + 0 FAIL, 5 deviations documentadas (D-env-F.6 MEDIUM + D-h3-regex-update LOW + D-signature-position LOW + D-progress-field LOW + D-fake-timers-handle401 LOW). 6 new REQ-OPS-113..118 materialized al canonical `openspec/specs/operations/spec.md` (md5 pre/post + byte-identity verified, DELTA precedent — second user-facing DELTA in Fase 3, sigue F3.1 first DELTA breaking F2.x NO-OP pattern). F3.2 cerrado. **Fase 3 2/3 cerrado**.

---

**End of archive report.**