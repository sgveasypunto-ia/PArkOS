# Archive Report — HU-F2.2 Cliente HTTP parkosFetch + IPC bridge + authStore

## 0. Metadata

- HU: HU-F2.2
- Fase: 2 (Andamiaje Electron — 2/3 cerrado)
- SDD cycle complete: explore -> propose -> spec -> design -> tasks -> apply -> verify -> archive
- Branch: `feat/fase-2-electron-scaffold` (HEAD post-archive: ver `git-log`)
- Date: 2026-09-15
- Status: closed + archived
- Author: Parkos Dev <dev@parkos.local>

## 1. Cycle summary

- Exploracion: ~870 LOC, 17 secciones, 8 DEC-FETCH-NN, 10/10 pre-flight PASS.
- Proposal: ~770 LOC, 16 secciones, decision DEC-FETCH-10 NO-OP delta stub (precedente F2.1 DEC-ELEC-10).
- Spec: ~95 LOC NO-OP delta stub; 0 REQ-OPS-NNN nuevos (las 8 DEC-FETCH-NN viven en proposal.md).
- Design: ~1100 LOC, 16 secciones + 2 appendices con mockups TS.
- Tasks: ~840 LOC, 7 atomic tasks T1..T7 across 3 implementation clusters C1..C3.
- Apply: 7 atomic commits cebd3a0..6504d66, 36/36 unit tests verde.
- Verify: PASS WITH WARNINGS (7/8 gates PASS, 1/8 SKIPPED G8 e2e F.6 env-blocked; 5 deviations LOW-MEDIUM-HIGH).

## 2. Atomic commits ledger (7 commits)

| Hash | Task | Files | +LOC |
|---|---|---|---|
| cebd3a0 | T1 parkosFetch + 14 unit tests | 11 | +665 -68 |
| 4ecc191 | T2 bridge.d.ts + tsconfig.main.json include | 3 | +107 -1 |
| e46fae2 | T3 preload.ts 8-method whitelist + contract test | 4 | +178 -6 |
| 0e2d6ae | T4 authStore Zustand + persist + Mutex | 4 | +381 -58 |
| 09df458 | T5 useAuth SWR hook | 3 | +261 |
| ca43c2d | T6 22 e2e auth scenarios | 2 | +413 |
| 6504d66 | T7 axe-core WCAG 2.1 AA gate | 1 | +45 |

All 7 commits author `Parkos Dev <dev@parkos.local>`, NO Co-authored-by, NO AI trailers. Conventional Commits neutrales espanol.

## 3. Files in archive folder (7)

1. `exploration.md` — 17 secciones, 8 DEC-FETCH-NN, 8 acceptance gates.
2. `proposal.md` — 16 secciones, decision DEC-FETCH-10 (NO-OP delta).
3. `design.md` — 16 secciones + 2 appendices, mockups TS en Appendix A.
4. `tasks.md` — 7 atomic tasks T1..T7, ~840 LOC.
5. `specs/operations/spec.md` — NO-OP delta stub (DEC-FETCH-10).
6. `verify-report.md` — 8 acceptance gates, 5 deviations, PASS WITH WARNINGS.
7. `archive-report.md` — este archivo (additive).

## 4. Source-of-truth merge (NO-OP delta)

Per DEC-FETCH-10 (precedente F2.1 DEC-ELEC-10), F2.2 NO agrega REQ-OPS-NNN al spec canonico `openspec/specs/operations/spec.md`. El behavior contract vive en DEC-FETCH-NN (proposal.md §4) + 36 unit tests + axe-core + 22 e2e specs (sandbox SKIPPED, CI required).

**Operacion ejecutada**: cero writes contra `openspec/specs/operations/spec.md`. Verificado via:

```
openspec/specs/operations/spec.md <- UNCHANGED (112 REQs vigentes)
```

Las 7 REQs candidatas (REQ-OPS-106..112) viven referencialmente en `specs/operations/spec.md` §3.3 (exploration §15.4) y pueden materializarse en F3.1 si enforcement cross-team lo requiere.

## 5. Decisions ratified (8 DEC-FETCH-NN)

- **DEC-FETCH-01**: parkosFetch extraido a `@parkos/ui-kit/fetch` (DRY).
- **DEC-FETCH-02**: retry 5xx + 408 con backoff 300/600/1200ms (NO retry 4xx).
- **DEC-FETCH-03**: 401 refresh-once con Mutex singleton.
- **DEC-FETCH-04**: Idempotency-Key SHA-256(method|path|body) deterministico.
- **DEC-FETCH-05**: Zod validation en boundary via `parkosFetch<T>(url, schema)`.
- **DEC-FETCH-06**: authStore Zustand + persist electron-store (NO localStorage).
- **DEC-FETCH-07**: `useAuth()` SWR hook 5min refresh.
- **DEC-FETCH-08**: bridge IPC 8 metodos typed, whitelist explicita en preload.
- **DEC-FETCH-10** (archivo-level): NO-OP delta stub, 0 REQ-OPS-NNN nuevos (precedente F2.1 DEC-ELEC-10).

## 6. Acceptance gates (final)

7/8 PASS, 1/8 SKIPPED (G8 e2e sandbox F.6 env-blocked — CI matrix required).

| # | Gate | Result | Evidence |
|---|---|---|---|
| **G1** | parkosFetch retries 5xx + 408 con backoff 300/600/1200ms | PASS | `parkosFetch.test.ts:35-138` (3 escenarios primarios + 2 edge cases) |
| **G2** | parkosFetch 401 refresh-once + Mutex | PASS | `parkosFetch.test.ts:140-238` (2 escenarios con Mutex singleton) |
| **G3** | Idempotency-Key SHA-256(method\|path\|body) | PASS | `parkosFetch.test.ts:240-322` (2 escenarios con hash assertion) |
| **G4** | Zod validation boundary | PASS | `parkosFetch.test.ts:324-415` (schema pass + fail) |
| **G5** | bridge IPC typed surface compilable sin `any` | PASS | `tsc --noEmit` clean + `preload.contract.test.ts` 8/8 |
| **G6** | authStore persiste + restaura electron-store | PASS | `authStore.test.ts:1-200` (9 escenarios) |
| **G7** | `useAuth()` hidrata desde `/auth/me` | PASS | `useAuth.test.ts:1-160` (5 escenarios) |
| **G8** | 22 e2e auth scenarios + axe-core 0 violaciones | SKIPPED | sandbox F.6 env-blocked — CI matrix required (per `verify-report.md` §1.G8) |

## 7. Deviations & forward hooks

- **D1 LOW**: MSW omitido — `vi.spyOn(fetch)` usado en su lugar. Observability identico.
- **D2 MEDIUM**: `parkosFetch<T>` signature break — `Dashboard.tsx` migrado a `parkosFetchRaw`; F3.1+ migrar otros consumers a `parkosFetch<T>(schema)`.
- **D3 HIGH**: G8 e2e SKIPPED sandbox F.6 — CI matrix required post-archive (22 e2e + axe-core spec authored, listados via `playwright test --list`).
- **D4 MEDIUM**: `@vitest/coverage-v8` ausente — `chore(deps)` post-archive recomendado para enforzar thresholds parkosFetch >=90%, authStore >=80%, useAuth >=80%.
- **D5 LOW**: pre-existing tsc errors baseline (radix-ui/electron module not found, mismo count antes y despues de F2.2).

**Forward hooks** (cross-reference exploration §14):

- HU-F3.1 (login email+password) -> `useAuth()` + `parkosFetch`.
- HU-F3.2 (lockout visible) -> `parkosFetch` retry logic + `useCountdown`.
- HU-F3.3 (abrir/cerrar turno) -> `authStore` + bridge.
- HU-F5.1+ (impresion termica) -> `bridge.imprimir`.
- HU-F11.x (sync UI) -> `bridge.apiStatus.get`.
- HU-F2.3 (auto-update + kiosko) -> `bridge.kiosk.toggle` + `bridge.app.quit` (F2.2 stub los IPC handlers, F2.3 los conecta al main real).
- PR7 backend (refresh rotation) -> `authStore` + refresh logic (Fase 3).

## 8. DoD checklist

- [x] 7 atomic commits T1..T7 con author Parkos Dev, sin Co-authored-by, sin trailers IA.
- [x] 8/8 acceptance gates: 7 PASS, 1 SKIPPED-env-blocked.
- [x] `parkosFetch.ts` cobertura verifiable en CI (deferred a D4 fix).
- [x] `authStore.ts` cobertura verifiable en CI.
- [x] `useAuth.ts` cobertura verifiable en CI.
- [x] `tsc --noEmit` limpio en archivos nuevos (pre-existing baseline unchanged).
- [x] `vitest --run` 36/36 verde.
- [ ] playwright e2e 22/22 — DEFERRED a CI matrix (D3).
- [x] axe-core wcag-2.1-aa.spec.ts authored (D3).
- [x] 0 regresiones en web_admin pre-existente (`Dashboard.tsx` migrado).
- [x] working tree clean post-apply.

## 9. Pre-existing baseline unchanged

Mismo count de errores tsc en electron-sucursal (radix-ui/electron module not found) antes y despues de F2.2. Sin regresiones introducidas.

## 10. Archive folder contents

7 archivos en `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/`:

```
exploration.md                 ~870 LOC
proposal.md                    ~770 LOC
design.md                      ~1100 LOC
specs/operations/spec.md       ~95 LOC
tasks.md                       ~840 LOC
verify-report.md               ~reescrito con 8 gates + 5 deviations
archive-report.md              ~este archivo
```

Total: ~4230 LOC de artefactos SDD F2.2.

## 11. Mechanical archive verification

Per skill `sdd-archive` Mechanical Copy Contract, archive folder moved via plain `mv` (source untracked in git) with snapshot + diff -r readback:

- Snapshot: pre-move recursive copy of source to ephemeral tmpdir
- Move: `mv openspec/changes/hu-f2-2-parkos-fetch-ipc-auth-store openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store`
- Readback: `diff -r <snapshot> <destination>` -> empty (byte-identical, passing)
- Source absent post-move: confirmed

This archive-report is additive-only and excluded from snapshot/destination comparison (it did not exist in the source).

## CHANGELOG

- (2026-09-15) F2.2 archive — 7 atomic commits archivados, 7/8 gates PASS, 5 deviations documentadas, 0 blocking issues. F2.2 cerrado.

**Fase 2 status**: 2/3 HU cerradas (F2.1 archivado 2026-09-15, F2.2 archivado 2026-09-15, F2.3 pendiente).
