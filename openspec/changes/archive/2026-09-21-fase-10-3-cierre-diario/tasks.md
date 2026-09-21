# Tasks: HU-F10.3 — Cierre Diario (Multi-Session Daily Reconciliation)

## Header

| Field | Value |
|---|---|
| Change | `fase-10-3-cierre-diario` |
| Phase | sdd-tasks (third and final HU of Fase 10) |
| Inputs read | `proposal.md` (Engram #1908), `specs/spec.md` (Engram #1909, REQ-OPS-163..169), `design.md` (Engram #1910), F10.1 + F10.2 archived tasks/design, `plan.md:2246-2264`, `apps/electron-sucursal/package.json` |
| Status | ready-for-apply |
| Preflight | pace=`auto`, artifact=`hybrid`, delivery=`ask-on-risk`, budget=`800` LOC/PR, strict_tdd=`true`, test_runner=`vitest`+`playwright` (`test.skip` per F9.x / Engram #1894), git_author=`Parkos Dev <dev@parkos.local>` |
| LOC forecast | ~1240 LOC nominal (design §LOC forecast). Strict-tdd historical inflation: F10.1 +1566, F10.2 +2037 (3rd straight overshoot expected) |
| Commit strategy | feature-branch-chain (per design AD; collapses design T1..T8 into 7 paired RED→GREEN commits per orchestrator plan) |

## Objective

Per `plan.md:2246-2264`, HU-F10.3 delivers the cajero end-of-day closure trilogy finale: as operator or supervisor, close all open sessions of the day with a single confirmation. The page surfaces a per-session resumen (`GET /caja/arqueo/resumen?uuid_sucursal=X&fecha=Y`) and submits `POST /caja/arqueo` with `tipo_arqueo='cierre_dia'` + `uuid_sesion=NULL` to atomically close every open session of the day (backend KD-ARQUEO-01 + KD-ARQUEO-03 invariants already shipped at F1.13). Strict-TDD paired RED→GREEN commits; route at `/caja/cierre-diario`; supervisor flow preserves own session (no F3.3 logout trifecta per AD-3); F8.x `useCierreDiario()` deprecated without deletion.

## Work units

Each WU = one commit on `feature/hu-f10-3-cierre-diario` (branched from `dev`). Test command confirmed against `apps/electron-sucursal/package.json` scripts (`lint`, `test`, `test:e2e`, `typecheck`).

| WU | Goal | Files touched | Focused test command | Runtime harness | Rollback boundary |
|----|------|---------------|---------------------|------------------|-------------------|
| C1 | RED scaffold hook + chain | NEW: `hooks/useArqueoResumenPorSesion.ts` (stub), NEW: `pages/cierreDiarioChain.ts` (stub), NEW: `hooks/__tests__/useArqueoResumenPorSesion.test.ts` (3 RED scenarios), NEW: `pages/__tests__/cierreDiarioChain.test.ts` (3 RED scenarios) | `pnpm vitest run src/features/caja/hooks/__tests__/useArqueoResumenPorSesion.test.ts src/features/caja/pages/__tests__/cierreDiarioChain.test.ts` | N/A (tests RED — no runtime feature yet) | Delete stub + test files; hook + chain remain uncreated |
| C2 | GREEN hook + chain | NEW: `hooks/useArqueoResumenPorSesion.ts` (~80 LOC), NEW: `pages/cierreDiarioChain.ts` (~150 LOC), MODIFY: `hooks/useArqueo.ts` (re-export `useArqueoResumenPorSesion` for tree-shaking, ~5 LOC) | `pnpm vitest run src/features/caja/hooks/__tests__/useArqueoResumenPorSesion.test.ts src/features/caja/pages/__tests__/cierreDiarioChain.test.ts` | N/A (helper is import-pure; runtime exercised in C4 page tests) | Delete hook + chain files; revert re-export in `useArqueo.ts` |
| C3 | RED form + page | NEW: `components/__tests__/CierreDiarioForm.test.tsx` (2 RED scenarios), NEW: `pages/__tests__/CierreDiario.test.tsx` (5 RED scenarios) | `pnpm vitest run src/features/caja/components/__tests__/CierreDiarioForm.test.tsx src/features/caja/pages/__tests__/CierreDiario.test.tsx` | N/A (tests RED — page + form not yet implemented) | Delete test files; no production code to revert |
| C4 | GREEN form + page | NEW: `components/CierreDiarioForm.tsx` (~110 LOC), NEW: `pages/CierreDiario.tsx` (~140 LOC) | `pnpm vitest run src/features/caja/components/__tests__/CierreDiarioForm.test.tsx src/features/caja/pages/__tests__/CierreDiario.test.tsx` | Detached Vite dev server (per AGENTS.md `app:dev:renderer`; 15s boot verification via `Test-NetConnection -Port 5173`) | Delete `CierreDiario.tsx` + `CierreDiarioForm.tsx`; F8.x `CierreDiarioDialog.tsx` untouched (independent path) |
| C5 | Deprecation log | MODIFY: `hooks/useArqueo.ts` (`@deprecated` JSDoc + dev-mode `console.warn` + once-per-page-load guard, ~15 LOC delta), NEW: `hooks/__tests__/useCierreDiario.deprecation.test.ts` (~80 LOC), NEW: `openspec/changes/fase-10-3-cierre-diario/specs/deprecation-log.md` (~30 LOC) | `pnpm vitest run src/features/caja/hooks/__tests__/useCierreDiario.deprecation.test.ts` | N/A (JSDoc + console.warn observable only in dev — production tree-shake verified via mock of `import.meta.env.DEV`) | Revert JSDoc + console.warn in `useArqueo.ts`; delete deprecation-log.md + test file |
| C6 | Route + i18n + sidebar | MODIFY: `renderer/App.tsx` (route registration at lines 70-76 per design, ~6 LOC), MODIFY: `renderer/i18n/locales/caja.json` (12 `cierreDiario.*` keys, ~12 LOC), MODIFY: `renderer/Dashboard.tsx` (sidebar anchor link to `/caja/cierre-diario`, ~6 LOC) | `pnpm tsc -p tsconfig.json --noEmit` + `pnpm lint` | Detached Vite dev server + navigate to `/caja/cierre-diario` (15s smoke); i18n key fallback check | Revert App.tsx + caja.json + Dashboard.tsx edits; page remains reachable only via direct URL |
| C7 | e2e + apply-progress | MODIFY: `e2e/arqueo.spec.ts` (extend F10.1 file with 4 `test.skip` scenarios + 1 axe-core scenario per REQ-OPS-169, ~150 LOC delta), NEW: `openspec/changes/fase-10-3-cierre-diario/apply-progress.md` (post-apply state with final SHAs per work unit) | `pnpm playwright test e2e/arqueo.spec.ts e2e/cerrar-turno.spec.ts e2e/arqueo.spec.ts` (NOT-FAIL per F9.x precedent — `test.skip` per scenario) | Detached Vite dev server (per AGENTS.md) + Playwright runs in deferred CI matrix | Revert e2e file additions; apply-progress.md is documentation-only |

## Phase 1: Foundation — hook + chain helpers (strict-TDD paired)

- [ ] 1.1 (C1 RED) Author 3 RED scenarios in `hooks/__tests__/useArqueoResumenPorSesion.test.ts`: per-session 3-row render, `cierre_dia` already-closed disables Confirmar, 401 triggers `useAuthStore.clear()` + `parkos:auth:cleared`. Stub `useArqueoResumenPorSesion.ts` exporting unimpl function so tests import cleanly.
- [ ] 1.2 (C1 RED) Author 3 RED scenarios in `pages/__tests__/cierreDiarioChain.test.ts`: happy 2-step sequencer (POST + bridge.imprimir once), bridge failure non-fatal, `400 cierre_dia_no_acepta_uuid_sesion` surfaces input drift. Stub `cierreDiarioChain.ts` exporting unimpl function.
- [ ] 1.3 (C1 RED commit) Conventional commit `test(caja): RED scaffold useArqueoResumenPorSesion + cierreDiarioChain` per `work-unit-commits` skill. Tests RED — no production code yet.
- [ ] 1.4 (C2 GREEN) Implement `useArqueoResumenPorSesion.ts` — SWR hook + Zod schema mirroring `ArqueoResumenRead` field-for-field with `.strict()` per REQ-OPS-165, `parkosFetch` Bearer+401-retry+5xx-backoff, SWR cache key `/caja/arqueo/resumen?uuid_sucursal=...&fecha=...`, key-gate null on missing inputs or `fecha > today` (DA-F10.3-3 efficiency guard), 401 → `useAuthStore.clear()` + `parkos:auth:cleared`. Export `ArqueoResumenPorSesion` type alias.
- [ ] 1.5 (C2 GREEN) Implement `cierreDiarioChain.ts` — `runCierreDiarioChain(args)` with discriminated `CierreDiarioChainResult` envelope (`'success' | 'arqueo_fallido' | 'red_arqueo' | 'ya_cerrado' | 'permiso_insuficiente'`), `ArqueoSubmitFn` type with `uuid_sesion: null` literal type (corrigendum for buggy legacy `useCierreDiario`), `CierreDiarioBridge` interface (`imprimir(kind, payload) => Promise<unknown>`), executes POST first, then bridge.imprimir with `auditoria_codigo: 'cierre_dia'` (failure logged + non-fatal per DA-F10.3-6). NO retry loop. NO client-side DELETE.
- [ ] 1.6 (C2 GREEN) MODIFY `hooks/useArqueo.ts` to add re-export `export { useArqueoResumenPorSesion } from './useArqueoResumenPorSesion';` for tree-shaking convenience (~5 LOC). NO mutation of legacy `useArqueoResumen` aggregate Zod schema (regression guard for F10.1/F8.x callers per NEW-DA-F10.3-9).
- [ ] 1.7 (C2 GREEN commit) Conventional commit `feat(caja): useArqueoResumenPorSesion hook + cierreDiarioChain sequencer` — `vitest run` GREEN for both new test files.

## Phase 2: Core UI — form + page orchestrator (strict-TDD paired)

- [ ] 2.1 (C3 RED) Author 2 RED scenarios in `components/__tests__/CierreDiarioForm.test.tsx`: `requiredMode='cierre_dia'` top-level Zod rejection on render, Confirmar disabled until `justificacion.length >= 3`. Stub component import.
- [ ] 2.2 (C3 RED) Author 5 RED scenarios in `pages/__tests__/CierreDiario.test.tsx`: happy multi-session (2 closed + 1 open), `Σ|diferencia|>0` requires justificacion, supervisor admin- variant, backend 5xx leaves S3 OPEN, `cierre_dia` already-closed banner replaces form. Stub page component.
- [ ] 2.3 (C3 RED commit) Conventional commit `test(caja): RED scaffold CierreDiarioForm + CierreDiario page`. Tests RED — components not yet implemented.
- [ ] 2.4 (C4 GREEN) Implement `components/CierreDiarioForm.tsx` (~110 LOC) — react-hook-form + Zod schema mirroring F10.2 `arqueoSchemaStrict` (top-level `z.string().trim().min(3, 'justificacion_requerida')` per REQ-OPS-158), shadcn `<Form>` primitives with `aria-invalid` + `aria-describedby` + `<FormMessage role="alert">` for WCAG 2.1 AA, aggregate-justification rule (Confirmar disabled when `Σ|diferencia|>0` AND `justificacion.length < 3`), i18n `cierreDiario.justificacionRequerida`.
- [ ] 2.5 (C4 GREEN) Implement `pages/CierreDiario.tsx` (~140 LOC) — orchestrator: fetch resumen via `useArqueoResumenPorSesion` → render `<ResumenTablaSesiones>` (per-session table with `Σ` footer + badge for `cerrado`/`abierta`) + `<CierreDiarioForm requiredMode="cierre_dia" totals={data.Σ}>` → on submit call `runCierreDiarioChain` → on `{ kind: 'success' }` navigate `/` (NOT `/login?closed=true`) with `<Alert data-testid="cierre-diario-success">`. NO `useSesionActiva().cerrarSesion` (AD-3). NO `useAuthStore.clear()` (AD-3). Date picker `<Input type="date" max={todayISO()} />` per AD-6.
- [ ] 2.6 (C4 GREEN commit) Conventional commit `feat(caja): CierreDiarioForm + CierreDiario page orchestrator` — `vitest run` GREEN for both new test files.

## Phase 3: Cleanup — deprecation log

- [ ] 3.1 (C5) MODIFY `hooks/useArqueo.ts:100-118` `useCierreDiario` — add `@deprecated` JSDoc tag with literal migration text "use the `useArqueo().submit({ uuid_sesion: null, tipo_arqueo: 'cierre_dia', ... })` path via `runCierreDiarioChain` from `pages/cierreDiarioChain.ts` (REQ-OPS-166)...". Add dev-mode `console.warn(...)` guard with `if (import.meta.env.DEV)` (Vite dead-code-eliminates in prod per REQ-OPS-168 scenario 2). Function body bit-identical (no behavior change). Once-per-page-load flag to prevent log spam.
- [ ] 3.2 (C5) Author 2 RED-then-GREEN scenarios in `hooks/__tests__/useCierreDiario.deprecation.test.ts`: dev-mode `console.warn` fires on `ejecutar(...)` call; production build tree-shakes warn guard (mock `import.meta.env.DEV = false`).
- [ ] 3.3 (C5) NEW `openspec/changes/fase-10-3-cierre-diario/specs/deprecation-log.md` — timeline: "useCierreDiario deprecated 2026-09-21 in HU-F10.3 PR; removal target: F11.x or later Fase 11 housekeeping. F8.x `CierreDiarioDialog.tsx:91` consumer must migrate before removal." per REQ-OPS-168.
- [ ] 3.4 (C5 commit) Conventional commit `chore(caja): deprecate useCierreDiario (no behavior change)` + deprecation-log.md.

## Phase 4: Wiring — route + i18n + sidebar

- [ ] 4.1 (C6) Verify current `renderer/App.tsx` lines 70-76 (per design). MODIFY to register `<Route path="/caja/cierre-diario" element={<ProtectedRoute><CierreDiario /></ProtectedRoute>} />`. Read file first per Edit precondition.
- [ ] 4.2 (C6) MODIFY `renderer/i18n/locales/caja.json` — append 12 `cierreDiario.*` keys: `title`, `fechaLabel`, `fechaFuturoRechazado`, `alreadyClosed`, `confirmar`, `cancelar`, `justificacionRequerida`, `errorCierreFallido`, `errorRedArqueo`, `errorCierreDiaNoAceptaSesion`, `errorPermisoInsuficiente`, `multiBranchOperatorPending`.
- [ ] 4.3 (C6) MODIFY `renderer/Dashboard.tsx` — add sidebar anchor link to `/caja/cierre-diario` with i18n `cierreDiario.title` label. Read file first per Edit precondition.
- [ ] 4.4 (C6) MODIFY `pending-fase-10.md` — add ABBC-F10.3-BE-1 (`perm_arqueo_cerrar_cualquiera` JWT issuer forward reference per REQ-OPS-167) + ABBC-F10.3-FE-1 (`useArqueoResumen` aggregate Zod reconciliation per NEW-DA-F10.3-9). Preserve existing ABBC-F10.2-BE-1 entry verbatim.
- [ ] 4.5 (C6 commit) Conventional commit `feat(caja): route /caja/cierre-diario + i18n + sidebar` + `chore(sdd): pending-fase-10 forward refs`. Run `pnpm tsc -p tsconfig.json --noEmit` + `pnpm lint` — must pass clean.

## Phase 5: Testing — e2e + apply-progress

- [ ] 5.1 (C7) MODIFY `e2e/arqueo.spec.ts` (extend F10.1 file per F10.2 precedent, NOT new file) — add 4 `test.skip` scenarios per REQ-OPS-169: (a) multi-session happy path with 3 sesiones (S1 closed + S2 closed + S3 open), (b) `Σ|diferencia|>0` requires justificacion, (c) supervisor admin- JWT variant, (d) fecha future boundary rejection. Reuse F10.1 fixtures (`VALID_ARQUEO_PAYLOAD`, `ARQUEO_RESUMEN_FIXTURE`); add `ARQUEO_RESUMEN_POR_SESION_FIXTURE` with 3 sesiones.
- [ ] 5.2 (C7) Append 1 axe-core scenario at end of `e2e/arqueo.spec.ts` — WCAG 2.1 AA on `/caja/cierre-diario` (page + form + table). `@axe-core/playwright` per package.json devDep.
- [ ] 5.3 (C7) NEW `openspec/changes/fase-10-3-cierre-diario/apply-progress.md` — populate AFTER apply: final commit SHAs per work unit C1..C7, test result summary, drift-anchor resolution status, deviations from this tasks.md (with rationale).
- [ ] 5.4 (C7 commit) Conventional commit `test(e2e): cierre-diario multi-session scenarios (test.skip per F9.x)` + apply-progress.md (documentation-only post-apply).

## Drift-anchor verification checklist

| Drift anchor | Status | Resolved by commit |
|--------------|--------|---------------------|
| DA-F10.3-1 (multi-session atomicity) | RESOLVED — KD-ARQUEO-01 single-commit invariant at `caja_arqueo.py:311`; REQ-OPS-164 scenario 3 codifies all-or-none | C2 (chain helper) + C4 (page 5xx leaves S3 OPEN scenario) |
| DA-F10.3-2 (supervisor closes OTHER operator's session) | RESOLVED — admin- JWT issuer gating; `requires_issuer("operador-", "admin-")` at `caja_arqueo.py:61`; ABBC-F10.3-BE-1 forward ref | C4 (supervisor admin- variant scenario) + C6 (ABBC-F10.3-BE-1 in pending-fase-10.md) |
| DA-F10.3-3 (fecha boundary) | RESOLVED — HTML5 `max={todayISO()}` + hook key-gate null on future + past read-only via page render | C2 (hook key-gate) + C4 (page date picker + futuro banner) |
| DA-F10.3-4 (per-session resumen shape) | RESOLVED — backend `ArqueoResumenRead` already returns per-session array at `schemas/caja.py:316-346`; new sibling hook + corrected `.strict()` Zod | C2 (new sibling hook) + C7 (e2e fixture `ARQUEO_RESUMEN_POR_SESION_FIXTURE`) |
| DA-F10.3-5 (aggregate-justification rule) | RESOLVED — `Σ|diferencia|>0` requires `justificacion.min(3)`; F10.2 `arqueoSchemaStrict` strict-mode Zod variant | C4 (form schema composes F10.2 strict-mode) + C3 (form RED scenario 2) |
| DA-F10.3-6 (escpos `auditoria_codigo='cierre_dia'`) | RESOLVED — F10.2 C5 regex extension already accepts `'cierre_dia'`; no escpos change | C2 (chain helper passes `auditoria_codigo: 'cierre_dia'`) |
| DA-F10.3-7 (`useCierreDiario()` bug collision) | RESOLVED — `@deprecated` JSDoc + dev-mode `console.warn`; no behavior change; no F8.x regression | C5 (deprecation marker + test + deprecation-log.md) |
| DA-F10.3-8 (strict-TDD coverage budget) | RESOLVED — orchestrator routes via `delivery_strategy=ask-on-risk`; ~1240 LOC forecast; 3rd straight overshoot expected | All commits (orchestrator decision at apply time) |
| NEW-DA-F10.3-9 (F10.1 `useArqueoResumen` aggregate Zod drift) | RESOLVED (deferred) — sibling hook + `.strict()` future-proofs; legacy NOT mutated; ABBC-F10.3-FE-1 forward ref | C2 (new sibling hook without legacy mutation) + C6 (ABBC-F10.3-FE-1 in pending-fase-10.md) |

## Test commands summary

Run in order from `apps/electron-sucursal/` workspace (pnpm per AGENTS.md workspace convention):

1. **Lint** — `cd apps/electron-sucursal && pnpm lint`
2. **Typecheck** — `cd apps/electron-sucursal && pnpm tsc -p tsconfig.json --noEmit`
3. **Focused unit tests** — `cd apps/electron-sucursal && pnpm vitest run src/features/caja/pages/__tests__/cierreDiarioChain.test.ts src/features/caja/hooks/__tests__/useArqueoResumenPorSesion.test.ts src/features/caja/pages/__tests__/CierreDiario.test.tsx`
4. **Full FE regression** — `cd apps/electron-sucursal && pnpm vitest run`
5. **E2E (NOT-FAIL per F9.x precedent — all scenarios `test.skip`)** — `cd apps/electron-sucursal && pnpm playwright test e2e/cierre-diario.spec.ts e2e/cerrar-turno.spec.ts e2e/arqueo.spec.ts`

All commands confirmed against `apps/electron-sucursal/package.json` scripts (`lint`, `test`, `test:e2e`, `typecheck`).

## Plain-text guard lines

```
Decision: single-pr (orchestrator will surface size:exception at apply time per ask-on-risk)
Chained PRs: No (or Yes with explanation if apply warrants)
Chain strategy: feature-branch-chain (per design AD; collapses design T1..T8 into 7 paired RED→GREEN commits)
Delivery strategy: ask-on-risk
Size exception: NOT pre-seeked (3rd straight strict_tdd overshoot expected → orchestrator will surface at apply time)
Review budget risk: High (forecast 1240 vs 800 hard budget — 3rd overshoot)
Review budget hard limit: 800 lines
Forecast ~1240 LOC actual (F10.1 1566, F10.2 2037 precedent for strict_tdd)
```

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1240 |
| 400-line budget risk | High |
| 800-line budget risk | High |
| Chained PRs recommended | Yes (feature-branch-chain per design AD; F10.2 archive precedent) |
| Suggested split | C1 (RED scaffold ~280) → C2 (GREEN hook+chain ~310) → C3 (RED form+page ~330) → C4 (GREEN form+page ~390) → C5 (deprecation ~95) → C6 (route+i18n+sidebar ~135) → C7 (e2e+apply-progress ~150) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |
| Size exception needed | Likely (3rd strict_tdd overshoot; precedent set by F10.1 + F10.2 ratification per Engram #1894, #1904) |
| Decision needed before apply | Yes |

## Open decisions

**The orchestrator must surface the size:exception decision (or chained-PR alternative) BEFORE apply.**

Historical pattern (3rd straight strict_tdd overshoot expected per DA-F10.3-8):

| HU | Nominal forecast | Actual delta vs `dev` | Outcome |
|---|---|---|---|
| F10.1 (Arqueo Parcial) | ~200 LOC | +1566 net (per Engram #1894) | **size:exception RATIFIED** |
| F10.2 (Cierre de turno) | ~340 LOC | +2037 net (per Engram #1904) | **size:exception RATIFIED** (3rd in repo) |
| **F10.3 (Cierre diario)** | **~1240 LOC nominal** | **forecast HIGH (per design + this tasks.md)** | **decision pending** |

The 800-line hard budget per `config.yaml` `rules.tasks` is not the operational budget; the operational pattern is `size:exception` after the fact (per F10.1 + F10.2 ratified precedents). Orchestrator's `delivery_strategy=ask-on-risk` will route this at apply time. **Do NOT pre-seek exception here per the explicit design §Risk acknowledgements row DA-F10.3-8 ("the spec does NOT pre-seek exception").**

Three plausible apply-time paths:

1. **`size:exception` ratified** (most likely per precedent): single PR to `dev`, similar to F10.1 + F10.2. Implementation cost: lowest; review cost: high (one ~1500-2500 LOC PR).
2. **Chained PRs (feature-branch-chain)** per design AD: 2-3 PRs, each ≤800 LOC, base = `feature/hu-f10-3-cierre-diario` tracker, child PRs target previous PR branches. Implementation cost: medium; review cost: medium.
3. **Trim scope**: drop C7 (e2e, already `test.skip` per F9.x precedent — zero functional impact) + defer C5 (deprecation, non-functional) + defer C6 sidebar anchor. Implementation cost: highest (re-scopes HU); review cost: lowest.

Recommended path: **chained PRs** (option 2) per design AD. Alternative: **size:exception** (option 1) per F10.1 + F10.2 precedent.

Open decisions carried from design: **none** (D1..D6 ratified inputs; sequencer enumerated exhaustively; spec REQ-OPS-163..169 codifies all 7 requirements).

## Risk acknowledgements

Copied verbatim from `design.md` §Risk acknowledgements:

| Risk id | Status | Residual |
|---|---|---|
| DA-F10.3-1 — Multi-session atomicity | RESOLVED | REQ-OPS-164 scenario `page-3-5xx-s3-stays-open` codifies the all-or-none contract. KD-ARQUEO-01 backend invariant (`caja_arqueo.py:311` single-commit) + KD-ARQUEO-03 in-tx `cerrar_sesiones_del_dia_bulk` (`caja_arqueo.py:266-272`) are the long-term backstop. Unit + e2e coverage is the regression guard. |
| DA-F10.3-2 — Supervisor closes OTHER operator's session | RESOLVED (Q2 closed via repo inspection) | AD-3 + REQ-OPS-167 gates FE on admin- issuer; backend `requires_issuer("operador-", "admin-")` at `caja_arqueo.py:61` is the long-term backstop. ABBC-F10.3-BE-1 forward reference for future `perm_arqueo_cerrar_cualquiera` JWT issuer permission (lands in F12.x). |
| DA-F10.3-3 — Fecha boundary | RESOLVED | AD-6 + REQ-OPS-164 + REQ-OPS-169 scenario `e2e-4-fecha-futuro-rejected` lock the three states (today writeable, past read-only, future rejected). HTML5 `max={todayISO()}` is browser-level enforcement; hook key-gate `null` for future dates is the efficiency guard. |
| DA-F10.3-4 — Per-session resumen shape (Q1) | RESOLVED | AD-1 + REQ-OPS-163 + REQ-OPS-165 codify the per-session shape from `ArqueoResumenRead`. NEW-DA-F10.3-9 (legacy aggregate Zod drift) is forwarded to ABBC-F10.3-FE-1 follow-up PR. |
| DA-F10.3-5 — Aggregate-justification rule | RESOLVED | AD-4 + REQ-OPS-164 scenario `page-2-diff-gt-0-justificacion` + F10.2 REQ-OPS-158 `requiredMode='cierre_dia'` strict-mode Zod variant lock the contract. The `<CierreDiarioForm>` composes the same Zod branch F10.2 shipped. |
| DA-F10.3-6 — ESC/POS `auditoria_codigo='cierre_dia'` discriminator | RESOLVED (no code change) | AD-2 + REQ-OPS-166 scenario `chain-1-happy-post-imprimir`. `escposBuilder.build('arqueo', payload)` at `lib/print/escposBuilder.ts:498` already emits `Codigo: ${payload.auditoria_codigo}`; `cierre_dia` flows through unchanged. 12-line body shape identical to F10.1 + F10.2. |
| DA-F10.3-7 — `useCierreDiario()` deprecation (Q3) | RESOLVED via repo inspection | AD-5 + REQ-OPS-168 codify the `@deprecated` JSDoc + dev-mode `console.warn`. Helper is NOT deleted in F10.3 scope (F8.x `CierreDiarioDialog.tsx:91` caller regression guard). Deletion target: F11.x or later Fase 11 housekeeping. Timeline in `specs/deprecation-log.md`. |
| DA-F10.3-8 — Strict-TDD coverage budget | RESOLVED (orchestrator routes) | 7 commits per orchestrator plan (collapses design T1..T8 into paired RED→GREEN per `work-unit-commits` skill). Forecast ~1240 LOC nominal (above 800-LOC per-PR budget; feature-branch-chain per F10.2 precedent). The orchestrator's `delivery_strategy=ask-on-risk` ratifies at apply time. |
| NEW DA-F10.3-9 — F10.1 `useArqueoResumen` Zod drift | RESOLVED (deferred) | AD-1 introduces the new sibling hook `useArqueoResumenPorSesion` with corrected `.strict()` schema (REQ-OPS-163 + REQ-OPS-165). Legacy aggregate schema is NOT modified (regression guard for F10.1 `ArqueoParcial.tsx` + F8.x `CierreDiarioDialog.tsx:91`). ABBC-F10.3-FE-1 in `pending-fase-10.md`. |
| NEW F8.x `CierreDiarioDialog.tsx:91` regression risk | RESOLVED | Per spec §Risk acknowledgements row 5: the dialog calls `useArqueo().submit(...)` directly (NOT `useCierreDiario().ejecutar(...)`), so the dialog's bug surface is independent of AD-5 deprecation. Dialog continues working with the existing bug; future fix in a separate housekeeping PR. |
| NEW `<CierreDiario />` route added without supervisor RBAC UI | RESOLVED (out of scope) | Per spec §Out-of-Scope: "Supervisor RBAC UI changes (route guards rely on existing `ProtectedRoute` — backend JWT scope is the gating factor)". The page itself gates UI on `useAuthStore` admin- issuer (AD-3 + REQ-OPS-167). Backend `requires_issuer("operador-", "admin-")` is the long-term backstop. |
