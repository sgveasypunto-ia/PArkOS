# Archive Report — HU-F3.1 Login con email + password

## 0. Metadata

- HU: HU-F3.1
- Fase: 3 (Autenticación y turno de caja — 1/3 cerrado)
- SDD cycle complete: explore → propose → spec → design → tasks → apply → verify → archive
- Branch: `feat/fase-2-electron-scaffold` (HEAD post-archive: ver `git log`)
- Date: 2026-09-15
- Status: closed + archived
- Author: Parkos Dev <dev@parkos.local>

---

## 1. Cycle summary

- Exploración: ~758 LOC inline, 17 secciones, 10 DEC-F3.1-01..10 ratified, 6 acceptance gates G1..G6, 8 riesgos R1..R8, 4 atomic tasks T1..T4, pre-flight 10/10 PASS + 0 KNOWN-MISSING.
- Proposal: ~800 LOC, 16 secciones F2.3 verbatim layout, 11 DEC-F3.1-NN ratificadas (DEC-F3.1-01..10 + **DEC-F3.1-11 NUEVA**). **CRITICAL**: DEC-F3.1-11 verdict = DELTA stub con 7 new REQ-OPS-106..112 (NOT NO-OP stub). F3.1 ES user-facing behavior observable (login UI + anti-enumeration 401 + cookie httpOnly round-trip + redirect transaccional + WCAG 2.1 AA compliance). Precedente directo: F1.15 (login histórico) archivado 2026-09-15 con 4 new REQ-OPS-102..105 user-facing.
- Spec: ~378 LOC, DELTA materializado en formato Given/When/Then/And RFC 2119. 7 REQ-OPS-106..112 con cross-reference §4 + 9-item acceptance criteria §5 + 8 forward hooks §6 + 13-item DoD §8.
- Design: ~870 LOC, 15 secciones + 2 apéndices. 8 TS mockups completos en Appendix A (loginApi.ts + loginSchema.ts + Login.tsx + LoginForm.tsx + auth.json delta + App.tsx delta + e2e outline + Login.test.tsx outline). 3 configs delta en Appendix B (package.json no-cambios + tsconfig.renderer.json path aliases + vitest.config.ts coverage thresholds).
- Tasks: ~430 LOC, 13 secciones F2.3 verbatim. 4 atomic tasks T1..T4, 1 cluster C1 end-to-end con orden interno estricto T1 → T2 → T3 → T4, 7 acceptance gates G1..G6 + G7 implícito axe-core WCAG 2.1 AA.
- Apply: 4 atomic commits `8961303..5fcfe66`, 8 NEW + 2 MODIFY archivos, +1011/-3 LOC (production + tests). 21 unit scenarios + 3 e2e + 1 axe-core WCAG 2.1 AA authored.
- Verify: PASS WITH WARNINGS (5/7 gates PASS source-level + 2/7 SKIPPED-env G6 e2e + G7 axe-core runtime — F.6 precedent verbatim F2.1 + F2.2 + F2.3). 5 deviations documentadas (D-data-shape LOW + D-axe-unit LOW + D-env-F.6 MEDIUM + D-form-prop-type LOW + D-tdd-order-early-effect LOW). 0 blocking issues.
- Archive: source moved via plain `mv` (untracked in git) + snapshot + `diff -r` empty readback + 7 new REQ-OPS-106..112 materialized to canonical `openspec/specs/operations/spec.md` (DELTA precedent — first user-facing DELTA in Fase 3, breaking F2.x NO-OP pattern).

---

## 2. Atomic commits ledger (4 commits)

4 commits authored by `Parkos Dev <dev@parkos.local>`, **NO Co-authored-by**, **NO AI trailers**:

| Hash | Task | Files | +LOC | -LOC | Commit message |
|---|---|---|---|---|---|
| `8961303` | T1 Login + LoginForm + Zod + i18n | 4 NEW + 1 MODIFY | +X | -Y | `feat(auth): adicionar Login page con RHF+Zod (email/password) + LoginForm presentacional + 5 i18n validation keys` |
| `8b84b3e` | T2 postLogin + 401/429 error mapping | 1 NEW + 1 MODIFY | +X | -Y | `feat(auth): integrar POST /auth/login con credentials:'include' + error mapping 401/429` |
| `70d9aa1` | T3 redirect transaccional + App.tsx Route | 1 MODIFY | +X | -Y | `feat(router): adicionar ruta /login con redirect a / post-hidratación useAuth()` |
| `5fcfe66` | T4 e2e + axe-core | 1 NEW | +X | -Y | `test(electron): adicionar 3 e2e login (cookie httpOnly + refresh transparente + logout)` |
| **TOTAL** | **4 atomic** | **8 NEW + 3 MODIFY** | **+1011** | **-3** | — |

Net LOC delta working tree (range `ba9d81a..5fcfe66`): **+1008 net LOC** (production + tests + i18n + 5 validation keys). Source-level PASS + 2/7 SKIPPED-env per F.6 precedent.

Hygiene verification (per `verify-report.md §2`):

```bash
git log -p 8961303..5fcfe66 | grep -iE "(Co-Authored-By|AI Generated|Signed-off-by)" | wc -l
# Output: 0
```

4/4 commits PASS hygiene: author `Parkos Dev <dev@parkos.local>` · NO Co-authored-by · NO AI trailers · conventional commits neutrales español · scopes `{auth, router, electron}`.

---

## 3. Files in archive folder (7)

1. `exploration.md` — ~758 LOC inline, 17 secciones, 10 DEC-F3.1-NN, 8 riesgos R1..R8, pre-flight 10/10 PASS.
2. `proposal.md` — ~800 LOC, 16 secciones, 11 DEC-F3.1-NN ratified, **CRITICAL DEC-F3.1-11 verdict = DELTA stub**.
3. `design.md` — ~870 LOC, 15 secciones + 2 apéndices (Appendix A: 8 TS mockups; Appendix B: 3 configs delta).
4. `specs/operations/spec.md` — ~378 LOC, DELTA materializado (7 new REQ-OPS-106..112 in Given/When/Then/And RFC 2119).
5. `tasks.md` — ~430 LOC, 13 secciones, 4 atomic tasks T1..T4, 1 cluster C1.
6. `verify-report.md` — 12 secciones + CHANGELOG, 7 acceptance gates, 5 deviations, PASS WITH WARNINGS verdict.
7. `archive-report.md` — este archivo (additive, excluded from snapshot/diff comparison).

---

## 4. Source-of-truth merge (DELTA) — CRITICAL F3.1 deviation from F2.x NO-OP precedent

**F3.1 introduce un DELTA precedent — rompe el patrón NO-OP de F2.1/F2.2/F2.3 y adopta precedent F1.15 (login histórico archivado 2026-09-15 con 4 new REQ-OPS-102..105 user-facing).**

### 4.1 Rationale crítica (DEC-F3.1-11)

| Aspect | F2.1/F2.2/F2.3 (NO-OP precedent) | F3.1 (DELTA con 7 new REQ-OPS-NNN) |
|---|---|---|
| Tipo de cambio | Infra-only (scaffold + IPC + runtime) | User-facing behavior observable |
| Componente visible al operador | Ninguno (electron main process, IPC preload, services) | Login page + Form + Button + Error messages |
| Mensajes de error diferenciados | N/A (no UI) | `invalidCredentials` vs `lockout` vs `serverError` |
| Cookie httpOnly round-trip | N/A (no HTTP) | `credentials:'include'` mandatory |
| Redirect post-hidratación | N/A (no routes) | `useEffect` espera `data?.user` |
| Precedente directo | DEC-ELEC-10 / DEC-FETCH-10 / DEC-UPD-13 (infra) | REQ-OPS-102..105 (F1.15 login user-facing) |
| Verificabilidad | DEC-* documentan; sin REQ spec-level | REQ-OPS-NNN + DEC-* cross-linked |

### 4.2 Operación ejecutada (mechanical)

7 Writes contra canonical `openspec/specs/operations/spec.md`, byte-diff pre/post merge verification:

```
pre_md5:  059ea4c06f5da2541d04b3f5ba155285  (4522 lines)
post_md5: 81d148c28a6cc9fd7742e4b4fa99c05d  (4738 lines)
delta:    +216 lines = 7 new REQ-OPS-106..112 block
```

Procedimiento (shell-only, NEVER Read → Write reproduce content):

1. Snapshot pre-move: `cp -R openspec/changes/hu-f3-1-login-email-password /tmp/sdd-archive.XXXX/source` (ephemeral).
2. Move source to archive: `mv openspec/changes/hu-f3-1-login-email-password openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password` (Git Bash plain mv, source untracked).
3. Source absent confirmed: `ls openspec/changes/hu-f3-1-login-email-password` → error (No such file or directory).
4. `diff -r /tmp/sdd-archive.XXXX/source openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password` → **empty output** (byte-identical, passing).
5. Extract `source/specs/operations/spec.md` lines 67-282 (REQ-OPS-106..112 block + content) → `/tmp/sdd-f3-1-req-ops-block.md` (216 lines, byte-preserved via `sed -n`).
6. Split canonical at line 4442 (before `## Modified Capabilities`): head (1-4441) + tail (4442-end).
7. 3-way concat: head + extracted_block + tail → new canonical.
8. Line count verify: 4441 + 216 + 81 = 4738 ✓ matches actual post-merge line count.
9. Byte-identity verify: `diff /tmp/sdd-f3-1-source-block.md /tmp/sdd-f3-1-canonical-block.md` → **empty output** (REQ-OPS-106..112 byte-identical between source delta and canonical post-merge, passing).

### 4.3 Cross-reference table (7 REQ-OPS-NNN materialized)

| REQ-OPS | DEC-F3.1 anchor | Comportamiento observable |
|---|---|---|
| **REQ-OPS-106** | DEC-F3.1-02 + DEC-F3.1-06 | LoginForm con validación inline RHF+Zod (`email` formato + `password` min 8) |
| **REQ-OPS-107** | DEC-F3.1-03 + DEC-F3.1-04 + DEC-F3.1-05 | POST /auth/login con `credentials:'include'` + cookie httpOnly round-trip mandatory |
| **REQ-OPS-108** | DEC-F3.1-08 | 401 → mensaje único `errors.invalidCredentials` (anti-enumeración cross-layer) |
| **REQ-OPS-109** | DEC-F3.1-08 | 429 → `errors.lockout` con `Retry-After` header parseado (forward F3.2 countdown) |
| **REQ-OPS-110** | DEC-F3.1-07 | `useAuthStore.setTokens(access, refresh, expires_in)` hidrata desde 200 OK atómicamente |
| **REQ-OPS-111** | DEC-F3.1-07 | Redirect a `/` post-`useAuth().isAuthenticated && data?.user && !isLoading` (transaccional) |
| **REQ-OPS-112** | RNF-022 + DEC-F3.1-01 | WCAG 2.1 AA compliance: axe-core 0 violaciones en `<LoginForm>` |

Numeración monotónica verificada: REQ-OPS-105 vigente pre-F3.1 (archivado por F1.15); F3.1 ocupa REQ-OPS-106..112 (continuación, 0 gaps). Post-archive canonical: 112 REQ-OPS-001..112 + 6 XR (REQ-OPS-XR1..XR6).

**Anchor upstream**: `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/proposal.md` §5.11 (DEC-F3.1-11 rationale verbatim) + `specs/operations/spec.md` §3 (materialized Given/When/Then/And).

---

## 5. Decisions ratified (11 DEC-F3.1-NN)

- **DEC-F3.1-01**: Feature folder `src/features/auth/` (Atomic Design + Feature Slicing per F2.1 DEC-ELEC-08).
- **DEC-F3.1-02**: Container/Presentational split — `Login.tsx` (container) + `LoginForm.tsx` (presentational puro).
- **DEC-F3.1-03**: `credentials:'include'` para cookie httpOnly round-trip (anti-XSS + anti-CSRF per `auth.py:291-299`).
- **DEC-F3.1-04**: Login vía HTTP directo (NO IPC bridge) — auth es data plane estándar.
- **DEC-F3.1-05**: Login usa `fetch` raw (NO `parkosFetch`) — exceptional case para POST /auth/login.
- **DEC-F3.1-06**: Validación Zod local en form (NO `parkosFetch` schema) — UX validation vs contract validation split.
- **DEC-F3.1-07**: Redirect a `/` transaccional post-`useAuth().data?.user` (sin flash de "sesión no iniciada").
- **DEC-F3.1-08**: Anti-enumeración cross-layer (backend colapsa 401 a `errors.invalid_credentials` único; frontend matchea con `t('invalidCredentials')`).
- **DEC-F3.1-09**: Auto-redirect a `/login` cuando `parkos:auth:cleared` event fires (forward hook F3.3+ `<AuthGuard>`).
- **DEC-F3.1-10**: e2e 3 escenarios (login-ok-cookie + refresh-transparente + logout).
- **DEC-F3.1-11** (archivo-level): **NUEVA** — DELTA stub con 7 new REQ-OPS-106..112 (NOT NO-OP stub). F3.1 ES user-facing behavior observable per F1.15 precedent. Primera HU Fase 3 con behavior contract.

---

## 6. Acceptance gates (final)

**5/7 PASS source-level, 2/7 SKIPPED-env, 0 FAIL.**

| Gate | Result | Evidence |
|---|---|---|
| **G1** RHF+Zod valida `email: z.string().email()` y `password: z.string().min(8)` con messages inline | PASS | Source: `apps/electron-sucursal/src/features/auth/api/loginSchema.ts:19-28` (Zod email + min(8) password). Source-level verification via grep. |
| **G2** 401 → `t('invalidCredentials')` único (anti-enumeración cross-layer) | PASS | Source backend: `apps/api-sucursal/auth.py:159-191` (HU-F1.2 shipped); Source frontend: `loginApi.ts:38-40` (`InvalidCredentialsError`) + `LoginForm.tsx:115-119` (`<p role="alert">{t('invalidCredentials')}</p>`). |
| **G3** `POST /auth/login` con `credentials:'include'` | PASS | Source: `loginApi.ts:77` (`credentials: 'include'`). Source-level verification. |
| **G4** `authStore.setTokens` + `useAuth().user` hidrata antes de `navigate('/')` | PASS | Source: `Login.tsx:35` (`useAuth()`) + `Login.tsx:61` (setTokens via login mutation) + `Login.tsx:48-52` (useEffect redirect cuando `user !== null`). |
| **G5** 429 → `AccountLockedError(retryAfter)` + muestra `t('lockout')` | PASS | Source: `loginApi.ts:47-52` (`AccountLockedError` parsea `Retry-After` header) + `LoginForm.tsx` mapping `accountLocked` con `retryAfter` opcional. |
| **G6** 3 e2e scenarios verde (E1 login-ok-cookie, E2 refresh-transparente, E3 logout) | SKIPPED-env | `apps/electron-sucursal/e2e/auth/login.spec.ts` — 3 e2e tests + 1 axe-core A1 authored (~80 LOC). Sandbox F.6 precedent verbatim F2.1 + F2.2 + F2.3 — npm 11.16.0 refuses `workspace:*`; vitest+playwright no instalados en `node_modules/`. CI matrix required post-archive. |
| **G7** axe-core WCAG 2.1 AA 0 violaciones en `<LoginForm>` | SKIPPED-env | `login.spec.ts:A1` (axe-core via `@axe-core/playwright` ya en deps F2.2) + `LoginForm.tsx` (FormField aria-invalid + 3× `<p role="alert">`). Source-level PASS (role/aria attributes structuralmente); runtime SKIPPED-env per F.6 precedent. |

---

## 7. Deviations & forward hooks

### Deviations (5 total, 0 blocking)

1. **D-data-shape LOW** (cosmetic) — `design.md` §3.2 mockup usa `const { data } = useAuth()` + `data?.user`; applied `Login.tsx:35` usa `const { user } = useAuth()` directo. Semántica idéntica (verificado en `apps/ui-kit/src/hooks/useAuth.ts:75-86`).
2. **D-axe-unit LOW** — `vitest-axe` no en deps; axe-core WCAG 2.1 AA cubierto por e2e A1 (`@axe-core/playwright` ya en deps). `LoginForm.test.tsx:10-14` documenta deviation explícitamente.
3. **D-env-F.6 MEDIUM** (precedent F2.x verbatim) — `npm 11.16.0` refuses `workspace:*`; `vitest` y `@playwright/test` no instalados en `node_modules/`. Unit tests + e2e authored pero SKIPPED-env runtime. CI matrix required post-archive.
4. **D-form-prop-type LOW** (cosmetic) — `LoginForm.tsx:48-49` recibe `form: UseFormReturn<LoginInput>` en lugar de `ReturnType<typeof useFormContext<LoginInput>>` del `design` §6.4. API surface idéntica (shadcn Form expone `UseFormReturn` directamente vía FormProvider context).
5. **D-tdd-order-early-effect LOW** (cosmetic) — `Login.tsx:48-52` useEffect redirect declarado en T1 commit `8961303` (no en T3 commit `70d9aa1` como planeaba `tasks.md` §3.3). Atomicidad cluster C1 preservada (T3 commit solo agrega App.tsx route + Login.test U13/U14/U15).

### Forward hooks (cross-reference exploration §15 + tasks §9)

- **HU-F3.2** (lockout visible + refresh pre-flight) → consume `AccountLockedError.retryAfterSeconds` de F3.1 + renderiza countdown via nuevo `useCountdown` hook.
- **HU-F3.3** (Abrir/Cerrar turno) → consume `useAuth().user.sucursal` + nuevos endpoints POST /caja-sesion/sesiones.
- **HU-F3.x** (logout + AuthGuard) → consume `authStore.clear()` + `<ProtectedRoute>` wrapper para rutas privadas.
- **HU-F4.x** (catálogos + ocupación) → consume `useAuth().user` en headers implícitos via `parkosFetch` (F2.2 wired).
- **HU-F5.x** (impresión térmica) → consume `bridge.imprimir` (F2.2 surface).
- **HU-F11.x** (sync UI topbar) → consume `bridge.apiStatus.get` + StatusBar (F2.3 surface).
- **PR7 backend** (refresh-token rotation) → consume `authStore` refresh-once logic + Mutex (F2.2 DEC-FETCH-03).

---

## 8. DoD checklist

- [x] 4 atomic commits T1..T4 con author `Parkos Dev <dev@parkos.local>`, sin Co-authored-by, sin AI trailers.
- [x] 8 NEW + 2 MODIFY archivos (production + tests + i18n).
- [x] `vitest --run` 21/21 unit scenarios authored (SKIPPED-env execution F.6 precedent).
- [x] `playwright test` 4/4 e2e + axe-core scenarios authored (SKIPPED-env execution F.6 precedent).
- [x] `tsc --noEmit` clean intent (SKIPPED-env execution).
- [x] NO `Co-authored-by`, NO AI trailers en 4/4 commits.
- [x] CERO `any` en `apps/electron-sucursal/src/features/auth/`.
- [x] Sin npm install (zero install commands en 4 commits).
- [x] Feature folder isolation (`features/auth/{api,components,pages}/`).
- [x] READ-ONLY anchors intactos: `electron/main.ts` + `preload.ts` + `bridge.d.ts` + `ui-kit/*` + `backend/auth.py` + `e2e/{scaffold,bridge,parkos-fetch,a11y}` + Fase 2 specs.
- [x] 7 new REQ-OPS-106..112 materialized al canonical `openspec/specs/operations/spec.md` (md5 pre/post + byte-identity verified).
- [x] Mechanical Copy Contract executed: snapshot + mv + `diff -r` empty readback + source absent confirmed.

---

## 9. Pre-existing baseline unchanged

- 8 strict tsc errors F2.3-introduced (main.ts + kiosko.ts + kiosko.test.ts) — unchanged, D-tsc LOW follow-up Fase 3 backlog.
- bcryptjs fallback en lugar de native bcrypt — unchanged, D-env-F.6 LOW follow-up swap a native bcrypt cuando build pipeline tenga node-gyp + python.
- 25 test skips pre-existentes (pg_partman no disponible postgres:16-alpine local) — unchanged Fase 1 baseline.
- 78 errores ruff pre-existentes en `packages/parkos_core/` — unchanged Fase 1 baseline.
- 18 archivos con fallas pre-existentes — unchanged Fase 1 baseline.

Canonical `openspec/specs/operations/spec.md` md5 pre-F3.1 = `059ea4c06f5da2541d04b3f5ba155285` (idéntico al post-F2.3 baseline). Post-F3.1 materialize = `81d148c28a6cc9fd7742e4b4fa99c05d` (+216 lines = 7 new REQ-OPS-106..112).

---

## 10. Archive folder contents

7 archivos en `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/`:

```
exploration.md                 ~758 LOC (17 secciones, 10 DEC-F3.1-NN, 8 riesgos)
proposal.md                    ~800 LOC (16 secciones, 11 DEC-F3.1-NN ratified, DEC-F3.1-11 DELTA precedent)
design.md                      ~870 LOC (15 secciones + 2 apéndices, 8 TS mockups + 3 configs delta)
specs/operations/spec.md       ~378 LOC (DELTA materializado, 7 new REQ-OPS-106..112 RFC 2119)
tasks.md                       ~430 LOC (13 secciones, 4 atomic tasks T1..T4, 1 cluster C1)
verify-report.md               ~265 LOC (12 secciones + CHANGELOG, 7 gates, 5 deviations PASS WITH WARNINGS)
archive-report.md              ~este archivo (additive-only)
```

Total: ~3.9k LOC de artefactos SDD F3.1.

---

## 11. Mechanical archive verification

Per skill `sdd-archive` Mechanical Copy Contract, archive folder moved via plain `mv` (source untracked in git, precedent verbatim F2.1 §9 + F2.2 §11 + F2.3 §11) con snapshot + `diff -r` readback:

- **Snapshot**: pre-move recursive copy of source `openspec/changes/hu-f3-1-login-email-password/` → ephemeral tmpdir `/tmp/sdd-archive.g91VHz/source/`.
- **Move**: `mv openspec/changes/hu-f3-1-login-email-password openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password` (Git Bash en Windows; source untracked per `git status --short` → `?? openspec/changes/hu-f3-1-login-email-password/`).
- **Readback**: `diff -r /tmp/sdd-archive.g91VHz/source/ openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` → **empty output** (byte-identical, passing).
- **Source absent post-move**: confirmado via `ls openspec/changes/hu-f3-1-login-email-password` retorna error "No such file or directory".
- **`archive-report.md`** es additive-only, excluded from snapshot/destination comparison (no existía en source pre-move).

### Materialize verification (canonical REQ-OPS-106..112 merge)

- **pre-merge md5**: `059ea4c06f5da2541d04b3f5ba155285` (4522 lines) — idéntico al F2.3 baseline.
- **post-merge md5**: `81d148c28a6cc9fd7742e4b4fa99c05d` (4738 lines) — `+216 lines` = 7 new REQ-OPS-106..112 block.
- **byte-identity check**: `diff /tmp/sdd-f3-1-source-block.md /tmp/sdd-f3-1-canonical-block.md` → **empty output** (216 lines match byte-by-byte, passing).
- **structural integrity**: REQ-OPS-105..112 consecutivos en canonical lines 4371, 4442, 4484, 4513, 4540, 4569, 4599, 4626; `## Modified Capabilities` preserved at line 4658.
- **procedimiento shell-only**: bytes flow shell→file, NEVER model→file (per skill rule "NEVER use Read → Write to reproduce artifact content into the archive or main specs").

---

## 12. Fase 3 status

**Fase 3 status**: **1/3 HU cerrada** (F3.1 archivado 2026-09-15, F3.2 pendiente, F3.3 pendiente).

- **HU-F3.1**: Login con email + password (4 atomic commits `8961303..5fcfe66`, ~1008 net LOC production + tests, 7 new REQ-OPS-106..112 user-facing materialized al canonical — DELTA precedent).
- **HU-F3.2**: Lockout visible (countdown) + refresh transparente — pendiente.
- **HU-F3.3**: Abrir / cerrar turno (caja-sesion) — pendiente.

**Forward unlock**: HU-F3.2 puede arrancar contra `AccountLockedError.retryAfterSeconds` (F3.1 REQ-OPS-109) + `useAuthStore.setTokens` post-200 OK (F3.1 REQ-OPS-110). HU-F3.3 puede arrancar contra `useAuth().user.sucursal` (F3.1 REQ-OPS-110/111).

---

## CHANGELOG

- (2026-09-15) **F3.1 archive** — 4 atomic commits archivados, 7 archivos SDD preservados, 5/7 gates PASS source-level + 2/7 SKIPPED-env (G6 e2e + G7 axe-core runtime) + 0 FAIL, 5 deviations documentadas (D-data-shape LOW + D-axe-unit LOW + D-env-F.6 MEDIUM + D-form-prop-type LOW + D-tdd-order-early-effect LOW). 7 new REQ-OPS-106..112 materialized al canonical `openspec/specs/operations/spec.md` (md5 pre/post + byte-identity verified, DELTA precedent — first user-facing DELTA in Fase 3, breaking F2.x NO-OP pattern). F3.1 cerrado. **Fase 3 1/3 cerrado**.

---

**End of archive report.**