# Tasks — HU-F3.2 Lockout visible (countdown) + refresh transparente (50min auto + pre-flight)

> **Phase**: tasks (sdd-tasks) · **Status**: ready for sdd-apply
> **HU ID**: HU-F3.2 (Fase 3 — segunda HU; Autenticación y turno de caja, hardening UX + lifecycle del `access_token`)
> **Working dir**: `E:\easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `bcfe2ed`, F3.1 archivado 2026-09-15 con 7 REQ-OPS-106..112)
> **Cross-refs**: `exploration.md` §1-§17 (10 DEC-F3.2-01..09 + 8 riesgos R1..R8 + 6 gates G1..G6 + 4 tasks T1..T4), `proposal.md` §1-§16 (11 DEC-F3.2-01..11 ratified, DEC-F3.2-08 + DEC-F3.2-11 verdict DELTA, 6 new REQ-OPS-113..118), `specs/operations/spec.md` (DELTA con 6 new REQ-OPS-113..118), `design.md` §1-§15 + Appendix A + Appendix B (8 TS mockups + 3 configs delta)
> **Prereq change**: `hu-f3-1-login-email-password` archived 2026-09-15
> **Author**: Parkos Dev <dev@parkos.local> · **Language**: español neutro profesional

---

## §0. Metadata

| Campo | Valor |
|---|---|
| **Change** | `hu-f3-2-lockout-refresh-pre-flight` |
| **HU** | F3.2 — Lockout visible (countdown decreciente `useCountdown` hook + `setInterval(1000)` + cleanup) + refresh transparente 50min auto (cambio `useAuth.refreshInterval: 5*60*1000 → 50*60*1000` per DEC-SUC-03) + refresh pre-flight gate antes de POST `/facturacion/*` + POST `/caja/arqueo` (`refreshIfExpiringSoon()` con Mutex shared F2.2 DEC-FETCH-03) + e2e lockout scenario (4 intentos fallidos → 429 → countdown → auto re-enable al 0) + axe-core A1 WCAG 2.1 AA en countdown state. |
| **Owner** | Parkos Dev <dev@parkos.local> |
| **Working tree** | `E:\easypunto_parkos` |
| **Branch base** | `feat/fase-2-electron-scaffold` (F2.1 + F2.2 + F2.3 + F3.1 archivados) |
| **PR target** | `origin/dev` |
| **Total tasks** | 4 atomic (T1..T4) |
| **Total clusters** | 1 (C1 — countdown + refresh end-to-end) |
| **Production LOC budget** | ~110 LOC (production 90 + configs 10 + JSDoc 10) |
| **Test LOC budget** | ~240 LOC (unit 160 + e2e 80) |
| **Total LOC budget** | ~370 LOC |
| **Atomic commits** | 4 (C1: T1, T2, T3, T4) |
| **Review actor** | `sdd-verify` post-apply |
| **Archive actor** | orchestrator (post-verify PASS) |
| **Related artifacts** | `exploration.md` (18 secciones, 10 DEC-F3.2-01..10, 8 riesgos R1..R8) · `proposal.md` (16 secciones, 11 DEC-F3.2-01..11 ratified, 6 new REQ-OPS-113..118) · `design.md` (15 secciones + 2 apéndices, 8 TS mockups + 3 configs delta) · `specs/operations/spec.md` (DELTA con 6 new REQ-OPS-113..118 user-facing per F1.15 + F3.1 precedent) |
| **Scope** | Hardening UX + lifecycle del `access_token`. `useCountdown` hook reusable (primer hook genuinely reusable del feature `auth` — forward F4.x/F5.x/F11.x) + countdown visible en `<LoginForm>` (`<p role="status" aria-live="polite">` con `mm:ss`) + form `disabled` durante lockout + auto re-enable al llegar a 0 + `useAuth.refreshInterval: 50min` con constante `REFRESH_INTERVAL_MS` exportada + pre-flight gate `refreshIfExpiringSoon()` antes de POST críticos + WCAG 2.1 AA countdown state. NO incluye backend cambios (HU-F1.2 + HU-F1.15 shipped), refresh-token rotation con `jti` reuse detection (PR7 backend), AuthGuard (F3.3+), logout button UI (F3.3+), countdown styling library externa (vanilla `formatTime` helper inline). |
| **Dependencies** | F2.1 archivado (Electron scaffold + shadcn Form/Input/Button + i18n) · F2.2 archivado (parkosFetch + authStore + useAuth + Mutex `refreshAccessToken`) · F2.3 archivado (kiosko mode + StatusBar) · F3.1 archivado (Login + LoginForm + loginApi + `AccountLockedError(retryAfterSeconds)` + ruta `/login`) · HU-F1.2 shipped Fase 1 (backend `POST /auth/login` + 429 + `Retry-After` header) · HU-F1.15 shipped Fase 1 (login histórico + refresh token rotation) · npm 11.16.0 local Windows + npm sandbox F.6 caveat documentado |

---

## §1. Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Total LOC production | ~110 |
| Total LOC tests | ~240 |
| Total LOC delta | ~370 |
| Atomic tasks | 4 (T1..T4) |
| Clusters | 1 (C1) end-to-end |
| Acceptance gates | 7 (G1..G6 + G7 implícito axe-core WCAG 2.1 AA) |
| DEC-F3.2-NN ratificadas | 11 (DEC-F3.2-01..11) |
| New REQ-OPS | 6 (REQ-OPS-113..118) |
| Files NEW | 3 (~170 LOC production + tests) |
| Files MODIFY | 7 (~165 LOC delta production + 3 keys i18n + coverage thresholds) |
| Files READ ONLY | 16 (Fase 2 + F3.1 primitives + backend anchors) |
| Conventional commits | feat(auth) × 2 + feat(refresh) × 1 + test(electron) × 1 |
| Author commits | `Parkos Dev <dev@parkos.local>` (sin Co-authored-by, sin AI trailers) |
| Sandbox F.6 caveat | npm 11.16.0 refuses workspace:* → e2e G6 SKIPPED local; CI matrix required |

**Plan 110 LOC matches**: 90 production + 10 configs + 10 JSDoc = ~110 verbatim `plan.md:1319` + `proposal.md §1` + `exploration.md §10.5`.

**Paralelización intra-cluster** (cross-ref design §4 + proposal §15):

- T1 antes de T2 y T3: T1 provee `useCountdown` hook reusable que T2 consume en `LoginForm`/`Login` y T3 NO consume (T3 es infra `parkosFetch` + `useAuth`). Sin T1, T2 no puede escribir tests.
- T2 y T3 son **independientes**: T2 es frontend UI (LoginForm + Login + i18n), T3 es infra ui-kit (parkosFetch pre-flight + useAuth 50min). Pueden ejecutarse en paralelo si el executor lo permite.
- T2 + T3 antes de T4: T4 (e2e `lockout.spec.ts`) requiere Login.tsx con countdown (T2) y useAuth 50min refresh (T3) para validar el flujo end-to-end.

**Dependencias** (T1 + (T2 || T3) + T4):

```
T1 (useCountdown hook + 4 unit tests)
  │
  ├─► T2 (LoginForm countdown integration + 3 i18n keys + Login reset errorState)
  │
  └─► T3 (useAuth 50min refresh + parkosFetch pre-flight gate)
       │
       └─► T4 (e2e lockout.spec.ts — 4 scenarios + axe-core)
```

---

## §2. Dependency graph + Cluster ordering

### §2.1 Diagrama ASCII

```
                    ┌─────────────────────────────────────────────┐
                    │ HOOK REUSABLE (NEW — DEC-F3.2-01)          │
                    │ apps/electron-sucursal/src/features/auth/   │
                    │                     /hooks/                │
                    └─────────────────────────────────────────────┘
                                       │
                                       ▼
              ┌──────────────────────────────────────────────────┐
              │ T1 useCountdown.ts + useCountdown.test.ts       │
              │ ~40 LOC prod + ~50 LOC tests = ~90 LOC          │
              │ Date.now() baseline + setInterval(1000)         │
              │ + cleanup + onComplete callback                 │
              └──────────────────────────────────────────────────┘
                                       │
                          ┌────────────┴────────────┐
                          ▼                         ▼
        ┌─────────────────────────────┐  ┌─────────────────────────────┐
        │ T2 LoginForm countdown      │  │ T3 useAuth 50min +          │
        │ integration + 3 i18n keys   │  │ parkosFetch pre-flight gate │
        │ + Login reset errorState    │  │ + 5 unit tests U12..U16     │
        │ + 3 unit tests U8 + U9+U10  │  │                             │
        │ ~75 LOC delta               │  │ ~90 LOC delta               │
        └─────────────────────────────┘  └─────────────────────────────┘
                          │                         │
                          └────────────┬────────────┘
                                       ▼
              ┌──────────────────────────────────────────────────┐
              │ T4 e2e/auth/lockout.spec.ts                     │
              │ 4 scenarios (E1+E2+E3) + axe-core A1            │
              │ ~80 LOC tests                                  │
              └──────────────────────────────────────────────────┘
                                       │
                                       ▼
              ┌──────────────────────────────────────────────────┐
              │ archive — mover change folder, update pending.md│
              └──────────────────────────────────────────────────┘
```

### §2.2 Tabla de orden estricto

| Step | Cluster | Task | Cuándo | Acción | Razón orden |
|---|---|---|---|---|---|
| 1 | C1 | **T1** | primera | NEW `useCountdown.ts` + `useCountdown.test.ts` (~90 LOC) | DEC-F3.2-01: hook reusable con `Date.now()` baseline. T2 consume; T4 e2e requiere hook verde. |
| 2 | C1 | **T2** | después T1 (paralelo T3) | MODIFY `LoginForm.tsx` (+25 LOC) + `Login.tsx` (+10 LOC) + `auth.json` (+3 keys) + `LoginForm.test.tsx` (+25 LOC U8+U9) + `Login.test.tsx` (+15 LOC U10) | DEC-F3.2-02/05/06: countdown display + form disabled + i18n + WCAG aria-live. Consume hook T1. |
| 3 | C1 | **T3** | después T1 (paralelo T2) | MODIFY `useAuth.ts` (line 60 + REFRESH_INTERVAL_MS export) + `parkosFetch.ts` (+20 LOC pre-flight) + `useAuth.test.ts` (+10 LOC U11) + `parkosFetch.test.ts` (+60 LOC U12..U16) | DEC-F3.2-03/04/07: 50min refresh + pre-flight gate `refreshIfExpiringSoon()` + Mutex shared F2.2 DEC-FETCH-03 invariant preserved. Independiente de T2 (T2 es UI, T3 es infra). |
| 4 | C1 | **T4** | después T2 + T3 | NEW `e2e/auth/lockout.spec.ts` (~80 LOC — E1+E2+E3+A1) | e2e requiere Login con countdown (T2) + useAuth 50min (T3) para validar flujo end-to-end. Plan.md:1315 verbatim. Sandbox F.6 SKIPPED-env (deviation D-env documentada). |

### §2.3 Justificación de orden

- **T1 antes que T2**: T2 (`LoginForm.tsx` consume `useCountdown` + tests U8/U9 mockeando el hook) depende de T1 (`useCountdown.ts` exportable). Si T2 intenta ejecutarse antes de T1, los tests fallan al no existir el hook.
- **T1 antes que T3**: T3 NO consume `useCountdown` directamente, pero T3 entrega `REFRESH_INTERVAL_MS` + pre-flight gate que T4 e2e valida en el flujo completo. Sin T1, el orden no es estrictamente necesario, pero mantengo T1 primero para flujo lógico (hook reusable → consumers).
- **T2 paralelo T3**: T2 (`LoginForm.tsx` + `Login.tsx` + `auth.json` + tests U8/U9/U10) NO toca archivos ui-kit. T3 (`useAuth.ts` + `parkosFetch.ts` + tests U11..U16) NO toca archivos auth feature. Pueden ejecutarse en paralelo sin merge conflicts.
- **T2 + T3 antes que T4**: T4 (`e2e/auth/lockout.spec.ts` con E1 4 intentos → 429 → countdown → E2 decrementa → E3 re-enable → A1 axe-core) requiere Login.tsx completo con countdown integration (T2) + useAuth con refresh 50min (T3) para validar el flujo end-to-end.
- **Single cluster C1 end-to-end**: la atomicidad del feature (countdown visible + form disabled + 50min refresh + pre-flight gate + WCAG accessibility) requiere que los 4 tasks se commiteen en orden sin pasos intermedios. Plan.md:1311 verbatim: "useCountdown(retryAfter) hook reusable; refresh automático 50min; pre-flight POST /facturacion + /caja/arqueo; form disabled durante lockout" — el flujo NO es divisible en features independientes.
- **Ningún task puede saltarse pasos** sin invalidar acceptance gates (cross-ref §6 G1..G6 + G7).

---

## §3. Cluster C1 — Countdown + refresh end-to-end (T1+T2+T3+T4)

### §3.0 Pre-requisitos C1

- branch: `feat/fase-2-electron-scaffold` checked out.
- working tree: `clean` (`git status --short` retorna vacío).
- pre-flight local:
  - `git log --oneline -1` → debe ser `bcfe2ed` o posterior (F3.1 archivado 2026-09-15).
  - F2.1 archivado en `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/`.
  - F2.2 archivado en `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/`.
  - F2.3 archivado en `openspec/changes/archive/2026-09-15-hu-f2-3-electron-auto-update-kiosko/`.
  - F3.1 archivado en `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/`.
  - `react@^18.3.1` en `apps/electron-sucursal/package.json:23` (F2.1 baseline) — provee `useState`, `useEffect`.
  - `@testing-library/react@^16.0.1` + `vitest@^2.1.x` en `apps/electron-sucursal/package.json` (F2.1 baseline).
  - `@axe-core/playwright@^4.10.0` en `apps/electron-sucursal/package.json:56` (F2.1 baseline).
  - `swr@^2.2.5` en `apps/ui-kit/package.json` (F2.2 baseline).
  - `useAuth.ts:60` con `refreshInterval: 5 * 60 * 1000` (F2.2 baseline — F3.2 T3 cambia a 50min).
  - `parkosFetch.ts:119-140` `handle401` Mutex refresh-once (F2.2 baseline — F3.2 T3 preserve invariant).
  - `useAuthStore.expiresAt` ISO 8601 derivado en `setTokens` (F2.2 authStore.ts:78).
  - `AccountLockedError(retryAfterSeconds)` + `parseRetryAfter` shipped F3.1 (loginApi.ts:47-63).
  - `LoginErrorState kind:'lockout'` con `retryAfterSeconds` shipped F3.1 (LoginForm.tsx:42-46).
  - HU-F1.2 shipped backend `POST /auth/login` + 429 + `Retry-After` header (`backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:148-307, 219-228`).

### §3.1 Task T1 — `useCountdown(retryAfterSeconds, options?)` hook + 4 unit tests (U1..U4)

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done (apply 2026-09-15) |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~90 LOC delta) |
| **Order** | 1 (primera de C1) |
| **Cluster** | C1 |
| **Pre-requisitos** | F2.1 + F2.2 + F2.3 + F3.1 archivados; React 18 `useState`/`useEffect` disponibles |
| **Acceptance gates** | G1 (`useCountdown` baseline + cleanup + onComplete + drift resistance) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- NEW: `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (~40 LOC — `Date.now()` baseline + `setInterval(1000)` + cleanup en `useEffect` return + `onComplete` callback).
- NEW: `apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts` (~50 LOC — U1 baseline + U2 cleanup + U3 onComplete fires + U4 drift resistance via fake timers).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, ~50 LOC):
   - Test U1 (`useCountdown.test.ts`): `renderHook(() => useCountdown(60))` → `expect(secondsLeft).toBe(60); expect(isExpired).toBe(false)`. Vitest fallido (hook no existe).
   - Test U2 (`useCountdown.test.ts`): `vi.useFakeTimers() + onComplete=vi.fn() + unmount() + vi.advanceTimersByTime(3000)` → `expect(onComplete).not.toHaveBeenCalled()` (cleanup on unmount).
   - Test U3 (`useCountdown.test.ts`): `renderHook(() => useCountdown(2, { onComplete })) + vi.advanceTimersByTime(2000)` → `expect(secondsLeft).toBe(0); expect(isExpired).toBe(true); expect(onComplete).toHaveBeenCalledOnce()`.
   - Test U4 (`useCountdown.test.ts`): `vi.advanceTimersByTime(2000)` con `retryAfterSeconds=60` → `expect(secondsLeft).toBe(58)` (decrementa 2, NO 1 — drift resistance).

2. **GREEN** (implementación mínima, ~40 LOC):
   - `useCountdown.ts` (~40 LOC):
     - `interface UseCountdownOptions { onComplete?: () => void }`.
     - `interface UseCountdownReturn { secondsLeft: number; isExpired: boolean }`.
     - `export function useCountdown(retryAfterSeconds, options?)`:
       - `const endTime = Date.now() + retryAfterSeconds * 1000` (wall clock baseline).
       - `const [secondsLeft, setSecondsLeft] = useState(() => Math.max(0, Math.ceil((endTime - Date.now()) / 1000)))`.
       - `const [isExpired, setIsExpired] = useState(secondsLeft === 0)`.
       - `useEffect(() => { if (isExpired) return; const id = setInterval(() => { const remaining = Math.max(0, Math.ceil((endTime - Date.now()) / 1000)); setSecondsLeft(remaining); if (remaining === 0) { setIsExpired(true); options?.onComplete?.(); clearInterval(id); } }, 1000); return () => clearInterval(id); }, [endTime, isExpired, options])`.
       - `return { secondsLeft, isExpired }`.

3. **REFACTOR** (extract constants, JSDoc):
   - Constante módulo-level `TICK_INTERVAL_MS = 1000`.
   - JSDoc cross-ref DEC-F3.2-01 en el hook con explicación "drift-resistant vs accumulator".
   - Types `UseCountdownOptions` + `UseCountdownReturn` exportados (forward consumers F4.x/F5.x/F11.x).
   - NO librería externa (kiosko bundle size).

**Commit message**:

```
feat(auth): adicionar useCountdown hook con Date.now() baseline + cleanup + onComplete
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm vitest run src/features/auth/hooks/useCountdown.test.ts --coverage
```

**LOC budget**: ~90 (production 40 + tests 50).

---

### §3.2 Task T2 — integrar `useCountdown` en `<LoginForm>` + countdown display + form disabled + 3 i18n keys + 3 unit tests (U8+U9+U10)

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done (apply 2026-09-15) |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~110 LOC delta) |
| **Order** | 2 (segunda de C1; corre DESPUÉS de T1 porque consume `useCountdown`) |
| **Cluster** | C1 |
| **Pre-requisitos** | T1 merged; F3.1 shipped `LoginForm.tsx` + `Login.tsx` + `auth.json` |
| **Acceptance gates** | G2 (regression `AccountLockedError` mapping — F3.1), G3 (form disabled durante countdown), G4 (auto re-enable al 0) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- MODIFY: `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` (+25 LOC delta — consume `useCountdown`, renderiza countdown display, aplica `disabled` a inputs + submit, helper `formatTime` inline ~5 LOC).
- MODIFY: `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (+10 LOC delta — `useCallback handleLockoutExpired` que setea `errorState` a `null` + pasa `onLockoutExpired` al `LoginForm`).
- MODIFY: `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (+3 keys — `lockoutCountdown`, `lockoutReEnable`, `lockoutLabel` con template `{{time}}`).
- MODIFY: `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` (+25 LOC — U8 lockout disables form + U9 countdown decrements).
- MODIFY: `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (+15 LOC — U10 isExpired resets errorState).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, +40 LOC):
   - Test U8 (`LoginForm.test.tsx`): mock `useCountdown` retorna `{secondsLeft: 300, isExpired: false}` + render con `error: { kind: 'lockout', retryAfterSeconds: 300 }` → `expect(inputEmail).toBeDisabled(); expect(inputPassword).toBeDisabled(); expect(buttonSubmit).toBeDisabled(); expect(buttonSubmit).toHaveAttribute('aria-disabled', 'true')`.
   - Test U9 (`LoginForm.test.tsx`): render con countdown activo → `vi.advanceTimersByTime(1000)` → `expect(screen.getByTestId('login-countdown')).toBeVisible(); expect(text).toMatch(/\d{2}:\d{2}/)`.
   - Test U10 (`Login.test.tsx`): mock 429 con `Retry-After: 2` + `vi.useFakeTimers() + vi.advanceTimersByTime(3000)` → `expect(errorState).toBeNull()` post-isExpired.

2. **GREEN** (implementación mínima, +75 LOC):
   - `LoginForm.tsx` MODIFY (+25 LOC):
     - `import { useCountdown } from '../hooks/useCountdown'`.
     - `import { useCallback } from 'react'` (si T2 lo requiere para `onLockoutExpired` callback wrapper — sino no necesario).
     - Prop nueva `onLockoutExpired?: () => void` en `LoginFormProps`.
     - Helper inline `formatTime(seconds: number): string` (~5 LOC): `const m = Math.floor(seconds / 60); const s = seconds % 60; return ${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`.
     - `const isLockout = error?.kind === 'lockout'; const { secondsLeft, isExpired } = useCountdown(isLockout ? error.retryAfterSeconds : 0, { onComplete: onLockoutExpired })`.
     - `const isFormDisabled = isSubmitting || (isLockout && !isExpired)`.
     - En `<Input>` email + password: `disabled={isFormDisabled}`.
     - En `<Button type="submit">`: `disabled={isFormDisabled} aria-disabled={isFormDisabled}`.
     - Render condicional `{isLockout && !isExpired && <div data-testid="login-lockout-block"><p role="alert" data-testid="login-error-lockout">{t('lockout')}</p><p role="status" aria-live="polite" aria-label={t('lockoutLabel', { time: formatTime(secondsLeft) })} data-testid="login-countdown">{t('lockoutCountdown', { time: formatTime(secondsLeft) })}</p></div>}`.
     - Render opcional `{isLockout && isExpired && <p role="status" aria-live="polite" data-testid="lockout-re-enable">{t('lockoutReEnable')}</p>}` (post-isExpired notice).
   - `Login.tsx` MODIFY (+10 LOC):
     - `import { useCallback } from 'react'`.
     - `const handleLockoutExpired = useCallback(() => { setErrorState(null); }, [])`.
     - `<LoginForm form={form} onSubmit={onSubmit} isSubmitting={form.formState.isSubmitting} error={errorState} onLockoutExpired={handleLockoutExpired} />`.
   - `auth.json` MODIFY (+3 keys): `"lockoutCountdown": "Reintento disponible en {{time}}"` + `"lockoutReEnable": "El formulario se ha reactivado. Puedes intentar de nuevo."` + `"lockoutLabel": "Tiempo restante para reintentar: {{time}}"`.

3. **REFACTOR** (extract constants, JSDoc):
   - Constantes testid: `COUNTDOWN_TESTID = 'login-countdown'` + `RE_ENABLE_TESTID = 'lockout-re-enable'` + `LOCKOUT_BLOCK_TESTID = 'login-lockout-block'`.
   - JSDoc cross-ref DEC-F3.2-02/05/06 en `<LoginForm>` con explicación "WCAG 2.1 AA polite announcement + form disabled defense anti-retry".
   - JSDoc en `handleLockoutExpired` con cross-ref DEC-F3.2-02 (auto re-enable atomic).

**Commit message**:

```
feat(auth): integrar useCountdown en LoginForm + countdown display + 3 i18n keys
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm vitest run src/features/auth/components/LoginForm.test.tsx src/features/auth/pages/Login.test.tsx --coverage
```

**LOC budget**: ~110 (production 70 + tests 40).

---

### §3.3 Task T3 — `parkosFetch` pre-flight gate + `useAuth` 50min refresh + 6 unit tests (U11..U16)

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done (apply 2026-09-15) |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~90 LOC delta) |
| **Order** | 3 (tercera de C1; corre en PARALELO con T2 — independiente: T3 NO toca archivos feature/auth) |
| **Cluster** | C1 |
| **Pre-requisitos** | T1 merged; F2.2 shipped `useAuth.ts` + `parkosFetch.ts` + `authStore.ts` Mutex |
| **Acceptance gates** | G5 (`parkosFetch` pre-flight gate antes de POST `/facturacion/*` + `/caja/arqueo` cuando `expiresAt < 5min`) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- MODIFY: `apps/ui-kit/src/hooks/useAuth.ts` (line 60 + constante exportada `REFRESH_INTERVAL_MS` + JSDoc update con safety margin).
- MODIFY: `apps/ui-kit/src/fetch/parkosFetch.ts` (+20 LOC delta — `PRE_FLIGHT_PATHS` regex + `PRE_FLIGHT_THRESHOLD_MS` constant + `refreshIfExpiringSoon()` internal function + integration en `parkosFetchRaw` antes del fetch).
- MODIFY: `apps/ui-kit/src/hooks/useAuth.test.ts` (+10 LOC — test U11 `REFRESH_INTERVAL_MS = 50 * 60 * 1000` assertion).
- MODIFY: `apps/ui-kit/src/fetch/parkosFetch.test.ts` (+60 LOC — tests U12..U16 pre-flight gate).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, +70 LOC):
   - Test U11 (`useAuth.test.ts`): `import { REFRESH_INTERVAL_MS } from './useAuth'; expect(REFRESH_INTERVAL_MS).toBe(3_000_000)`.
   - Test U12 (`parkosFetch.test.ts`): mock `useAuthStore.expiresAt = ISO(Date.now() + 60_000)` (60s, <5min) + POST `/facturacion/emision` → spy `useAuthStore.refreshAccessToken` → `expect(refreshAccessToken).toHaveBeenCalledOnce()`.
   - Test U13 (`parkosFetch.test.ts`): mock `expiresAt = ISO(Date.now() + 600_000)` (10min, >5min) + POST `/facturacion/emision` → `expect(refreshAccessToken).not.toHaveBeenCalled()`.
   - Test U14 (`parkosFetch.test.ts`): mock `expiresAt < 5min` + GET `/catalogos` → `expect(refreshAccessToken).not.toHaveBeenCalled()` (GET no triggerea pre-flight).
   - Test U15 (`parkosFetch.test.ts`): mock `refreshAccessToken` reject + POST `/facturacion/emision` → assert fetch called + request succeeds (graceful degradation — error capturado en try/catch).
   - Test U16 (`parkosFetch.test.ts`): concurrent pre-flight + 401 caller → UNA sola llamada a `refreshAccessToken` (spy count = 1 — Mutex shared con handle401 F2.2 invariant preserved).

2. **GREEN** (implementación mínima, +20 LOC):
   - `useAuth.ts` MODIFY (line 60 + JSDoc):
     - `export const REFRESH_INTERVAL_MS = 50 * 60 * 1000` con JSDoc safety margin `ACCESS_TOKEN_TTL (3600s) - REFRESH_INTERVAL_MS (3000s) = 600s = 10min`.
     - `refreshInterval: REFRESH_INTERVAL_MS` (reemplaza `refreshInterval: 5 * 60 * 1000`).
   - `parkosFetch.ts` MODIFY (+20 LOC):
     - `import { useAuthStore } from '@parkos/ui-kit/store'`.
     - `export const PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/` (regex módulo-level, NO recompilada per request).
     - `export const PRE_FLIGHT_THRESHOLD_MS = 5 * 60 * 1000`.
     - `async function refreshIfExpiringSoon(): Promise<void> { const { expiresAt, refreshAccessToken } = useAuthStore.getState(); if (expiresAt === null) return; const msUntilExpiry = Date.parse(expiresAt) - Date.now(); if (msUntilExpiry < PRE_FLIGHT_THRESHOLD_MS) { try { await refreshAccessToken(); } catch { /* graceful degradation — handle401 cubre 401 post-refresh */ } } }`.
     - En `parkosFetchRaw` antes de `fetch`: `const method = (init.method ?? 'GET').toUpperCase(); if (method === 'POST' && PRE_FLIGHT_PATHS.test(url)) { await refreshIfExpiringSoon(); }`.

3. **REFACTOR** (extract constants, JSDoc):
   - Constantes módulo-level: `PRE_FLIGHT_PATHS` + `PRE_FLIGHT_THRESHOLD_MS` exportadas (testabilidad determinista sin magic numbers).
   - JSDoc cross-ref DEC-F3.2-03/04/07 + F2.2 DEC-FETCH-03 invariant preserved en `refreshIfExpiringSoon`.
   - JSDoc en `REFRESH_INTERVAL_MS` con safety margin explanation + DEC-SUC-03 verbatim.
   - `PRE_FLIGHT_PATHS` regex compilada UNA VEZ en módulo-level (NO recompilada per request — performance).

**Commit message**:

```
feat(refresh): 50min SWR refresh + pre-flight gate antes de POST /facturacion/* + /caja/arqueo
```

**Verification command** (post-commit):

```bash
cd apps/ui-kit && pnpm vitest run src/hooks/useAuth.test.ts src/fetch/parkosFetch.test.ts --coverage
```

**LOC budget**: ~90 (production 20 + tests 70).

---

### §3.4 Task T4 — e2e `lockout.spec.ts` (4 scenarios + axe-core A1)

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done (apply 2026-09-15) |
| **Type** | test |
| **Atomicidad** | sí (1 commit, ~80 LOC delta tests only) |
| **Order** | 4 (última de C1; corre DESPUÉS de T2 + T3 mergeados) |
| **Cluster** | C1 |
| **Pre-requisitos** | T1 + T2 + T3 done; `apps/electron-sucursal/playwright.config.ts` auto-discovers `e2e/**/*.spec.ts` (F2.1) |
| **Acceptance gates** | G6 (4 e2e scenarios verde), G7 implícito (axe-core 0 violaciones WCAG 2.1 AA en countdown state) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Sandbox F.6 caveat**: npm 11.16.0 en sandbox refuses `workspace:*` resolution. e2e G6 SKIPPED en este ambiente; CI matrix required. NO es project defect — precedent F2.1 + F2.2 + F2.3 + F3.1 verbatim.

**Files**:
- NEW: `apps/electron-sucursal/e2e/auth/lockout.spec.ts` (~80 LOC — E1 + E2 + E3 + A1).

**E2E scenarios** (per `plan.md:1315` + `design.md §13.2` + `design.md Appendix A.8` verbatim):

- **E1 — countdown-display**: 4 intentos fallidos → 429 con `Retry-After: 600` → assert `<p data-testid="login-countdown">` visible + texto `/\d{2}:\d{2}/` + form `disabled` (email + password + submit). Mock via `page.route('**/api/v1/auth/login', ...)` (DEC-F3.2-09 — e2e usa 4 intentos para velocidad, backend default es 5 per `auth.py:225` — verifica FLOW no número exacto).
- **E2 — countdown-decrements**: countdown display decrece cada ~1000ms vía polling assertion (`getByTestId('login-countdown').textContent()` cada ~2500ms + assert segundos decrementan).
- **E3 — countdown-re-enable**: mock countdown 2s + `page.waitForTimeout(3000)` + assert `<button data-testid="login-submit">` NO disabled + countdown display NOT visible (cleanup post-isExpired).
- **A1 — axe-core WCAG 2.1 AA en countdown state**: `page.route` mock 429 con `Retry-After: 300` (5min) + `await expect(countdown).toBeVisible()` + `new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()` + assert `result.violations` length === 0 (G7 REQ-OPS-118 F3.2).

**Commit message**:

```
test(electron): adicionar 4 e2e lockout (countdown display + decrement + re-enable + axe-core)
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm playwright test e2e/auth/lockout.spec.ts
```

**LOC budget**: ~80 tests.

---

### §3.5 C1 commits ledger

| Hash TBD | Task | +LOC | -LOC | Files | Commit message |
|---|---|---|---|---|---|
| TBD-1 | T1 `useCountdown` hook + 4 unit tests | +90 | 0 | 2 | `feat(auth): adicionar useCountdown hook con Date.now() baseline + cleanup + onComplete` |
| TBD-2 | T2 countdown integration + 3 i18n keys | +110 | -5 | 5 | `feat(auth): integrar useCountdown en LoginForm + countdown display + 3 i18n keys` |
| TBD-3 | T3 50min refresh + pre-flight gate | +90 | -5 | 4 | `feat(refresh): 50min SWR refresh + pre-flight gate antes de POST /facturacion/* + /caja/arqueo` |
| TBD-4 | T4 e2e 4 scenarios + axe-core | +80 | 0 | 1 | `test(electron): adicionar 4 e2e lockout (countdown display + decrement + re-enable + axe-core)` |
| **TOTAL C1** | — | **+370** | **-10** | **12** | — |

**Net LOC delta**: `+370 - 10 = +360 net LOC production + tests`.

---

## §4. Atomic commits ledger (consolidado)

| Hash TBD | Task | Cluster | Files | +LOC | -LOC | Commit message |
|---|---|---|---|---|---|---|
| TBD-1 | T1 `useCountdown` hook | C1 | 2 | +90 | 0 | `feat(auth): adicionar useCountdown hook con Date.now() baseline + cleanup + onComplete` |
| TBD-2 | T2 countdown integration | C1 | 5 | +110 | -5 | `feat(auth): integrar useCountdown en LoginForm + countdown display + 3 i18n keys` |
| TBD-3 | T3 50min refresh + pre-flight | C1 | 4 | +90 | -5 | `feat(refresh): 50min SWR refresh + pre-flight gate antes de POST /facturacion/* + /caja/arqueo` |
| TBD-4 | T4 e2e lockout scenarios | C1 | 1 | +80 | 0 | `test(electron): adicionar 4 e2e lockout (countdown display + decrement + re-enable + axe-core)` |
| **TOTAL** | **4 atomic** | **1 cluster** | **12** | **+370** | **-10** | — |

**Net LOC delta**: `+370 - 10 = +360 net LOC production + tests`.

**Plan 110 LOC matches**: `~90 production + 10 configs/JSDoc = ~110` ≈ `360 net (90 production T1 + 70 production T2 + 20 production T3 + 0 production T4) + (50 + 40 + 70 + 80) tests + 3 keys i18n + coverage thresholds`.

---

## §5. Files inventory

Cross-ref `exploration.md §18` + `design.md §B.1-B.5` + `proposal.md §2.1` verbatim.

### §5.1 NEW (3 archivos production + tests)

| Path | Task | LOC target | Descripción |
|---|---|---|---|
| `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` | T1 | 40 | Hook reusable: `Date.now()` baseline + `setInterval(1000)` + cleanup + `onComplete`. |
| `apps/electron-sucursal/src/features/auth/hooks/useCountdown.test.ts` | T1 | 50 | U1 baseline + U2 cleanup + U3 onComplete + U4 drift resistance. |
| `apps/electron-sucursal/e2e/auth/lockout.spec.ts` | T4 | 80 | 4 scenarios e2e (E1+E2+E3+A1) — countdown display + decrement + re-enable + axe-core. |
| **TOTAL NEW** | T1+T4 | **~170 LOC** | — |

### §5.2 MODIFY (7 archivos)

| Path | Task | Delta LOC | Descripción |
|---|---|---|---|
| `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` | T2 | +25 LOC | Consume `useCountdown` + countdown display + form `disabled` + helper `formatTime`. |
| `apps/electron-sucursal/src/features/auth/pages/Login.tsx` | T2 | +10 LOC | `useCallback handleLockoutExpired` + `onLockoutExpired` callback prop. |
| `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` | T2 | +25 LOC | U8 lockout disables form + U9 countdown decrements. |
| `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` | T2 | +15 LOC | U10 isExpired resets errorState. |
| `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` | T2 | +3 keys | `lockoutCountdown` + `lockoutReEnable` + `lockoutLabel`. |
| `apps/ui-kit/src/hooks/useAuth.ts` | T3 | line 60 + JSDoc + `REFRESH_INTERVAL_MS` export | `refreshInterval: 5min → 50min` (DEC-F3.2-04 + DEC-SUC-03). |
| `apps/ui-kit/src/hooks/useAuth.test.ts` | T3 | +10 LOC | U11 `REFRESH_INTERVAL_MS` assertion. |
| `apps/ui-kit/src/fetch/parkosFetch.ts` | T3 | +20 LOC | Pre-flight gate `refreshIfExpiringSoon()` + `PRE_FLIGHT_PATHS` + `PRE_FLIGHT_THRESHOLD_MS`. |
| `apps/ui-kit/src/fetch/parkosFetch.test.ts` | T3 | +60 LOC | U12..U16 pre-flight gate (expiring + not expiring + GET skip + graceful + Mutex shared). |
| `apps/electron-sucursal/vitest.config.ts` | T1+T2 | coverage thresholds | `useCountdown.ts` ≥90% + `LoginForm.tsx` ≥80% + `Login.tsx` ≥80%. |
| `apps/ui-kit/vitest.config.ts` | T3 | coverage thresholds | `parkosFetch.ts` ≥85% + `useAuth.ts` ≥80%. |
| **TOTAL MODIFY** | T1+T2+T3 | **~165 LOC delta** | — |

### §5.3 READ ONLY (16 archivos — anchors)

| Path | Precedent | Razón NO F3.2 touch |
|---|---|---|
| `apps/electron-sucursal/electron/main.ts` | F2.3 | DEC-F3.1-04 login HTTP no IPC; main process intacto. F3.2 NO requiere IPC. |
| `apps/electron-sucursal/electron/preload.ts` | F2.2 | F3.2 NO expone nuevos métodos bridge. Pre-flight gate es HTTP puro. |
| `apps/electron-sucursal/electron/bridge.d.ts` | F2.2+F2.3 | F3.2 NO agrega tipos bridge. |
| `apps/electron-sucursal/src/features/auth/api/loginApi.ts` | F3.1 | `AccountLockedError(retryAfterSeconds)` + `parseRetryAfter` ya shipped (line 47-63). F3.2 consume as-is. |
| `apps/electron-sucursal/src/features/auth/api/loginSchema.ts` | F3.1 | Zod schema no F3.2 touch. |
| `apps/ui-kit/src/store/authStore.ts` | F2.2 | `setTokens` + `clear` + `refreshAccessToken` Mutex + `expiresAt` ISO 8601 shipped. F3.2 consume `expiresAt` + `refreshAccessToken` Mutex as-is (DEC-FETCH-03 invariant preserved). |
| `apps/electron-sucursal/src/renderer/components/ui/{form,input,button}.tsx` | F2.1 | F3.2 reusa shadcn primitives sin modificar (solo cambia `disabled` prop dinámicamente). |
| `apps/electron-sucursal/src/renderer/i18n/index.ts` | F2.1 | `auth` namespace ya registrado. F3.2 NO agrega namespace. |
| `apps/electron-sucursal/src/renderer/i18n/locales/{common,operacion,caja,facturacion,sync,errors}.json` | F2.1 | F3.2 NO agrega namespaces. |
| `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` | F2.3 | StatusBar visible durante login (sin modificación). |
| `apps/electron-sucursal/src/renderer/App.tsx` | F3.1 | `/login` route ya wired (F3.1 shipped). F3.2 NO modifica. |
| `apps/electron-sucursal/src/renderer/main.tsx` | F2.1 | BrowserRouter ya wrappea. |
| `apps/electron-sucursal/e2e/{scaffold,auth/login,auth/parkos-fetch,auth/bridge,a11y/wcag-2.1-aa,lifecycle,kiosko}.spec.ts` | F2.1+F2.2+F2.3+F3.1 | F3.2 agrega solo `lockout.spec.ts`; no toca los e2e existentes. |
| `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py` | HU-F1.2 + HU-F1.15 shipped | `Retry-After: <segundos>` header (line 219-228) consumido por `parseRetryAfter`. F3.2 NO modifica backend. |
| `backend/packages/parkos_core/src/parkos_core/schemas/auth.py` | HU-F1.2 shipped | F3.2 consume `LoginRequest` + `TokenPair` + `AuthMeResponse` as-is. |
| `openspec/specs/operations/spec.md` | canonical | F3.2 AGREGA 6 new REQ-OPS-113..118 (post-archive merge). |

### §5.4 Total de impacto

- **NEW**: 3 archivos de producción + tests (~170 LOC).
- **MODIFY**: 9 archivos de producción + i18n + coverage (~165 LOC delta + 3 keys).
- **READ ONLY**: 16 archivos.
- **TOTAL IMPACT**: 28 archivos de 170 LOC nuevos + 165 LOC delta.

---

## §6. Acceptance gates mapping

Cross-ref `proposal.md §11` + `design.md §13` + `exploration.md §9` + `spec.md §5` verbatim.

| Gate | Task | Mechanism | File | Verification command |
|---|---|---|---|---|
| **G1** | T1 | vitest unit (useCountdown baseline + cleanup + onComplete + drift resistance) | `useCountdown.test.ts` U1..U4 | `pnpm vitest run src/features/auth/hooks/useCountdown.test.ts --coverage` |
| **G2** | T2 (regression) | vitest unit (`AccountLockedError.retryAfterSeconds` mapping F3.1 sin regresión) | `loginApi.test.ts` U3 + U3b | `pnpm vitest run src/features/auth/api/loginApi.test.ts --coverage` |
| **G3** | T2 | vitest unit (`LoginForm` form disabled durante countdown) | `LoginForm.test.tsx` U8 + U9 | `pnpm vitest run src/features/auth/components/LoginForm.test.tsx --coverage` |
| **G4** | T2 | vitest unit (countdown auto re-enable al llegar a 0) | `Login.test.tsx` U10 | `pnpm vitest run src/features/auth/pages/Login.test.tsx --coverage` |
| **G5** | T3 | vitest unit (`parkosFetch` pre-flight fires antes de POST `/facturacion/*` + `/caja/arqueo` cuando `expiresAt < 5min`) | `parkosFetch.test.ts` U12..U16 + `useAuth.test.ts` U11 | `pnpm vitest run src/fetch/parkosFetch.test.ts src/hooks/useAuth.test.ts --coverage` |
| **G6** | T4 | playwright e2e (`_electron.launch` 4 scenarios) | `lockout.spec.ts` E1+E2+E3+A1 | `pnpm playwright test e2e/auth/lockout.spec.ts` |
| **G7 (implícito)** | T2 + T4 | axe-core WCAG 2.1 AA 0 violaciones en countdown state | `LoginForm.test.tsx` (vitest-axe) + `lockout.spec.ts` A1 (playwright axe-core) | `pnpm vitest run src/features/auth/components/LoginForm.test.tsx && pnpm playwright test e2e/auth/lockout.spec.ts` |

**Estado pre-flight target**: 0/7 PASS al inicio; **7/7 PASS** post-implementación en local dev (Windows native npm 11.16+) o CI matrix con image compatible.

**Sandbox F.6 caveat**: G6 SKIPPED en sandbox F.6 (npm 11.16.0 refuses workspace:*). G1, G2, G3, G4, G5, G7 (axe-core unit) pueden ejecutar con mocks (sin necesidad de workspace resolution post-install). Documentado en §8.

---

## §7. Verification contract (cross-ref `sdd-verify`)

`sdd-verify` debe validar los siguientes criterios antes de emitir PASS:

1. **4 atomic commits** en `feat/fase-2-electron-scaffold` con:
   - Author: `Parkos Dev <dev@parkos.local>` (verificado via `git log --format='%an <%ae>'`).
   - **SIN** `Co-authored-by` trailer (verificado via `git log --format='%(trailers)' --grep='Co-authored-by'` retorna vacío).
   - **SIN** AI trailers (no `Signed-off-by` automático, no `[AI]`, no `Generated by`).
   - Mensajes verbatim de §4 commits ledger.

2. **7/7 acceptance gates** evaluados:
   - G1, G2, G3, G4, G5, G7 (unit + axe-core) ejecutan localmente.
   - G6 (e2e) ejecuta solo en CI matrix (sandbox F.6 SKIPPED-env-blocked documentado).

3. **Coverage thresholds** (cross-ref design §13.4 + tsconfig `coverage.thresholds`):
   - `src/features/auth/hooks/useCountdown.ts` ≥90% lines, ≥90% functions, ≥85% branches.
   - `src/features/auth/components/LoginForm.tsx` ≥80% lines, ≥80% functions, ≥75% branches.
   - `src/features/auth/pages/Login.tsx` ≥80% lines, ≥80% functions, ≥75% branches.
   - `src/fetch/parkosFetch.ts` ≥85% lines, ≥85% functions, ≥80% branches.
   - `src/hooks/useAuth.ts` ≥80% lines, ≥80% functions, ≥75% branches.
   - Verificado via `vitest --coverage` en CI matrix.

4. **TypeScript strict**:
   - `pnpm tsc --noEmit -p tsconfig.renderer.json` limpio en archivos nuevos.
   - `pnpm tsc --noEmit -p tsconfig.main.json` limpio (F3.2 NO toca main, pero verificable).
   - **CERO** `any` introducido en código nuevo.

5. **Unit tests verde**:
   - `pnpm vitest --run` en archivos nuevos (`useCountdown.test.ts` + `LoginForm.test.tsx` + `Login.test.tsx` + `useAuth.test.ts` + `parkosFetch.test.ts`) verde.

6. **Canonical `openspec/specs/operations/spec.md` DELTA mergeado**:
   - Post-archive, las 6 new REQ-OPS-113..118 están mergeadas al spec canónico (byte count incrementado).
   - Numeración monotónica verificada: REQ-OPS-112 vigente pre-archive → REQ-OPS-113..118 nuevos.

7. **i18n keys nuevas**:
   - `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` delta con 3 keys (`lockoutCountdown` + `lockoutReEnable` + `lockoutLabel`) — snapshot test estable.

8. **Defense in depth XR6 (5 capas)** preservado + REQ-OPS-113..118:
   - Layer 1 auth: HU-F1.2 + HU-F1.15 backend bcrypt + JWT + cookie httpOnly SameSite=Lax.
   - Layer 2 engineering: TS strict + noUncheckedIndexedAccess.
   - Layer 3 a11y: axe-core WCAG 2.1 AA + FormField aria-invalid + FormMessage role=alert + `<p role="status" aria-live="polite">` countdown (REQ-OPS-118 F3.2 — extiende REQ-OPS-112 F3.1).
   - Layer 4 contract: Zod validation form (DEC-F3.1-06) + backend Pydantic + 6 new REQ-OPS-113..118 (DEC-F3.2-11).
   - Layer 5 retry-budget: parkosFetch retry 5xx + 401 refresh-once (F2.2) + pre-flight gate F3.2 (DEC-F3.2-03 + DEC-F3.2-07).

---

## §8. Sandbox F.6 + npm 11.16.0 caveat

Cross-ref `exploration.md §3 sandbox` + `design.md §15.5` + precedent F2.1 + F2.2 + F2.3 + F3.1 archive reports.

**Documentación obligatoria**:

- `npm 11.16.0` en sandbox F.6 refuses `workspace:*` resolution (`apps/ui-kit` consume `apps/electron-sucursal` etc.). Esto bloquea `pnpm/npm install` con workspaces.
- e2e G6 (playwright `_electron.launch`) SKIPPED en este ambiente — `pnpm install` falla antes de poder ejecutar tests.
- **NO es project defect** — precedent verbatim F2.1 + F2.2 + F2.3 + F3.1 archive reports documentan misma limitation.
- e2e verdes en local dev (Windows native npm 11.16+) o CI con image compatible (ubuntu-latest, macos-latest).
- Unit tests G1, G2, G3, G4, G5, G7 (axe-core unit) ejecutan con mocks (no requieren workspace resolution post-install) — estos sí corren localmente.

**Acciones en verify-report**:

- `verify-report.md` documenta D-env deviation: "e2e G6 SKIPPED en sandbox F.6 — CI matrix required para validar".
- `verify-report.md` lista los 6 unit gates PASS (G1, G2, G3, G4, G5, G7) y el 1 e2e gate DEFERRED (G6) a CI.
- Status final del verify: `partial — CI matrix required para completar G6` (NO `fail`).

---

## §9. Forward hooks (a Fase 3+)

Cross-ref `proposal.md §14` + `design.md §15.2` + `exploration.md §6.4` verbatim.

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.3** (Abrir/Cerrar turno) | pre-flight gate automático para `POST /caja-sesion/*` si F3.3 decide agregar al path match | DEC-F3.2-10: extender `PRE_FLIGHT_PATHS` regex para incluir `/caja-sesion/*` via constante módulo-level `PRE_FLIGHT_PATHS_EXTENDED` o env var. |
| **HU-F3.3** | `useAuth().user.sucursal` + `permisos[]` hidratados post-F3.1 (F3.2 NO toca `useAuth` shape) | F3.3 consume via SWR data — refresh 50min aplica transparentemente. |
| **HU-F3.x** (logout button UI) | `useAuthStore.clear()` ya implementado en F2.2 + `parkos:auth:cleared` window event | F3.3+ logout button dispatch `clear()` + `navigate('/login')`. |
| **HU-F3.x** (AuthGuard component) | `parkos:auth:cleared` window event | F3.3+ `<AuthGuard>` envuelve `<Routes>` excepto `/login` → `navigate('/login?next=...')`. |
| **HU-F4.x** (catálogos + ocupación) | `useCountdown` para retry buttons con countdown visual | F4.x export `useRetryWithCountdown` pattern que envuelve `useCountdown` con retry-exponential-backoff. |
| **HU-F4.x** | `parkosFetch` pre-flight gate — F4.x hereda automáticamente (T3 cubre `/facturacion/*`) | Cero cambios F4.x. |
| **HU-F5.x** (facturación) | pre-flight gate automático (`/facturacion/*` ya cubierto) + `useAuth.refreshInterval: 50min` | Cero cambios F5.x. |
| **HU-F5.x** | `useCountdown` para retry buttons post-409 conflicto | F5.x export `useRetryWithCountdown`. |
| **HU-F11.x** (sync UI + alertas CU-07/14) | `useCountdown` para reintentos de sync con countdown visual + exponential backoff | F11.x export `useSyncRetryCountdown` que envuelve `useCountdown`. |
| **HU-F11.x** | `useAuth` 50min refresh — F11.x hereda automáticamente | Cero cambios F11.x. |
| **PR7 backend** (refresh-token rotation) | `refreshAccessToken` Mutex F2.2 + pre-flight F3.2 → rotación con `jti` reuse detection | PR7 backend: detectar reuse de `jti` claim y revocar cadena. F3.2 ya provee Mutex infrastructure + pre-flight gate ready para integrar rotation. |

---

## §10. Implementation strategy (TDD strict per task)

Cross-ref `exploration.md §10` + `design.md §13` + `proposal.md §13`.

### §10.1 Reglas globales

- **TDD strict**: cada test escrito ANTES de la implementación. Tests rojos primero (RED), luego código que los hace verde (GREEN), luego refactor (REFACTOR).
- **Cobertura >80% exigida** en `useCountdown.ts` (≥90%) + `Login.tsx` (≥80%) + `LoginForm.tsx` (≥80%) + `parkosFetch.ts` (≥85%) + `useAuth.ts` (≥80%) (vitest --coverage threshold per tsconfig).
- **Cobertura snapshot** en i18n `auth.json` con 3 nuevas keys countdown (no regression).
- **Conventional commits** neutrales español: `feat(auth)` × 2, `feat(refresh)`, `test(electron)`.
- **NO Co-authored-by**, **NO AI trailers** (verificación §7 #1).
- **CERO `any`** introducido en código nuevo.

### §10.2 Pre-flight gates (per task)

| Task | RED (tests rojos primero) | GREEN (implementación mínima) | REFACTOR (extract + JSDoc) | Commit |
|---|---|---|---|---|
| **T1** | `useCountdown.test.ts` U1/U2/U3/U4 (4 tests, ~50 LOC) | `useCountdown.ts` (~40 LOC — `Date.now()` baseline + `setInterval(1000)` + cleanup + `onComplete`) | Constants `TICK_INTERVAL_MS` + JSDoc DEC-F3.2-01 + types `UseCountdownOptions`/`UseCountdownReturn` exportados | `feat(auth): adicionar useCountdown hook con Date.now() baseline + cleanup + onComplete` |
| **T2** | `LoginForm.test.tsx` U8+U9 + `Login.test.tsx` U10 (3 tests, +40 LOC) | `LoginForm.tsx` MODIFY (+25 LOC — useCountdown + countdown display + form disabled + `formatTime` helper) + `Login.tsx` MODIFY (+10 LOC — `handleLockoutExpired` callback) + `auth.json` MODIFY (+3 keys) | Constants testid + JSDoc DEC-F3.2-02/05/06 + helper `formatTime` inline | `feat(auth): integrar useCountdown en LoginForm + countdown display + 3 i18n keys` |
| **T3** | `useAuth.test.ts` U11 + `parkosFetch.test.ts` U12..U16 (6 tests, +70 LOC) | `useAuth.ts` MODIFY (line 60 + `REFRESH_INTERVAL_MS` export + JSDoc) + `parkosFetch.ts` MODIFY (+20 LOC — pre-flight gate + constants) | `PRE_FLIGHT_PATHS` + `PRE_FLIGHT_THRESHOLD_MS` exportadas + JSDoc DEC-F3.2-03/04/07 + F2.2 DEC-FETCH-03 invariant preserved | `feat(refresh): 50min SWR refresh + pre-flight gate antes de POST /facturacion/* + /caja/arqueo` |
| **T4** | e2e stubs E1/E2/E3 + A1 (axe-core) | `lockout.spec.ts` con 4 scenarios + axe-core | Doc comments cross-ref DEC-F3.2-05/09 + plan.md:1315 verbatim | `test(electron): adicionar 4 e2e lockout (countdown display + decrement + re-enable + axe-core)` |

### §10.3 Order strictness

- **T1 → T2**: T2 consume `useCountdown` hook de T1. Sin T1, T2 tests fallan (hook no existe).
- **T1 → T3**: T3 NO consume `useCountdown` directamente, pero T3 entrega `REFRESH_INTERVAL_MS` + pre-flight gate que T4 e2e valida en el flujo completo. Mantengo T1 primero para flujo lógico (hook reusable → consumers).
- **T2 || T3**: T2 (frontend UI: LoginForm + Login + auth.json) y T3 (infra ui-kit: useAuth + parkosFetch) NO comparten archivos editados — pueden ejecutarse en paralelo sin merge conflicts.
- **T2 + T3 → T4**: T4 (e2e `lockout.spec.ts`) requiere Login.tsx con countdown (T2) + useAuth 50min refresh (T3) para validar el flujo end-to-end. Plan.md:1315 verbatim.
- **Single cluster C1**: los 4 tasks son una unidad end-to-end (countdown + refresh + pre-flight + WCAG). No se pueden dividir en features independientes.
- **No reordering**: si T2 se intenta ejecutar antes de T1, los tests de `LoginForm.test.tsx` U8/U9 fallan al no existir `useCountdown`.
- **No rollback parcial**: si T3 falla, NO se commitea T2 standalone — se revierte T2 también (atomic cluster C1).

---

## §11. DoD checklist

Cross-ref `proposal.md §16.4` + `design.md §11.5` + `exploration.md §13`.

- [ ] **4 atomic commits T1..T4** con author `Parkos Dev <dev@parkos.local>` (verificado via `git log`).
- [ ] **NO Co-authored-by, NO AI trailers** en los 4 commits (verificado via `git log --format='%(trailers)'`).
- [ ] **Conventional commits** neutrales español: `feat(auth)` × 2 + `feat(refresh)` × 1 + `test(electron)` × 1.
- [ ] **`pnpm vitest --run` verde** en archivos nuevos: `useCountdown.test.ts` + `LoginForm.test.tsx` + `Login.test.tsx` + `useAuth.test.ts` + `parkosFetch.test.ts`.
- [ ] **`pnpm tsc --noEmit -p tsconfig.renderer.json` clean** en archivos nuevos (zero TS errors).
- [ ] **axe-core 0 violaciones** en `LoginForm` countdown state (G7 REQ-OPS-118 F3.2) — vitest `vitest-axe` matcher.
- [ ] **e2e SKIPPED-env** documentado (G6 deviation D-env en `verify-report.md` — sandbox F.6 npm 11.16.0 refuses workspace:*).
- [ ] **No regresiones en suite e2e Fase 2 + F3.1** (F2.1 + F2.2 + F2.3 + F3.1 e2e siguen verdes post-merge F3.2).
- [ ] **Coverage thresholds** cumplidos: `useCountdown.ts` ≥90% + `Login.tsx` ≥80% + `LoginForm.tsx` ≥80% + `parkosFetch.ts` ≥85% + `useAuth.ts` ≥80% (vitest --coverage).
- [ ] **CERO `any`** introducido en código nuevo (TS strict + lint).
- [ ] **Working tree clean post-apply** (`git status --short` retorna vacío post-archive).
- [ ] **`auth.json` snapshot estable** con 3 nuevas countdown keys (`lockoutCountdown` + `lockoutReEnable` + `lockoutLabel`) — snapshot test verde.
- [ ] **`pending.md` §1 row F3.2 → ✅ cerrado** (archive phase post-verify).
- [ ] **`openspec/specs/operations/spec.md` REQ-OPS-113..118 mergeados** (post-archive byte count incrementado).

---

## §12. Risks & mitigations (per task)

Cross-ref `exploration.md §8 R1..R8` + `design.md §10` verbatim.

| # | Risk | Severity | Task | Mitigación |
|---|---|---|---|---|
| **R1** | **Countdown drift** — `setInterval` puede pausar si tab inactive o system sleep → `secondsLeft` queda atrasado del wall clock | MEDIUM | T1 | DEC-F3.2-01: `Date.now()` baseline + recalc en cada tick (NO accumulator). Test U4 usa `vi.advanceTimersByTime(2000)` post-`vi.useFakeTimers()` y verifica `secondsLeft` decrementa 2 (no 1). |
| **R2** | **Pre-flight race con Mutex 401** — pre-flight triggerea refresh + 401 response triggerea refresh concurrent → doble refresh | LOW | T3 | DEC-F3.2-03 + F2.2 DEC-FETCH-03: pre-flight REUSA `refreshAccessToken()` Mutex. Si 401 llega mid-pre-flight, ambos callers comparten UNA promesa. NO doble refresh. Test U16 verifica `refreshAccessToken` spy count = 1. |
| **R3** | **50min refresh coincide con active request** — SWR revalida `/auth/me` mientras operador está submiteando POST `/facturacion` → potential interference | LOW | T3 | SWR `refreshInterval` es non-blocking — `parkosFetch('/auth/me')` corre en paralelo con POST `/facturacion`. Ambos viajan con MISMO access_token (read at request start). NO conflicto. SWR mutation isolation. |
| **R4** | **Countdown cleanup en unmount** — `setInterval` no cleared en unmount → memory leak + late callback en componente desmontado | MEDIUM | T1 | DEC-F3.2-01: `useEffect` retorna cleanup `clearInterval(intervalId)`. Test U2 verifica `unmount → no callback fires`. |
| **R5** | **Pre-flight latency >200ms** — refresh HTTP se cuelga + degrada POST crítico UX | LOW | T3 | DEC-F3.2-07: graceful degradation — si `refreshIfExpiringSoon` falla o tarda, el request continúa con token existente. `handle401` retry cubre 401 post-refresh. Budget 200ms es soft target, no hard fail. Try/catch en `refreshIfExpiringSoon` silencia rejection. |
| **R6** | **WCAG countdown accessibility** — screen reader no anuncia countdown updates | MEDIUM | T2 + T4 | DEC-F3.2-05 + DEC-F3.2-06: `<p role="status" aria-live="polite">` anuncia cambios sin interrumpir (NO `aria-live="assertive"`). `aria-label={t('lockoutLabel')}` da contexto. axe-core scan valida 0 violaciones (A1 test). |
| **R7** | **429 sin `Retry-After` header** — backend anomaly omite header → countdown con `retryAfterSeconds: 0` → display inmediato "00:00" sin tiempo real | LOW | T2 (NO acción directa) | F3.1 precedent (loginApi.ts:59-63): `parseRetryAfter` retorna 0 si header falta. UI fallback: mostrar `t('lockout')` sin countdown numérico. DEC-F3.2-02: `useCountdown(0)` retorna `{secondsLeft: 0, isExpired: true}` → form re-enabled inmediato (sin display). |
| **R8** | **Refresh rotation race** — pre-flight + 401 retry concurrent + rotation PR7 backend | LOW | T3 (NO acción directa) | F2.2 DEC-FETCH-03 Mutex preserved. Rotation con `jti` reuse detection es PR7 backend (forward). F3.2 NO introduce rotation; consume Mutex as-is. |

**Riesgos identificados y cerrados**: 8/8 con mitigación explícita. 0 KNOWN-MISSING.

---

## §13. Open questions (resoluciones F3.1 proposal §16 + design §15.5)

Las 3 inconsistencies detectadas en `exploration.md §1` están cerradas en `proposal.md §16` + `design.md §15.5` + `exploration.md §7 DEC-F3.2-NN`:

- **I1** (`max_intentos_login` 4 vs 5): **DEC-F3.2-09** — e2e configurable via env (default 4). Sin cambio backend. Default backend `max_intentos_login = 5` per `auth.py:225`. Test e2e verifica FLOW (intentos → 429 → countdown), no número EXACTO. Mockea 429 después de 4 intentos con `page.route` para velocidad.
- **I2** (`refreshInterval` 5min vs 50min): **DEC-F3.2-04** — T3 MODIFY `useAuth.ts:60` → `REFRESH_INTERVAL_MS = 50 * 60 * 1000`. Constante exportada para testabilidad. 50min deja 10min safety margin vs `ACCESS_TOKEN_TTL = 3600` per DEC-SUC-03 (plan.md:418) verbatim.
- **I3** (`/caja/arqueo` no existe): **DEC-F3.2-10** — pre-flight gate genérico matchea regex `/\/facturacion(\/|$)|\/caja\/arqueo/`. F3.2 cubre `/facturacion/*` que existe post-F1.8 (REQ-OPS-030). `/caja/arqueo*` se incluye en la regex aunque el endpoint aún no exista — forward extensibility cuando Fase 10 introduzca arqueos. Sin error si regex matchea path no-existente porque `expiresAt === null` en pre-login state, y authenticated requests matchean `/facturacion` que sí existe.

**0 KNOWN-MISSING**. F3.2 ready for `sdd-apply` post tasks archive.

---

## CHANGELOG

- (2026-09-15) **F3.2 tasks phase complete** — 4 atomic tasks T1..T4 across 1 cluster C1 (countdown + refresh end-to-end, orden interno T1 → (T2 || T3) → T4). ~370 LOC total (production 110 + tests 240 + configs 20). 7 acceptance gates G1..G6 + G7 axe-core WCAG 2.1 AA mapeados a unit + e2e + a11y mechanisms. 11 DEC-F3.2-NN ratificadas (cross-ref proposal §4 + exploration §7 + design §5). 6 new REQ-OPS-113..118 user-facing (DEC-F3.2-11 — DELTA stub precedent F3.1 + F1.15 verbatim). T1 entrega primer hook genuinely reusable del feature `auth` (forward F4.x/F5.x/F11.x). T2 integra countdown + form disabled + 3 i18n keys + WCAG compliance. T3 muta `useAuth` 50min refresh + agrega pre-flight gate con Mutex preserved F2.2 DEC-FETCH-03 invariant. T4 e2e 4 scenarios + axe-core A1. Sandbox F.6 caveat documentado (e2e G6 SKIPPED local, CI matrix required). Plan 110 LOC production matches verbatim. Ready for `sdd-apply`.

---

**End of tasks — HU-F3.2.**
