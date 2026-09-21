# Tasks: HU-F10.1 Arqueo Parcial (frontend delta)

## Header

| Field | Value |
|-------|-------|
| Change | `fase-10-1-arqueo-parcial` |
| Phase | `sdd-tasks` |
| Inputs read | `openspec/changes/fase-10-1-arqueo-parcial/proposal.md` (Engram #1888), `openspec/changes/fase-10-1-arqueo-parcial/specs/spec.md` (Engram #1889), `openspec/changes/fase-10-1-arqueo-parcial/design.md` (Engram #1890), `plan.md` lines 2140-2181, `openspec/specs/operations/spec.md` REQ-OPS-091..097 (F1.13 backend contract), `apps/electron-sucursal/{package.json,vitest.config.ts,playwright.config.ts}` (confirmed test runner and config), `apps/electron-sucursal/src/features/caja/{hooks/useArqueo.ts,components/ArqueoSheet.tsx,pages/Dashboard.tsx}` (verified actual paths), `apps/electron-sucursal/src/renderer/App.tsx`, `apps/electron-sucursal/src/lib/print/{escposTemplates.ts,escposBuilder.ts}` |
| Status | ready-for-apply |
| Preflight (cached) | pace=`auto`, artifact=`hybrid`, delivery=`ask-on-risk`, chain=`gitflow`, review_budget_lines=`800`, strict_tdd=`true`, test_runner=`vitest` (unit) + `playwright` (e2e), git_author_override=`Parkos Dev <dev@parkos.local>` |
| Branch | `feature/hu-f10-1-arqueo-parcial` (target: `dev` via merge-to-dev at session close per AGENTS.md §Gitflow Estricto regla 8) |
| LOC forecast | ~306 LOC actual (under 800 budget; above 260 soft target — see Risks §R3) |

## Objective

From `plan.md` line 2142: "Como operador o supervisor, quiero contar la caja en cualquier momento del turno sin cerrarlo, y que el sistema me diga si hay diferencia." Surface CU-10 BR1 via routed page `/caja/arqueo-parcial` wrapping the existing `<ArqueoSheet>` drawer; reconcile renderer payload naming with backend REQ-OPS-091; emit a printable `'arqueo'` ESC/POS tiquete via `escposBuilder.build(...)`; keep `expectedValue` read from the server (single source of truth — `factura_pagos` immutability honored).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~306 |
| 400-line budget risk | Low |
| 800-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR `feature/hu-f10-1-arqueo-parcial` -> `dev` |
| Delivery strategy | ask-on-risk (risk resolved: Low forecast -> proceed) |
| Chain strategy | n/a |
| Decision needed before apply | No |
| Size exception needed | No |

Decision: single-pr
Chained PRs: No
Chain strategy: n/a
Delivery strategy: ask-on-risk
Size exception: No
Review budget risk: Low
Review budget hard limit: 800 lines
Forecast ~306 LOC actual

### Plain-text guard lines (CI auto-grep contract)

```
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main|feature-branch-chain|size-exception|pending
400-line budget risk: Low
```

## Work units

Strict-TDD commit boundaries per `work-unit-commits` skill. Each work unit (WU) is one logical behavior unit; commits ship RED + GREEN where the test runs against NEW code (single commit), or split RED/GREEN when the test runs against STUB code that is later replaced. Order follows dependency: hook+schema refinement -> page wrapper -> ESC/POS dispatcher -> e2e wiring -> docs/apply-progress.

### WU-T1 — `useArqueo` rename + Zod refinement (HOOK layer)

| Field | Value |
|---|---|
| WU name | WU-T1 RED scaffold `useArqueo.test.ts` for renamed submit payload + arqueoSchema refinement |
| Files touched | NEW `apps/electron-sucursal/src/features/caja/hooks/__tests__/useArqueo.test.ts` (RED); MODIFY `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts` (payload keys rename; ~11 LOC delta per design AD-2); MODIFY `apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx` (~12 LOC delta: Zod schema rename + refinement + `expected` prop per AD-4) |
| Focused test command | `cd apps/electron-sucursal && pnpm vitest run src/features/caja/hooks/__tests__/useArqueo.test.ts --reporter=verbose` |
| Runtime harness | N/A (pure unit test on hook + Zod schema); renderer integration covered by WU-T4 e2e |
| Rollback boundary | Revert this WU only: removes renamed payload keys and the Zod refinement from `<ArqueoSheet>`; `<ArqueoSheet>` falls back to legacy `efectivo_contado_cop`/`observaciones`. `<ArqueoSheet>` is still mountable by WU-T4's page (separate concern). No migration data loss. |
| Coverage goal | lines >=90, branches >=85 (mirrors `useRegistrarPago.ts` precedent; add entry to `vitest.config.ts` `coverage.thresholds`) |

**RED commit** (`test: add RED tests for useArqueo submit payload shape + Zod refinement`):
- Adds `useArqueo.test.ts` with 4 cases: `rename-keys-1` (renamed payload shape `valor_efectivo_reportado`/`valor_datafono_reportado`/`justificacion`), `rename-keys-2` (regression: legacy keys NOT accepted), `rename-keys-3` (Zod `arqueoSchema` refinement: `justificacion` optional when `diferencia === 0`), `refinement-1` (Zod `arqueoSchema` refinement: `justificacion.min(3)` required when `|diferencia| > 0`), `contract-1` (no DELETE call in the mutation), `expected-source-1` (resumen hook unchanged; consumes renamed GET shape).
- `pnpm vitest run src/features/caja/hooks/__tests__/useArqueo.test.ts` MUST FAIL (RED).
- Commit message body MUST list the 4 case IDs verbatim.

**GREEN commit** (`refactor(caja): align useArqueo payload to REQ-OPS-091 + Zod refinement on diferencia`):
- Rename `efectivo_contado_cop` -> `valor_efectivo_reportado`, `datafono_contado_cop` -> `valor_datafono_reportado`, `observaciones` -> `justificacion` in `useArqueo.ts::submit` argument type and forwarded body.
- Update `arqueoSchema` in `ArqueoSheet.tsx`: rename keys + add `.superRefine((data, ctx) => { if (Math.abs(diferencia_cop) > 0 && (!data.justificacion || data.justificacion.trim().length < 3)) ctx.addIssue(...) })`.
- Update `<ArqueoSheet>` form field `name=` attributes and `data-testid` to `arqueo-efectivo`, `arqueo-datafono`, `arqueo-justificacion`.
- `pnpm vitest run src/features/caja/hooks/__tests__/useArqueo.test.ts` MUST PASS (GREEN).
- Plus the existing `<ArqueoSheet>` form (without page wrapper) keeps working because WU-T4 has not yet run; no page is required for the hook unit test.

### WU-T2 — ESC/POS `'arqueo'` dispatcher + 12-field byte fixture

| Field | Value |
|---|---|
| WU name | WU-T2 RED+GREEN `arqueoFixture.test.ts` + escposTemplates/escposBuilder `'arqueo'` extension |
| Files touched | NEW `apps/electron-sucursal/src/lib/print/__tests__/arqueoFixture.test.ts` (~40 LOC); MODIFY `apps/electron-sucursal/src/lib/print/escposTemplates.ts` (~30 LOC delta: `'arqueo'` in `TiqueteTipo` union + `TIQUETE_TIPOS` + `arqueoPayloadSchema` + `payloadSchemaByTipo` entry); MODIFY `apps/electron-sucursal/src/lib/print/escposBuilder.ts` (~12 LOC delta: `buildArqueoBody()` + dispatch `case 'arqueo'` + `validatePayload` case + import) |
| Focused test command | `cd apps/electron-sucursal && pnpm vitest run src/lib/print/__tests__/arqueoFixture.test.ts --reporter=verbose` |
| Runtime harness | N/A (pure byte composition test against golden literal substrings per REQ-OPS-155 scenario 2) |
| Rollback boundary | Revert this WU only: removes `'arqueo'` from `TiqueteTipo` (the dispatcher would fall back to `exhaustive` TS error, which is the desired blast radius); WU-T1's renamed payload still works because submit does NOT depend on print. |
| Coverage goal | lines >=95, branches >=90 (mirrors `escposTemplates.ts` precedent; add entry to `vitest.config.ts` `coverage.thresholds`) |

**Single RED+GREEN commit** (`feat(print): add 'arqueo' ESC/POS dispatcher with 12-field body + byte fixture`):
- Adds `arqueoFixture.test.ts` with 3 cases: `dispatch-1` (12-field body byte fixture — every literal substring from REQ-OPS-155 scenario 2), `dispatch-2` (Zod parse rejects missing `auditoria_codigo` or out-of-range `fecha`), `dispatch-3` (envelope `0x1B 0x40` init and `0x1D 0x56 0x00 0x0A` cutPartial+LF).
- Extends `escposTemplates.ts`: union member, schema, `payloadSchemaByTipo`, `TIQUETE_TIPOS`.
- Extends `escposBuilder.ts`: `buildArqueoBody()`, `buildArqueoBuffer()`, dispatch case, `validatePayload` case.
- Test runs against NEW code (commit ships both); `pnpm vitest run src/lib/print/__tests__/arqueoFixture.test.ts` MUST PASS in CI.

### WU-T3 — Routed `<ArqueoParcial>` page + Dashboard anchor + i18n

| Field | Value |
|---|---|
| WU name | WU-T3 RED+GREEN `<ArqueoParcial>` page + `App.tsx` route + Dashboard anchor + i18n keys |
| Files touched | NEW `apps/electron-sucursal/src/features/caja/pages/ArqueoParcial.tsx` (~30 LOC per design AD-1); MODIFY `apps/electron-sucursal/src/renderer/App.tsx` (~5 LOC: `<Route path="/caja/arqueo-parcial">` BEFORE the `*` catch-all); MODIFY `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` (~3 LOC: sidebar anchor `navigate('/caja/arqueo-parcial')` in place of `openDrawer('arqueo', 'sidebar-arqueo')`); MODIFY `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (add `arqueoParcial.diferencia_critica`, `arqueoParcial.diferencia_informativa_pct`, `arqueoParcial.justificacion_requerida` per design AD-5) |
| Focused test command | `cd apps/electron-sucursal && pnpm vitest run src/features/caja/pages/__tests__/ArqueoParcial.test.tsx --reporter=verbose` (test added inline) |
| Runtime harness | WU-T4 e2e (Playwright boots the Electron app, navigates to `/caja/arqueo-parcial`, asserts drawer mounts); WU-T3 only adds the route entry point. |
| Rollback boundary | Revert this WU only: removes the routed page and route entry; `<ArqueoSheet>` is still imported by WU-T1's `ArqueoSheet.tsx` so it remains usable from `<Dashboard>` via legacy `openDrawer(...)` path. No data loss. |
| Coverage goal | lines >=80, branches >=75 (mirrors `Venta.tsx` page precedent; add entry to `vitest.config.ts` `coverage.thresholds`) |

**Single RED+GREEN commit** (`feat(caja): routed /caja/arqueo-parcial page wrapping ArqueoSheet + dashboard anchor`):
- Adds `ArqueoParcial.test.tsx` (3 cases: route mounts `<ArqueoSheet>`; live diferencia alert renders; field rename in submit body — per design §Test plan).
- Adds `ArqueoParcial.tsx` (calls `useArqueoResumen`, mounts `<ArqueoSheet expected={resumen} uuid_sesion={sesion.uuid} />`, falls back to F3.3 "open a turn first" message when no active session).
- Adds route entry in `App.tsx` BEFORE `*` catch-all.
- Swaps Dashboard sidebar anchor `openDrawer('arqueo', ...)` -> `navigate('/caja/arqueo-parcial')`.
- Adds 3 i18n keys.
- Test runs against NEW code (commit ships both); `pnpm vitest run src/features/caja/pages/__tests__/ArqueoParcial.test.tsx` MUST PASS in CI.

### WU-T4 — Playwright e2e `e2e/arqueo.spec.ts` (3 scenarios + axe-core)

| Field | Value |
|---|---|
| WU name | WU-T4 RED+GREEN `e2e/arqueo.spec.ts` (3 scenarios per REQ-OPS-156) |
| Files touched | NEW `apps/electron-sucursal/e2e/arqueo.spec.ts` (~80 LOC per design §Test plan) |
| Focused test command | `cd apps/electron-sucursal && pnpm playwright test e2e/arqueo.spec.ts --reporter=list` |
| Runtime harness | The Electron app boots via `_electron` per `playwright.config.ts`; the test mocks `GET /api/v1/caja/arqueo/resumen` and intercepts `POST /api/v1/caja/arqueo` via `page.route(...)`; `bridge.imprimir` stubbed via `window.__bridgeStub` per the F3.3 e2e precedent. |
| Rollback boundary | Revert this WU only: removes the e2e spec. WU-T1..T3 stay green. No data loss. |
| Coverage goal | N/A (e2e coverage is per-scenario pass/fail; lines not measured). axe-core WCAG 2.1 AA zero violations on `/caja/arqueo-parcial`. |

**Single RED+GREEN commit** (`test(e2e): add arqueo.spec.ts with 3 scenarios per REQ-OPS-156`):
- Scenario 1 (happy path `diferencia === 0`): open `/caja/arqueo-parcial` with `sesion_activa` mocked, type exact `valor_esperado_*`, click Confirmar, intercept `POST /api/v1/caja/arqueo` and assert body equals `{ uuid_sesion: "S", tipo_arqueo: "auditoria", valor_efectivo_reportado: 100000, valor_datafono_reportado: 0 }` (no legacy keys, no `justificacion`), assert `bridge.imprimir` called once with kind=`'arqueo'`, assert sheet closes (DOM has no `[data-testid=arqueo-sheet][data-state=open]`), assert axe-core zero violations on `/caja/arqueo-parcial`.
- Scenario 2 (warning + required justificacion): `diferencia = -3000` against `tolerancia_efectivo=1000`, assert `<Alert variant="warning">` renders with `caja.descuadre_warning` text + `formatCOP(valor_esperado)`/`formatCOP(valor_reportado)`/`formatCOP(diferencia_cop)`, assert submit button disabled while `justificacion` is empty, re-enabled after typing >=3 chars, POST body carries `justificacion` field.
- Scenario 3 (regression guard): intercept `POST /api/v1/caja/arqueo` and assert JSON keys do NOT contain `efectivo_contado_cop` / `datafono_contado_cop` / `observaciones`; assert `justificacion` is absent when `diferencia=0` (not sent as empty string).
- `pnpm playwright test e2e/arqueo.spec.ts` MUST PASS (3/3) in CI before merge.

### WU-T5 — `apply-progress.md` + i18n key alignment finalize (docs/compliance)

| Field | Value |
|---|---|
| WU name | WU-T5 `openspec/changes/fase-10-1-arqueo-parcial/apply-progress.md` + final i18n key review |
| Files touched | NEW `openspec/changes/fase-10-1-arqueo-parcial/apply-progress.md` (artifact-only, after git commits WU-T1..T4 land at apply time) |
| Focused test command | N/A (docs/compliance artifact) |
| Runtime harness | N/A |
| Rollback boundary | Revert this WU only: deletes `apply-progress.md`. WU-T1..T4 stay green. |
| Coverage goal | N/A |

**Single commit** (`docs(sdd): add apply-progress.md with final commit SHAs for fase-10-1-arqueo-parcial`):
- Records final commit SHAs after `git commit` actually executes at apply time.
- Includes drift-anchor resolution table (cross-references WU-T1..T4 commit hashes).
- Includes per-WU test command output snapshot (vitest + playwright exit codes).

## Commit plan (final order)

Strict-TDD: RED + GREEN per work unit where the test runs against NEW code (WU-T1 splits RED/GREEN because the RED test fails against STUB legacy keys before the rename lands; WU-T2/T3/T4/T5 ship RED+GREEN together because the test runs against the new code in the same commit).

| # | Type | Files | Conventional commit | Test command | Expected |
|---|------|-------|---------------------|--------------|----------|
| C1 | RED | NEW `useArqueo.test.ts` | `test(caja): add RED tests for useArqueo submit payload shape + Zod refinement` | `pnpm vitest run src/features/caja/hooks/__tests__/useArqueo.test.ts --reporter=verbose` | FAIL (RED) |
| C2 | GREEN | MODIFY `useArqueo.ts` + `ArqueoSheet.tsx` (rename + Zod refinement) | `refactor(caja): align useArqueo payload to REQ-OPS-091 + Zod refinement on diferencia` | `pnpm vitest run src/features/caja/hooks/__tests__/useArqueo.test.ts --reporter=verbose` | PASS (GREEN) |
| C3 | RED+GREEN | NEW `arqueoFixture.test.ts` + MODIFY `escposTemplates.ts` + `escposBuilder.ts` | `feat(print): add 'arqueo' ESC/POS dispatcher with 12-field body + byte fixture` | `pnpm vitest run src/lib/print/__tests__/arqueoFixture.test.ts --reporter=verbose` | PASS (GREEN) |
| C4 | RED+GREEN | NEW `ArqueoParcial.tsx` + NEW `ArqueoParcial.test.tsx` + MODIFY `App.tsx` + MODIFY `Dashboard.tsx` + MODIFY `caja.json` | `feat(caja): routed /caja/arqueo-parcial page wrapping ArqueoSheet + dashboard anchor` | `pnpm vitest run src/features/caja/pages/__tests__/ArqueoParcial.test.tsx --reporter=verbose` | PASS (GREEN) |
| C5 | RED+GREEN | NEW `e2e/arqueo.spec.ts` | `test(e2e): add arqueo.spec.ts with 3 scenarios per REQ-OPS-156` | `pnpm playwright test e2e/arqueo.spec.ts --reporter=list` | PASS (3/3 GREEN) |
| C6 | DOCS | NEW `apply-progress.md` | `docs(sdd): add apply-progress.md with final commit SHAs for fase-10-1-arqueo-parcial` | N/A | N/A |

## Drift-anchor verification checklist

Every drift anchor from `proposal.md` §Risks and `spec.md` §Drift reconciliation table resolved by a specific commit.

| # | Drift anchor | L | Status | Resolution commit | Where in spec |
|---|---|---|---|---|---|
| DA-1 | `useArqueo.submit` uses `efectivo_contado_cop`; REQ-OPS-091.Scenario1 uses `valor_efectivo_reportado` (silent 422 risk) | H | RESOLVED | **C1 (RED) + C2 (GREEN)** — rename in `useArqueo.ts` payload + Zod schema + e2e regression guard REQ-OPS-156 scenario 3 | REQ-OPS-153 |
| DA-2 | AC routed `/caja/arqueo-parcial`; current UX is Sheet drawer from Dashboard F4 | M | RESOLVED | **C4** — route WRAPS drawer (preserves F4 hotkey + sidebar anchor + `useDashboardDrawerStore` state) | REQ-OPS-152 |
| DA-3 | BR1 base configurable al momento del arqueo: `sesion.valor_inicial_efectivo` — vigente base or snapshot? | H | RESOLVED (documentation only — NO migration) | **NONE** — REQ-OPS-097 §3919 already reads `sesion.valor_inicial_efectivo` at GET time; this is the vigente base snapshot. No `configuracion_caja.base_efectivo_vigente` migration needed for F10.1. Confirmed by `spec.md` §Drift reconciliation table row 3: "tasks.md: NONE; apply: NONE". | REQ-OPS-097 |
| DA-4 | Justification asymmetry: AC optional in CU; UI refines required on `|diferencia|>0`; backend REQ-OPS-096 accepts `auditoria` without it | M | RESOLVED (documentation only — NO code change beyond C2's Zod refinement) | **C2** refines the UI Zod schema (REQ-OPS-154); backend permits per REQ-OPS-094 (no change). No divergence in success path. | REQ-OPS-154 |
| DA-5 | `'arqueo'` dispatcher key NOT yet in `escposTemplates` union (only `entrada`/`salida`/`recibo_pago`/`reimpresion`) | H | RESOLVED | **C3** — adds dispatcher entry + `arqueoPayloadSchema` + `buildArqueoBody()` + byte fixture | REQ-OPS-155 |
| DA-6 | `factura_pagos` immutability: `fn_factura_pagos_inmutable` trigger fires on any UPDATE | L | RESOLVED (documentation + test isolation only — NO code change beyond docstring in `useArqueoResumen`) | **C4** adds a docstring annotation in `useArqueoResumen` ("renderer MUST NOT compute `esperado` from local `factura_pagos` cache"); **C5** e2e uses `page.route()` mocks instead of mutating `prod.factura_pagos`. | REQ-OPS-154 + REQ-OPS-156 |
| DA-7 | Hash chain extension: every `arqueo` [A] extends `prod.log_transaccional` per `uuid_sucursal`. Out-of-order e2e could fork. | L | RESOLVED (no code change — relies on shipped verifier) | **C5** e2e is single-shot per scenario (no out-of-order writes); `job_sync_cloud.hash_chain_verifier_loop` (PR9b, Engram #1888 reference) is the safety net. | REQ-OPS-156 |

## Test commands summary

Every command `sdd-apply` will invoke, in order. All commands assume working directory `apps/electron-sucursal` unless otherwise noted.

### Pre-flight (before any commit)

```bash
# 1. Lint clean
cd apps/electron-sucursal && pnpm lint

# 2. Type-check clean
cd apps/electron-sucursal && pnpm typecheck

# 3. Full vitest coverage on touched modules (per vitest.config.ts thresholds; new entries required for F10.1)
cd apps/electron-sucursal && pnpm vitest run --coverage
```

### Per-commit verification

| Commit | Focused test command | Expected exit |
|--------|----------------------|---------------|
| C1 (RED) | `pnpm vitest run src/features/caja/hooks/__tests__/useArqueo.test.ts --reporter=verbose` | non-zero (RED) |
| C2 (GREEN) | `pnpm vitest run src/features/caja/hooks/__tests__/useArqueo.test.ts --reporter=verbose` | 0 |
| C3 | `pnpm vitest run src/lib/print/__tests__/arqueoFixture.test.ts --reporter=verbose` | 0 |
| C4 | `pnpm vitest run src/features/caja/pages/__tests__/ArqueoParcial.test.tsx --reporter=verbose` | 0 |
| C5 | `pnpm playwright test e2e/arqueo.spec.ts --reporter=list` | 0 (3/3) |
| C6 | N/A (docs) | N/A |

### Post-flight invariants (after C6, before merge to dev)

```bash
# 1. Lint: zero errors / zero max-warnings violations
cd apps/electron-sucursal && pnpm lint

# 2. Type-check: zero errors across workspace
cd apps/electron-sucursal && pnpm typecheck

# 3. Full vitest with coverage: threshold >=80% lines on touched modules
#    (per the per-file entries added in vitest.config.ts: useArqueo.ts >=90, ArqueoSheet.tsx >=85, ArqueoParcial.tsx >=80, escposTemplates.ts >=95, escposBuilder.ts >=85, arqueoFixture test >=95)
cd apps/electron-sucursal && pnpm vitest run --coverage

# 4. Playwright e2e on the new spec: all 3 scenarios green
cd apps/electron-sucursal && pnpm playwright test e2e/arqueo.spec.ts --reporter=list

# 5. axe-core WCAG 2.1 AA on the new page: zero violations
#    (the @a11y check is inline inside scenario 1 of e2e/arqueo.spec.ts via AxeBuilder; no separate --grep needed)
```

### Coverage thresholds to add to `apps/electron-sucursal/vitest.config.ts` `coverage.thresholds`

```ts
// HU-F10.1 (REQ-OPS-152..156) — renamed submit payload + Zod refinement
'src/features/caja/hooks/useArqueo.ts': {
  lines: 90, functions: 90, branches: 85,
},
// HU-F10.1 (REQ-OPS-154) — Sheet with refinement + expected prop + alerta banner
'src/features/caja/components/ArqueoSheet.tsx': {
  lines: 85, functions: 85, branches: 80,
},
// HU-F10.1 (REQ-OPS-152) — routed page composing useArqueoResumen + Sheet
'src/features/caja/pages/ArqueoParcial.tsx': {
  lines: 80, functions: 80, branches: 75,
},
// HU-F10.1 (REQ-OPS-155) — 'arqueo' union + payload schema
'src/lib/print/escposTemplates.ts': {
  lines: 95, functions: 95, branches: 90,
},
// HU-F10.1 (REQ-OPS-155) — buildArqueoBody + dispatch case (mirrors F7.3 precedent)
'src/lib/print/escposBuilder.ts': {
  lines: 85, functions: 85, branches: 80,
},
```

## Open decisions

**None.** All 7 drift anchors (DA-1..DA-7) resolved in `spec.md` §Drift reconciliation table. All 6 architecture decisions (AD-1..AD-6) ratified in `design.md` §Architecture decisions. Preflight ratified chain strategy (`gitflow`) and budget (800 LOC). `delivery_strategy=ask-on-risk` resolves to "proceed" because the forecast is Low.

## Risk acknowledgements

Copied verbatim from `design.md` §Risks carried from spec and `spec.md` §Risk acknowledgements.

| ID | Source | Status | Residual |
|---|---|---|---|
| R1 | REQ-OPS-153 / DA-1 (silent 422 risk if rename missed) | RESOLVED | LOW — single-source-of-truth is the hook payload; `<ArqueoSheet>` consumes the typed return. Mitigated by C1 unit tests on rename + C5 e2e payload alignment (regression guard). |
| R2 | REQ-OPS-154 / DA-4 (justification asymmetry: UI requires, backend permits) | RESOLVED | LOW — explicitly documented in REQ-OPS-156; UI is the gate (Zod refinement), server permits per REQ-OPS-094. Banner drives supervisor visibility, not duplicate POST. |
| R3 | LOC forecast 306 vs soft target 260 | ACCEPTED | LOW — under hard 800 budget. The 46-LOC overshoot comes from e2e (80 LOC) + byte-fixture (40 LOC) — TDD-required per `strict_tdd=true`. Re-baselining to 260 would drop the byte-fixture or the e2e suite; not acceptable. |
| R4 | REQ-OPS-155 / DA-5 ('arqueo' dispatcher missing) | RESOLVED | LOW at design time — being added in C3; full mitigation by C3-GREEN commit. |
| R5 | AD-1 (Dashboard.tsx path correction) | RESOLVED | LOW — actual path is `features/caja/pages/Dashboard.tsx` (verified during tasks authoring, 2026-09-21). The C4 work unit greps for the actual anchor before editing. |
| R6 | REQ-OPS-154 / `factura_pagos` immutability (DA-6) | RESOLVED | LOW — doc-only at the renderer (trigger is server-side); C4 adds a docstring annotation in `useArqueoResumen`; C5 e2e uses `page.route()` mocks instead of mutating `prod.factura_pagos`. |
| R7 | REQ-OPS-156 / hash chain forking (DA-7) | RESOLVED | LOW — relies on shipped `job_sync_cloud.hash_chain_verifier_loop` (PR9b); no new code path introduces a fork. C5 e2e is single-shot per scenario. |

## References

- Proposal: `openspec/changes/fase-10-1-arqueo-parcial/proposal.md`
- Spec: `openspec/changes/fase-10-1-arqueo-parcial/specs/spec.md`
- Design: `openspec/changes/fase-10-1-arqueo-parcial/design.md`
- Plan source: `plan.md` lines 2140-2181 (HU-F10.1)
- Base spec: `openspec/specs/operations/spec.md` REQ-OPS-091..097 (F1.13 backend contract)
- Engram mirrors: `#1888` (proposal), `#1889` (spec), `#1890` (design), `#1887` (SDD session preflight Fase 10)
- Architectural canon: `AGENTS.md` §1 (audit-first), §2 (bi-temporal), §3 (C/Q/U only — no DELETE), §Operational Timeouts (HARD RULE)