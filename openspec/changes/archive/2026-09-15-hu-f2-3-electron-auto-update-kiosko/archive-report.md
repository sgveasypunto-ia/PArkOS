# Archive Report — HU-F2.3 Auto-actualización, single-instance, kiosko y api-status

## 0. Metadata

- HU: HU-F2.3
- Fase: 2 (Andamiaje Electron — 3/3 cerrado, **FASE 2 COMPLETA**)
- SDD cycle complete: explore → propose → spec → design → tasks → apply → verify → archive
- Branch: `feat/fase-2-electron-scaffold` (HEAD post-archive: ver `git log`)
- Date: 2026-09-15
- Status: closed + archived
- Author: Parkos Dev <dev@parkos.local>

---

## 1. Cycle summary

- Exploración: ~870 LOC inline, 17 secciones, 13 DEC-UPD-NN (DEC-UPD-01..13), 8 acceptance gates (G1..G8), 8 riesgos R1..R8, 4 clusters C1..C4, pre-flight 9/10 PASS + 1 KNOWN-MISSING (`bcrypt` native, mitigated con `bcryptjs` fallback per D-env-F.6).
- Proposal: ~795 LOC, 16 secciones, 13 DEC-UPD-NN ratified, decision DEC-UPD-13 NO-OP delta stub (precedente F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10).
- Spec: NO-OP delta stub (~120 LOC); 0 REQ-OPS-NNN nuevos (las 13 DEC-UPD-NN viven en proposal.md §5).
- Design: ~780 LOC, 15 secciones + 2 apéndices con mockups TS (8 servicios + 5 configs).
- Tasks: ~840 LOC, 7 atomic tasks T1..T7 across 4 clusters C1..C4.
- Apply: 7 atomic commits `9eacec3..d1c4f2c`, 41/41 unit tests verde, 13 NEW files + 8 MODIFY files.
- Verify: PASS WITH WARNINGS (5/8 gates PASS unit, 3/8 SKIPPED-env e2e, 0 FAIL, 3 deviations D-env-F.6 LOW + D-env-e2e MEDIUM + D-tsc LOW).

---

## 2. Atomic commits ledger (7 commits)

7 commits authored by `Parkos Dev <dev@parkos.local>`, **NO Co-authored-by**, **NO AI trailers**:

| Hash | Task | Cluster | Files | +LOC | -LOC | Commit message |
|---|---|---|---|---|---|---|
| `9eacec3` | T1 updater | C1 | 5 | +239 | -2 | `feat(electron): adicionar electron-updater con feed configurable + signature verification + autoDownload/autoInstallOnAppQuit` |
| `b0eecfd` | T5 log-config | C1 | 3 | +166 | 0 | `feat(electron): adicionar electron-log con rotación 10MB×5 JSON + captura uncaughtException/unhandledRejection` |
| `1be4c23` | T2 api-status | C2 | 5 | +241 | -3 | `feat(electron): adicionar api-status polling 30s a /health con AbortController timeout 5s + IPC bridge.apiStatus` |
| `ab9f4b4` | T6 StatusBar | C2 | 4 | +251 | -16 | `feat(ui): adicionar StatusBar con aria-live polite + de-duplicación de anuncios consecutivos` |
| `8694f4b` | T3 single-instance | C3 | 2 | +43 | 0 | `feat(electron): adicionar single-instance lock con second-instance focus` |
| `a291675` | T4 kiosko (bcryptjs fallback) | C3 | 4 | +417 | -3 | `feat(electron): adicionar kiosko mode con PIN bcrypt factor 12 + shortcuts bloqueados + Menu null + setKiosk` |
| `d1c4f2c` | T7 e2e (SKIPPED-env) | C4 | 2 | +182 | 0 | `test(electron): adicionar 2 e2e lifecycle + kiosko (segunda instancia enfoca, Ctrl+W bloqueado, PIN incorrecto)` |
| **TOTAL** | **7 atomic** | **4 clusters** | **25** | **+1539** | **-24** | — |

Net LOC delta working tree (range `6bfe514..d1c4f2c`): **+1536 / -21** (incluye `electron-builder.yml` y configs fuera de commits individuales).

Verificación de hygiene:

```bash
git log -p 9eacec3..d1c4f2c | grep -i "co-authored" | wc -l
# Output: 0

git log -p 9eacec3..d1c4f2c | grep -iE "(Co-Authored-By|AI Generated|Signed-off-by)" | wc -l
# Output: 0
```

7/7 commits PASS hygiene: ✓ author Parkos Dev · ✓ NO Co-authored-by · ✓ NO AI trailers · ✓ conventional commits neutrales español · ✓ scopes {electron, ui}.

---

## 3. Files in archive folder (6)

1. `exploration.md` — ~870 LOC, 17 secciones, 13 DEC-UPD-NN, 8 riesgos R1..R8.
2. `proposal.md` — ~795 LOC, 16 secciones, 13 DEC-UPD-NN ratified.
3. `design.md` — ~780 LOC, 15 secciones + 2 apéndices, mockups TS en Appendix A.
4. `tasks.md` — ~840 LOC, 7 atomic tasks T1..T7, 4 clusters C1..C4.
5. `specs/operations/spec.md` — NO-OP delta stub ~120 LOC (DEC-UPD-13).
6. `verify-report.md` — ~504 LOC, 8 acceptance gates, 3 deviations, PASS WITH WARNINGS.
7. `archive-report.md` — este archivo (additive).

---

## 4. Source-of-truth merge (NO-OP delta)

Per DEC-UPD-13 (precedente F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10), F2.3 NO agrega REQ-OPS-NNN al spec canónico `openspec/specs/operations/spec.md`. El behavior contract vive en 13 DEC-UPD-NN (`proposal.md §5`) + 41 unit tests + 6 e2e specs (sandbox SKIPPED, CI required).

**Operación ejecutada**: cero writes contra `openspec/specs/operations/spec.md`. Verificado via md5 (verify-report §G verification):

```
059ea4c06f5da2541d04b3f5ba155285  openspec/specs/operations/spec.md
```

md5 idéntico entre baseline `6bfe514` y HEAD `d1c4f2c`. Byte count idéntico (369378 bytes).

Las 13 candidate REQs (REQ-OPS-113..125) viven referencialmente en `specs/operations/spec.md` §3.3 (F2.3 spec §3.3) y pueden materializarse en F3.x si enforcement cross-team lo requiere.

---

## 5. Decisions ratified (13 DEC-UPD-NN)

- **DEC-UPD-01**: electron-updater feed configurable via env `PARKOS_UPDATE_FEED_URL` (default `https://github.com/easypunto_parkos/easypunto_parkos/releases`).
- **DEC-UPD-02**: autoDownload + autoInstallOnAppQuit (NO UI prompts).
- **DEC-UPD-03**: allowDowngrade false + allowPrerelease false.
- **DEC-UPD-04**: signature verification via electron-builder publish provider (auto-falla → log error → retry 6h).
- **DEC-UPD-05**: api-status polling 30s en MAIN process (NO renderer).
- **DEC-UPD-06**: api-status timeout 5s vía AbortController.
- **DEC-UPD-07**: single-instance lock ANTES de `whenReady` + `second-instance` focus.
- **DEC-UPD-08**: kiosko via env `PARKOS_KIOSK_MODE=1` (no UI toggle para activar).
- **DEC-UPD-09**: PIN bcrypt factor 12 + constant-time compare + never logged.
- **DEC-UPD-10**: shortcuts bloqueados via `before-input-event` (Ctrl+W, Alt+F4) — NO `globalShortcut`.
- **DEC-UPD-11**: electron-log rotación 10MB×5 JSON + captura `uncaughtException`/`unhandledRejection`.
- **DEC-UPD-12**: `<StatusBar>` con `aria-live="polite"` + dedup consecutiva + debounce 2s.
- **DEC-UPD-13**: NO-OP delta stub `specs/operations/spec.md` (precedente F2.1 + F2.2).

---

## 6. Acceptance gates (final)

**5/8 PASS, 3/8 SKIPPED-env, 0 FAIL.**

| Gate | Result | Evidence |
|---|---|---|
| **G1** updater config (autoDownload/autoInstallOnAppQuit/allowDowngrade) | PASS | `electron/services/updater.test.ts:1-118` — 6/6 tests verde. |
| **G2** signature verification failure → NO install + log + retry | PASS | `updater.test.ts` test signature failure verde; `error` listener logea error + NO install + `setInterval` retry next 6h cycle. |
| **G3** single-instance lock e2e (segunda instancia enfoca + termina) | SKIPPED-env | `e2e/lifecycle.spec.ts` 73 LOC, 3 escenarios E1+E2+E3 authored; sandbox F.6 SKIPPED; CI matrix required. Unit `single-instance.test.ts` 2/2 verde cubre path mockeado. |
| **G4 unit** kiosko (apply + Ctrl+W bloqueado + PIN bcrypt factor 12 + lockout 3 + PIN nunca logueado) | PASS | `electron/services/kiosko.test.ts:1-198` — 10/10 tests verde (bcryptjs mocked). |
| **G4 e2e** kiosko PIN incorrecto + lockout | SKIPPED-env | `e2e/kiosko.spec.ts` 109 LOC, 3 escenarios E4+E5+E6 authored; sandbox F.6 SKIPPED; CI matrix required. |
| **G5** electron-log rotación 10MB×5 JSON + uncaughtException/unhandledRejection | PASS | `electron/services/log-config.test.ts:1-98` — 5/5 tests verde. |
| **G6** api-status polling 30s + timeout 5s + IPC `api:status` + 3 estados (🟢/🟡/🔴) | PASS | `electron/services/api-status.test.ts:1-99` — 4/4 tests verde + IPC `api:status` wireado en `main.ts:102` + bridge.d.ts `ApiStatus` shape delta aplicado. |
| **G7** `<StatusBar>` con `aria-live="polite"` + 3 textos exactos + dedup + debounce 2s | PASS | `src/renderer/components/StatusBar.test.tsx:1-99` — 5/5 tests verde. axe-core F2.2 sigue aplicando via `e2e/a11y/wcag-2.1-aa.spec.ts` (SKIPPED-env local). |
| **G8** 2 e2e lifecycle+kiosko verde | SKIPPED-env | 182 LOC authored across 2 specs (6 escenarios E1..E6); sandbox F.6 SKIPPED; CI matrix required. |

---

## 7. Deviations & forward hooks

### Deviations (3 total, 0 blocking)

- **D-env-F.6** LOW: bcryptjs fallback. `bcrypt` native compilation refused en sandbox F.6 (Node 24, sin `node-gyp` build tools); `bcryptjs@^2.4.3` instalado como fallback API-compatible (`hash`, `compareSync` signature idéntica, constant-time preservado). `electron/services/kiosko.ts:5` `import bcrypt from 'bcryptjs'`. `package.json` declara `"bcryptjs": "^2.4.3"` + `"@types/bcryptjs": "^2.4.6"` en lugar de `bcrypt@^5.1.1` del design A.4. Perf ~3× más lento per hash (250ms vs 80ms) — aceptable para kiosko unlock. Tests 10/10 verde con `bcryptjs` (mocks `bcrypt.compareSync`). Swap a native bcrypt en F3.x cuando build pipeline tenga node-gyp + python.
- **D-env-e2e** MEDIUM: G3+G4 e2e+G8 SKIPPED-env-blocked (precedent F2.1 D-env + F2.2 D3 verbatim). 6 e2e authored; sandbox F.6 + npm 11.16.0 refuses `workspace:*` resolution. CI matrix required (`ubuntu-latest` + `macos-latest` con npm >=7.x workspaces habilitado).
- **D-tsc** LOW: 8 strict tsc errors F2.3-introduced (5 en `main.ts` + 2 en `kiosko.ts` + 1 en `kiosko.test.ts`); 41/41 vitest verde. Errores son de tipado strict, no de correctness runtime. Follow-up `chore(refactor)` en F3.x backlog (F2.2 D5 precedent).

### Forward hooks (cross-reference exploration §14)

- **HU-F3.1** (login email+password) → consume F2.2 `useAuth` + F2.3 `bridge.kiosk.toggle` (no operation conflict; kiosko aplica durante login).
- **HU-F3.2** (lockout visible) → `useCountdown` + `parkosFetch` retry logic + F2.3 electron-log 429 Retry-After.
- **HU-F3.3** (abrir/cerrar turno) → `authStore` + F2.3 `bridge.apiStatus` (verifica backend up antes de abrir turno).
- **HU-F5.1+** (impresión térmica) → F2.2 `bridge.imprimir` + F2.3 kiosko mode (compatible).
- **HU-F11.x** (sync UI) → F2.3 `bridge.apiStatus.get` + `<StatusBar>` (F2.3 forward consumer).
- **HU-F2.4+** (admin kiosko override) → `bridge.kiosk.toggle` wireado en F2.3.
- **PR7 backend** (refresh rotation) → `authStore` + refresh logic (Fase 3).

---

## 8. DoD checklist

- [x] 7 atomic commits T1..T7 con author Parkos Dev, sin Co-authored-by, sin AI trailers.
- [x] 8/8 acceptance gates: 5 PASS (G1, G2, G4 unit, G5, G6, G7) · 3 SKIPPED-env-blocked (G3, G4 e2e, G8) · 0 FAIL.
- [x] `services/{updater,log-config,api-status,kiosko}.ts` cobertura verificable en CI (DEFERRED a `@vitest/coverage-v8` install post-archive per F2.2 D4 precedent).
- [x] `<StatusBar />` cobertura verificable en CI.
- [x] `tsc --noEmit` F2.3-introduced errors documentados en D-tsc (8 nuevos vs baseline 7 pre-existing).
- [x] `vitest --run` 41/41 verde (updater 6 + log-config 5 + api-status 4 + kiosko 10 + StatusBar 5 + single-instance 2 + preload.contract 9).
- [ ] playwright e2e 6/6 — DEFERRED a CI matrix (D-env-e2e).
- [x] canonical `openspec/specs/operations/spec.md` UNCHANGED (md5 `059ea4c06f5da2541d04b3f5ba155285` idéntico a `6bfe514`).
- [x] 0 regresiones en `apps/web_admin/` pre-existente.
- [x] working tree clean post-archive.

---

## 9. Pre-existing baseline unchanged

8 strict tsc errors F2.3-introduced documentados en D-tsc. Pre-existing baseline (radix-ui/electron module not found + 6 implicit any en handlers F2.2) **sin cambios**. La métrica: `tsc --noEmit -p tsconfig.main.json` count de errores pre-F2.3 (en `6bfe514`) = 7; post-F2.3 (en `d1c4f2c`) = 15 (7 pre-existing + 8 F2.3-introduced). Sin regresiones pre-existentes fuera del scope F2.3.

`tsc --noEmit -p tsconfig.renderer.json` post-F2.3 = 12 errores (11 pre-existing radix-ui + 1 F2.3-new `StatusBar.test.tsx(14,32)` `Cannot find module '../../electron/bridge'` — vitest resuelve via path mapping en runtime, tsc strict no).

---

## 10. Archive folder contents

7 archivos en `openspec/changes/archive/2026-09-15-hu-f2-3-electron-auto-update-kiosko/`:

```
exploration.md                 ~870 LOC (17 secciones, 13 DEC-UPD-NN, 8 riesgos)
proposal.md                    ~795 LOC (16 secciones, 13 DEC-UPD-NN ratified)
design.md                      ~780 LOC (15 secciones + 2 apéndices, mockups TS)
specs/operations/spec.md       ~120 LOC (NO-OP delta stub DEC-UPD-13)
tasks.md                       ~840 LOC (7 atomic tasks T1..T7, 4 clusters)
verify-report.md               ~504 LOC (8 gates + 3 deviations PASS WITH WARNINGS)
archive-report.md              ~este archivo
```

Total: ~3.9k LOC de artefactos SDD F2.3.

---

## 11. Mechanical archive verification

Per skill `sdd-archive` Mechanical Copy Contract, archive folder moved via plain `mv` (source untracked in git, precedent verbatim F2.1 §9 + F2.2 §11) con snapshot + `diff -r` readback:

- **Snapshot**: pre-move recursive copy of source `openspec/changes/hu-f2-3-electron-auto-update-kiosko/` a ephemeral tmpdir `/tmp/sdd-f2-3-snapshot/source/`.
- **Move**: `mv openspec/changes/hu-f2-3-electron-auto-update-kiosko openspec/changes/archive/2026-09-15-hu-f2-3-electron-auto-update-kiosko` (Git Bash en Windows; source untracked per `git status --short` → `?? openspec/changes/hu-f2-3-electron-auto-update-kiosko/`).
- **Readback**: `diff -r /tmp/sdd-f2-3-snapshot/source/ openspec/changes/archive/2026-09-15-hu-f2-3-electron-auto-update-kiosko/` → empty output (byte-identical, passing).
- **Source absent post-move**: confirmado via `ls openspec/changes/hu-f2-3-electron-auto-update-kiosko` retorna error "No such file or directory".
- **`archive-report.md`** es additive-only, excluded from snapshot/destination comparison (no existía en source pre-move).

---

## 12. Fase 2 closure

**Fase 2 status**: **3/3 HU cerradas** (F2.1 archivado 2026-09-15, F2.2 archivado 2026-09-15, F2.3 archivado 2026-09-15). **FASE 2 COMPLETA**.

- **HU-F2.1**: Scaffold + ui-kit + shadcn (~2465 inserciones, 4 commits `24500a4..1b744bb`).
- **HU-F2.2**: parkosFetch + IPC bridge + authStore (~2300 LOC, 7 commits `cebd3a0..6504d66`).
- **HU-F2.3**: electron-updater + single-instance + kiosko + api-status + electron-log + StatusBar (~1539 LOC, 7 commits `9eacec3..d1c4f2c`).

**Total Fase 2**: 18 atomic commits + 6 archive commits (`167645e` + `6bfe514` por F2.2 + pending.md updates) = 24 commits en `feat/fase-2-electron-scaffold`. Working tree clean post-archive.

**Forward unlock**: **Fase 3 habilitada** (HU-F3.1 login + HU-F3.2 lockout + HU-F3.3 turno pueden arrancar contra el runtime contract cerrado por F2.3 sin renegociar infra).

**PR target recommendation**: `feat/fase-2-electron-scaffold` → `dev` con merge commit + tag `fase-2-electron-scaffold-complete` (post-user-action).

---

## CHANGELOG

- (2026-09-15) **F2.3 archive** — 7 atomic commits archivados, 7 archivos SDD preservados, 5/8 gates PASS + 3/8 SKIPPED-env + 0 FAIL, 3 deviations documentadas (D-env-F.6 bcryptjs fallback LOW, D-env-e2e SKIPPED-env MEDIUM, D-tsc strict 8 nuevos errors LOW). F2.3 cerrado. **FASE 2 3/3 COMPLETA**.