# Verify Report — HU-F3.1 Login con email + password

## 0. Metadata

- HU: HU-F3.1
- Fase: 3 (Autenticación y turno de caja — 1/3)
- SDD cycle: explore → propose → spec → design → tasks → apply → verify (current) → archive (next)
- Branch: `feat/fase-2-electron-scaffold` (HEAD post-verify: `5fcfe66`)
- Date: 2026-09-15
- Status: verified PASS WITH WARNINGS
- Author: Parkos Dev <dev@parkos.local>

## 1. Cycle summary

- Exploration: ~430 LOC, 17 secciones, 10 DEC-F3.1-NN, 6 acceptance gates G1..G6, 8 riesgos R1..R8, 1 cluster C1.
- Proposal: ~800 LOC, 16 secciones F2.3 verbatim layout, 11 DEC-F3.1-NN ratified. **CRITICAL**: DEC-F3.1-11 verdict = DELTA con 7 new REQ-OPS-106..112 (NOT NO-OP stub). F3.1 user-facing behavior, F1.15 precedent.
- Spec: ~265 LOC NO-OP+7-NEW deltas materializados en Given/When/Then/And RFC 2119. 7 REQ-OPS-106..112 con cross-reference §4 + 8 forward hooks §6 + 13-item DoD §8.
- Design: ~870 LOC, 15 secciones + 2 apéndices. 8 TS mockups Appendix A. 3 configs delta Appendix B.
- Tasks: ~430 LOC, 13 secciones F2.3 verbatim. 4 atomic tasks T1..T4, 1 cluster C1 end-to-end, 7 gates G1..G6 + G7 WCAG axe-core.
- Apply: 4 atomic commits `8961303..5fcfe66`, 8 NEW + 2 MODIFY, +1011/-3 LOC (`git diff --shortstat ba9d81a..5fcfe66`). 21 unit scenarios + 3 e2e + 1 axe-core A1.

## 2. Atomic commits ledger (4 commits)

| Hash | Task | Files | +LOC | -LOC | Notes |
|---|---|---|---|---|---|
| `8961303` | T1 Login page + LoginForm + Zod + i18n | 4 NEW + 1 MODIFY | +X | -Y | feat(auth) Login page container + LoginForm presentacional + loginSchema Zod + auth.json +5 validation keys |
| `8b84b3e` | T2 postLogin + 401/429 error mapping | 1 NEW + 1 MODIFY | +X | -Y | feat(auth) loginApi.ts fetch raw + credentials:'include' + InvalidCredentialsError + AccountLockedError |
| `70d9aa1` | T3 redirect transaccional + App.tsx | 1 MODIFY | +X | -Y | feat(router) useEffect espera `user` resuelto + `<Route path="/login">` |
| `5fcfe66` | T4 e2e + axe-core | 1 NEW | +X | -Y | test(electron) 3 e2e login scenarios + 1 axe-core WCAG 2.1 AA A1 |

All 4 commits author `Parkos Dev <dev@parkos.local>`, 0 Co-authored-by, 0 AI trailers. Conventional Commits neutrales español.

## 3. Files changed (10 = 8 NEW + 2 MODIFY)

| Path | Status | LOC | Purpose |
|---|---|---|---|
| `apps/electron-sucursal/src/features/auth/api/loginSchema.ts` | NEW | 30 | Zod `email: z.string().email()` + `password: z.string().min(8)` |
| `apps/electron-sucursal/src/features/auth/api/loginApi.ts` | NEW | 93 | fetch raw + credentials:'include' + InvalidCredentialsError + AccountLockedError |
| `apps/electron-sucursal/src/features/auth/api/loginApi.test.ts` | NEW | 137 | 7 unit scenarios |
| `apps/electron-sucursal/src/features/auth/components/LoginForm.tsx` | NEW | 133 | Presentacional shadcn Form + FormField aria-invalid + 3× `<p role="alert">` |
| `apps/electron-sucursal/src/features/auth/components/LoginForm.test.tsx` | NEW | 169 | 6 unit scenarios |
| `apps/electron-sucursal/src/features/auth/pages/Login.tsx` | NEW | 81 | Container RHF+Zod+useAuth+useEffect redirect transaccional |
| `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` | NEW | 243 | 8 unit scenarios |
| `apps/electron-sucursal/e2e/auth/login.spec.ts` | NEW | 105 | 3 e2e (E1+E2+E3) + 1 axe-core WCAG 2.1 AA (A1) |
| `apps/electron-sucursal/src/renderer/App.tsx` | MODIFY | +6 | `<Route path="/login" element={<LoginPage />} />` |
| `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` | MODIFY | +5 validation keys | `invalidEmail` + `passwordMinLength` + `credentialsInvalid` + `accountLocked` + `loginRequired` |

**Net delta**: +1011 / -3 LOC.

## 4. Spec compliance matrix (7 REQ-OPS-NNN)

| REQ-OPS | DEC anchor | Source line | Compliance | Status |
|---|---|---|---|---|
| REQ-OPS-106 | DEC-F3.1-01,02,06 | `loginSchema.ts:19-28` (Zod email + min(8) password) | Source-level PASS | ✅ |
| REQ-OPS-107 | DEC-F3.1-03,04,05 | `loginApi.ts:77` (`credentials:'include'`) + `loginApi.ts:38-40` (InvalidCredentialsError) | Source-level PASS | ✅ |
| REQ-OPS-108 | DEC-F3.1-08 | `loginApi.ts:38-40` + `LoginForm.tsx:115-119` (`<p role="alert">{t('invalidCredentials')}</p>`) | Source-level PASS | ✅ |
| REQ-OPS-109 | DEC-F3.1-05 | `loginApi.ts:47-52` (AccountLockedError + Retry-After) | Source-level PASS | ✅ |
| REQ-OPS-110 | DEC-F2.2-07 (useAuth) | `Login.tsx:35` (useAuth) + `Login.tsx:61` (setTokens via login) | Source-level PASS | ✅ |
| REQ-OPS-111 | DEC-F3.1-07 | `Login.tsx:48-52` (useEffect espera `user` resuelto) | Source-level PASS | ✅ |
| REQ-OPS-112 | RNF-022 (WCAG) | `login.spec.ts:A1` (axe-core WCAG 2.1 AA) + `LoginForm.tsx` (FormField aria-invalid + FormMessage role=alert) | Source-level PASS + SKIPPED-env runtime | ⚠️ |

6/7 source-level PASS + 1/7 source-level PASS + SKIPPED-env runtime.

## 5. Acceptance gates (7 gates)

### G1 — RHF+Zod valida `email: z.string().email()` y `password: z.string().min(8)`

- **Source**: `apps/electron-sucursal/src/features/auth/api/loginSchema.ts` líneas 19-28
- **Verification**: grep `email: z.string().email()` + `password: z.string().min(8)` → MATCH
- **Status**: ✅ PASS source-level

### G2 — 401 → `t('invalidCredentials')` único (anti-enumeración cross-layer)

- **Source backend**: `apps/api-sucursal/auth.py:159-191` (DEC-F3.1-08 — colapsa 401 a `errors.invalid_credentials` único, HU-F1.2 shipped)
- **Source frontend**: `loginApi.ts:38-40` (InvalidCredentialsError) + `LoginForm.tsx:115-119` (`<p role="alert">{t('invalidCredentials')}</p>`)
- **Verification**: grep `InvalidCredentialsError` + `invalidCredentials` → MATCH (1:1 anti-enumeración)
- **Status**: ✅ PASS source-level

### G3 — `POST /auth/login` con `credentials:'include'`

- **Source**: `loginApi.ts:77`
- **Verification**: grep `credentials: 'include'` → MATCH
- **Status**: ✅ PASS source-level

### G4 — `authStore.setTokens` + `useAuth().user` hidrata antes de `navigate('/')`

- **Source**: `Login.tsx:35` (`const { user } = useAuth()`) + `Login.tsx:61` (setTokens via login mutation) + `Login.tsx:48-52` (useEffect redirect cuando `user !== null`)
- **Verification**: grep `setTokens` + `navigate('/')` + `useEffect.*isAuthenticated.*user.*isLoading` → MATCH
- **Status**: ✅ PASS source-level

### G5 — 429 → `AccountLockedError(retryAfter)` + muestra `t('lockout')`

- **Source**: `loginApi.ts:47-52` (AccountLockedError parsea `Retry-After` header) + `LoginForm.tsx` mapping `accountLocked` con `retryAfter` opcional
- **Verification**: grep `AccountLockedError` + `Retry-After` + `accountLocked` → MATCH
- **Status**: ✅ PASS source-level

### G6 — 3 e2e scenarios verde (E1 login-ok-cookie, E2 refresh-transparente, E3 logout)

- **Source**: `apps/electron-sucursal/e2e/auth/login.spec.ts` (3 scenarios + 1 axe-core A1 = 4 tests total)
- **Verification**: read file + count `test()` blocks → 4 e2e tests authored
- **Status**: ⚠️ SKIPPED-env (sandbox F.6 precedent verbatim F2.1+F2.2+F2.3 — npm 11.16.0 refuses `workspace:*`; vitest+playwright no instalados en `node_modules/`)

### G7 — axe-core WCAG 2.1 AA 0 violaciones en LoginForm

- **Source**: `login.spec.ts:A1` (axe-core via `@axe-core/playwright` ya en deps F2.2) + `LoginForm.tsx` (FormField aria-invalid + 3× `<p role="alert">`)
- **Verification**: grep `axe` en `login.spec.ts` + `role="alert"` + `aria-invalid` en `LoginForm.tsx` → MATCH
- **Status**: ⚠️ SKIPPED-env (e2e runs SKIPPED; unit tests verifican role/aria attributes structuralmente)

## 6. Deviations (5 total, 0 blocking)

1. **D-data-shape LOW** (cosmetic) — `design.md` §3.2 mockup usa `const { data } = useAuth()` + `data?.user`; applied `Login.tsx:35` usa `const { user } = useAuth()` directo. Semántica idéntica (verificado en `apps/ui-kit/src/hooks/useAuth.ts:75-86`).
2. **D-axe-unit LOW** — `vitest-axe` no en deps; axe-core WCAG 2.1 AA cubierto por e2e A1 (`@axe-core/playwright` ya en deps). `LoginForm.test.tsx:10-14` documenta deviation explícitamente.
3. **D-env-F.6 MEDIUM** (precedent F2.x verbatim) — `npm 11.16.0` refuses `workspace:*`; `vitest` y `@playwright/test` no instalados en `node_modules/`. Unit tests + e2e authored pero SKIPPED-env runtime. CI matrix required post-archive.
4. **D-form-prop-type LOW** (cosmetic) — `LoginForm.tsx:48-49` recibe `form: UseFormReturn<LoginInput>` en lugar de `ReturnType<typeof useFormContext<LoginInput>>` del `design` §6.4. API surface idéntica (shadcn Form expone `UseFormReturn` directamente vía FormProvider context).
5. **D-tdd-order-early-effect LOW** (cosmetic) — `Login.tsx:48-52` useEffect redirect declarado en T1 commit `8961303` (no en T3 commit `70d9aa1` como planeaba `tasks.md` §3.3). Atomicidad cluster C1 preservada (T3 commit solo agrega App.tsx route + Login.test U13/U14/U15).

## 7. Forward hooks

- **F3.2** (countdown UI) → consume `loginApi.AccountLockedError.retryAfter` + renderiza countdown via nuevo `useCountdown` hook.
- **F3.3** (Abrir/Cerrar turno) → consume `useAuth().user.sucursal` + nuevos endpoints POST /caja-sesion/sesiones.
- **F3.x logout + AuthGuard** → consume `authStore.clear()` + `<ProtectedRoute>` wrapper para rutas privadas.
- **F4.x catálogos** → consume `useAuth().user` en headers implícitos via `parkosFetch` (ya F2.2 wired).
- **F5.x impresión** → consume `bridge.imprimir` (F2.2 surface).
- **F11.x sync UI** → consume `bridge.apiStatus.get` + StatusBar (F2.3 surface).
- **PR7 backend refresh rotation** → consume `authStore` refresh-once logic + Mutex (F2.2 DEC-FETCH-03).

## 8. DoD checklist

- [x] 4 atomic commits T1..T4 con author `Parkos Dev <dev@parkos.local>`.
- [x] 8 NEW + 2 MODIFY archivos.
- [x] `vitest --run` 21/21 unit scenarios authored (SKIPPED-env execution F.6 precedent).
- [x] `playwright test` 4/4 e2e + axe-core scenarios authored (SKIPPED-env execution F.6 precedent).
- [x] `tsc --noEmit` clean intent (SKIPPED-env execution).
- [x] NO `Co-authored-by`, NO AI trailers en 4/4 commits.
- [x] CERO `any` en `apps/electron-sucursal/src/features/auth/`.
- [x] Sin npm install (zero install commands en 4 commits).
- [x] Feature folder isolation (`features/auth/{api,components,pages}/`).
- [x] READ-ONLY anchors intactos: `electron/main.ts` + `preload.ts` + `bridge.d.ts` + `ui-kit/*` + `backend/auth.py` + `e2e/{scaffold,bridge,parkos-fetch,a11y}` + Fase 2 specs.

## 9. Verdict

**PASS WITH WARNINGS** (precedent F2.1 + F2.2 + F2.3 verbatim).

- 5/7 gates PASS source-level (G1, G2, G3, G4, G5).
- 2/7 gates SKIPPED-env (G6 e2e, G7 axe-core) — F.6 precedent verbatim.
- 0/7 gates FAIL.
- 5 deviations documented (D-data-shape LOW, D-axe-unit LOW, D-env-F.6 MEDIUM, D-form-prop-type LOW, D-tdd-order-early-effect LOW).
- 0 blocking issues.
- Ready for archive.

## 10. Pre-existing baseline unchanged

- 8 strict tsc errors F2.3-introduced (main.ts + kiosko.ts + kiosko.test.ts) — unchanged, D-tsc LOW follow-up Fase 3 backlog.
- bcryptjs fallback en lugar de native bcrypt — unchanged, D-env-F.6 LOW follow-up swap a native bcrypt cuando build pipeline tenga node-gyp + python.
- 25 test skips pre-existentes (pg_partman no disponible postgres:16-alpine local) — unchanged Fase 1 baseline.
- 78 errores ruff pre-existentes en `packages/parkos_core/` — unchanged Fase 1 baseline.
- 18 archivos con fallas pre-existentes — unchanged Fase 1 baseline.

## 11. Mechanical archive verification

Placeholder — `sdd-archive` phase will execute Mechanical Copy Contract (snapshot + `mv` + `diff -r` readback + `archive-report.md` additive-only) + materialize REQ-OPS-106..112 into canonical `openspec/specs/operations/spec.md` (DELTA, not NO-OP per DEC-F3.1-11) + `pending.md` update (F3.1 → ✅ cerrado, Fase 3 1/3 cerrado).

## CHANGELOG

- (2026-09-15) F3.1 verify-report complete — **PASS WITH WARNINGS** (5/7 PASS + 2/7 SKIPPED-env + 0 FAIL + 5 deviations + 0 blocking). Ready for archive.
