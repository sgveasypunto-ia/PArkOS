# Tasks: HU-F12.1 — Panel "Mi turno"

## Header

| Field | Value |
|---|---|
| Change | `fase-12-1-mi-turno` |
| Phase | 12 (Fase 12 — Reportería local mínima, subset de CU-09) |
| Inputs read | `openspec/changes/fase-12-1-mi-turno/proposal.md`; `openspec/changes/fase-12-1-mi-turno/specs/spec.md` (REQ-OPS-184..190); `openspec/changes/fase-12-1-mi-turno/design.md` (7 AD + 18 file changes + 15 tests); `plan.md` lines 2348-2375 |
| Substrate verified | `backend/.../api/v1/operacion.py:42-97`; `backend/.../models/L_S/sesion.py`; `backend/.../models/L_E/ingreso.py:46-49`; `backend/.../models/A/salidas.py:32`; `backend/.../models/A/factura_pagos.py:40-94`; `backend/.../repo/arqueo.py:287-316`; `backend/.../repo/session_cycle.py:46-48`; `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx:78`; `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (exists) |
| Status | DRAFT — awaits `sdd-apply` |
| Preflight | pace=auto, artifact=hybrid, delivery=ask-on-risk, budget=2000 LOC meta-budget, strict_tdd=true, test=pytest+testcontainers (BE) \| vitest+RTL+playwright (FE), author=`Parkos Dev <dev@parkos.local>` |

## Objective

Ship the operator-facing "Mi turno" KPI panel (subset of CU-09 reportería local mínima per `plan.md` L2348-2375): a read-only backend aggregate `GET /operacion/mi-turno?uuid_sesion=X` returning the 7-field `MiTurnoRead` Pydantic over a `Sesion` open-window temporal JOIN, plus a SWR-driven FE `<MiTurnoPanel />` mounted in `Dashboard.tsx` right sidebar above `<OcupacionPanel />` with 5 KPI cards (ingresos / salidas / totalCobrado / efectivo / datafono) and a navigation-only "Cerrar turno" button. Tenant-pinned via JWT issuer scope (no `uuid_sucursal` trust); `Cache-Control: no-store`; 15 s polling cadence (vs F11.x 30 s) justified by operator-live turn metrics; bi-temporal canon preserved (no `uuid_sesion` column added to `[L-E]`/`[A]` tables).

## Work units

Strict-TDD paired RED→GREEN commits. Test commands confirmed against `apps/electron-sucursal/package.json` scripts and `backend/pyproject.toml` (per Phase 9 + Fase 10.x + Fase 11.x precedent). Every work unit maps to one Conventional Commit. Drift anchors DA-F12.1-1..10 + R-F12.1-1..4 + R-CARRY-1 + REQ-OPS-173 letter + REQ-OPS-177..183 are resolved by design; this plan enforces them at commit time.

## Commit plan (final order — strict TDD)

### Backend commits (B-prefixed)

#### C-B1 (RED) — pytest failures before production code

- **What to ship**:
  1. `backend/packages/parkos_core/tests/unit/test_mi_turno_schema.py` (~30 LOC): pytest covering `MiTurnoRead.model_fields.keys()` matches the 7-name fixture, default-zero assertion on `ingresos_count`/`salidas_count`/`total_cobrado_*_cop`, `Cache-Control: no-store` (covered in integration, not unit).
  2. `backend/packages/parkos_core/tests/unit/test_mi_turno_query.py` (~25 LOC): pytest covering the SQL builder at `app/sql/mi_turno_query.py` — pure function returning the expected SQL string for a known uuid_sesion + branch scope tuple.
  3. `backend/packages/parkos_core/tests/integration/test_mi_turno_endpoint.py` (~80 LOC): 5 scenarios against testcontainers Postgres — happy / zero-state / cross-branch 403 / sesion cerrada (post-turn exclusion) / uuid_sesion not found 404.
- **Verify command**: `cd backend && uv run pytest tests/unit/test_mi_turno_*.py tests/integration/test_mi_turno_endpoint.py -q` — MUST be RED (imports fail, no module yet).
- **Runtime harness**: N/A — tests fail at import before reaching the runtime harness.
- **Rollback boundary**: `git revert C-B1` removes the three test files; nothing else changes.
- **Drift anchors resolved**: DA-F12.1-1, DA-F12.1-8, DA-F12.1-9 (test scaffold).
- **Commit message**: `test(operacion): add RED pytests for mi-turno schema, query builder, endpoint`

#### C-B2 (GREEN) — minimal production code to flip RED → GREEN

- **What to ship**:
  1. `backend/packages/parkos_core/src/parkos_core/app/sql/mi_turno_query.py` (NEW, ~40 LOC): pure SQL builder returning the `Sesion` open-window temporal JOIN with `COUNT(*) FILTER (WHERE …)` for `ingresos_count` and `salidas_count`.
  2. `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (MODIFY, +25 LOC): add `MiTurnoRead` Pydantic class with the 7 REQ-OPS-184 fields and zero defaults on count/decimal fields.
  3. `backend/packages/parkos_core/src/parkos_core/repo/mi_turno.py` (NEW, ~40 LOC): `calcular_resumen_mi_turno(session, uuid_sesion, ctx_sucursal_uuid)` orchestrating SQL builder + two `_sum_factura_pagos_by_medio_pago` calls with the canonical medio_pago tuples per AD-3 (`("efectivo",)` for efectivo; `("tarjeta", "datafono")` for datafono) + `timestamp_calculo = _now_naive()`.
  4. `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (MODIFY, +40 LOC): append `GET /mi-turno` handler with `Response` injection for `Cache-Control: no-store`, tenant pin via server-side `Sesion.uuid_sucursal` resolution + 403 on mismatch + 404 on unknown uuid_sesion.
  5. `backend/packages/parkos_core/tests/integration/conftest.py` (MODIFY, +60 LOC): add `sesion_with_ingresos_y_pagos` factory fixture (1 Sesion + 2 ingreso + 1 salida + 3 factura_pagos; mirrors F1.13 pattern).
- **Verify commands**:
  - `cd backend && uv run pytest tests/unit/test_mi_turno_*.py tests/integration/test_mi_turno_endpoint.py -q` — MUST be GREEN (≥10 scenarios).
  - `cd backend && uv run pytest tests/integration/test_mi_turno_endpoint.py -q --cov=parkos_core.operacion --cov-fail-under=80` — coverage ≥80% on the new module.
  - `cd backend && uv run ruff check .` — 0 errors.
  - `cd backend && uv run mypy packages/parkos_core/src` — 0 errors.
- **Runtime harness**: backend pytest integration against testcontainers Postgres (per Fase 10.x + Fase 11.x precedent); tests run real SQL on the seeded fixture.
- **Rollback boundary**: `git revert C-B2` removes the 2 NEW files + the 3 MODIFY lines; `python openspec/scripts/check_schema_match.py` exits 0 (no migration added; read-only aggregator).
- **Drift anchors resolved**: DA-F12.1-1, DA-F12.1-2, DA-F12.1-4, DA-F12.1-6, DA-F12.1-9, DA-F12.1-10, R-F12.1-1, R-F12.1-2.
- **Commit message**: `feat(operacion): add GET /operacion/mi-turno read-only aggregator`

#### C-B3 (docs) — endpoint documentation

- **What to ship**:
  1. `backend/docs/api/operacion.md` (NEW or MODIFY, +40 LOC): document `GET /operacion/mi-turno` with Pydantic `MiTurnoRead` shape, query parameters, response codes (200/403/404), `Cache-Control: no-store` note, curl example, tenant-pin invariants.
- **Verify command**: read-back review (no executable test).
- **Runtime harness**: N/A — docs commit.
- **Rollback boundary**: `git revert C-B3` removes the docs file/section; no production code affected.
- **Drift anchors resolved**: DA-F12.1-7 (partial — i18n keys covered in C-F4).
- **Commit message**: `docs(operacion): document GET /operacion/mi-turno endpoint`

### Frontend commits (F-prefixed)

#### C-F1 (RED) — vitest failures before production code

- **What to ship**:
  1. `apps/electron-sucursal/src/lib/api/schemas/__tests__/mi-turno.test.ts` (~40 LOC): Zod parse + key-set lock test (`Object.keys(MiTurnoSchema.shape)` matches the 7-field fixture, `strict()` rejects unknown fields, DA-F12.1-9 drift gate).
  2. `apps/electron-sucursal/src/features/operacion/__tests__/useMiTurno.test.ts` (~80 LOC, 4 scenarios): loading / zero state (data undefined → all-zero KPI render) / 15s polling cadence / 401 mid-polling → `useAuthStore.getState().clear()` + `parkos:auth:cleared` event dispatch.
  3. `apps/electron-sucursal/src/features/operacion/__tests__/MiTurnoPanel.test.tsx` (~120 LOC, 5 scenarios): zero-state (uuid_sesion null → all zeros, no skeleton, no error), non-zero rendering of 5 KPI cards, 401 fallback, 5xx fallback, Cerrar-turno click → `navigate('/caja/cerrar-turno')` only (no `cerrarSesion` call).
- **Verify command**: `cd apps/electron-sucursal && pnpm vitest run src/features/operacion/ src/lib/api/schemas/__tests__/mi-turno.test.ts` — MUST be RED (imports fail).
- **Runtime harness**: vitest unit tests with mocked `parkosFetch` + SWR `mutate` injection (per Fase 10.2 / F11.x precedent).
- **Rollback boundary**: `git revert C-F1` removes the three test files; nothing else changes.
- **Drift anchors resolved**: DA-F12.1-1, DA-F12.1-3, DA-F12.1-9 (FE side).
- **Commit message**: `test(operacion): add RED vitests for mi-turno schema, hook, panel`

#### C-F2 (GREEN) — types + Zod schema + SWR hook + Cerrar-turno button

- **What to ship**:
  1. `apps/electron-sucursal/src/features/operacion/types.ts` (NEW, ~30 LOC): shared TS types derived from BE `MiTurnoRead` (7-field snake_case verbatim).
  2. `apps/electron-sucursal/src/lib/api/schemas/mi-turno.ts` (NEW, ~25 LOC): Zod `MiTurnoSchema` matching backend Pydantic field-for-field, `.strict()` (rejects unknown fields), 7 fields per REQ-OPS-189.
  3. `apps/electron-sucursal/src/features/operacion/hooks/useMiTurno.ts` (NEW, ~80 LOC): SWR hook — key `'api/v1/operacion/mi-turno?uuid_sesion=' + uuid_sesion` (gated by `accessToken` + `uuid_sesion`), `refreshInterval: 15_000`, `dedupingInterval: 5_000`, `revalidateOnReconnect: true`, `shouldRetryOnError` excluding 401/403/404, `onError` triggering 401 cleanup; fetcher is `parkosFetch<unknown>(url)` + `MiTurnoSchema.parse(raw)`.
  4. `apps/electron-sucursal/src/features/operacion/components/CerrarTurnoButton.tsx` (NEW, ~30 LOC): shadcn `Button` with `onClick={() => navigate('/caja/cerrar-turno')}` ONLY (navigation, no business logic). Disabled when `uuid_sesion` is null.
- **Verify commands**:
  - `cd apps/electron-sucursal && pnpm vitest run src/features/operacion/ src/lib/api/schemas/__tests__/mi-turno.test.ts` — MUST be GREEN.
  - `cd apps/electron-sucursal && pnpm lint` — 0 errors.
  - `cd apps/electron-sucursal && pnpm tsc -p tsconfig.renderer.json --noEmit` — 0 errors.
- **Runtime harness**: vitest unit tests against mocked fetch (per Fase 10.2 / F11.x precedent).
- **Rollback boundary**: `git revert C-F2` removes the 4 NEW files; no other component or mount changes.
- **Drift anchors resolved**: DA-F12.1-1 (FE side), DA-F12.1-3 (polling cadence), DA-F12.1-5 (navigation-only button), DA-F12.1-9 (FE side).
- **Commit message**: `feat(operacion): add useMiTurno hook, Zod schema, CerrarTurnoButton`

#### C-F3 (GREEN) — KPI card + panel orchestrator

- **What to ship**:
  1. `apps/electron-sucursal/src/features/operacion/components/MiTurnoKpiCard.tsx` (NEW, ~40 LOC): shadcn `Card` KPI cell — semantic tokens only; `tabular-nums`; `aria-label={label}`; `data-testid={`mi-turno-kpi-${slug(label)}`}`.
  2. `apps/electron-sucursal/src/features/operacion/components/MiTurnoPanel.tsx` (NEW, ~120 LOC): orchestrator — `useMiTurno(uuid_sesion)` + shadcn `Card` strip with header `t("miTurno.titulo")`, body grid of 5 `<MiTurnoKpiCard>` (ingresos / salidas / totalCobrado / efectivo / datafono), footer `<CerrarTurnoButton>`. Zero-state (`uuid_sesion === null` OR `data === undefined`) renders all-zero KPIs without skeleton or error.
- **Verify command**: `cd apps/electron-sucursal && pnpm vitest run src/features/operacion/__tests__/MiTurnoPanel.test.tsx` — MUST be GREEN.
- **Runtime harness**: vitest unit tests with RTL (per Fase 10.2 / F11.x precedent).
- **Rollback boundary**: `git revert C-F3` removes the 2 NEW files; `<CerrarTurnoButton />` from C-F2 still exists but unused.
- **Drift anchors resolved**: DA-F12.1-4 (zero-state), DA-F12.1-5 (Cerrar-turno navigation-only), DA-F12.1-7 (partial — i18n keys in C-F4).
- **Commit message**: `feat(operacion): add MiTurnoPanel orchestrator and MiTurnoKpiCard`

#### C-F4 (mount + i18n) — wire panel into Dashboard + add locale keys

- **What to ship**:
  1. `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` (MODIFY, +10 LOC): import `<MiTurnoPanel />` + `<useSesionActiva>`; mount `<MiTurnoPanel uuid_sesion={sesion?.uuid ?? null} />` in the right sidebar ABOVE `<OcupacionPanel />` per AD-4.
  2. `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (MODIFY, +30 LOC): add 8 es-CO keys — `miTurno.titulo`, `miTurno.kpis.ingresos`, `miTurno.kpis.salidas`, `miTurno.kpis.totalCobrado`, `miTurno.kpis.efectivo`, `miTurno.kpis.datafono`, `miTurno.cerrarTurno`, `miTurno.unidades.cop`.
- **Verify commands**:
  - `cd apps/electron-sucursal && pnpm vitest run src/features/operacion/ src/lib/api/schemas/__tests__/mi-turno.test.ts` — STILL GREEN (no behavior regression).
  - `cd apps/electron-sucursal && pnpm tsc -p tsconfig.renderer.json --noEmit` — 0 errors.
  - `cd apps/electron-sucursal && pnpm lint` — 0 errors.
- **Runtime harness**: vitest unit tests still pass; mount is a render-only integration with Dashboard.
- **Rollback boundary**: `git revert C-F4` removes the import + mount line + the 8 i18n keys; the panel component still exists (from C-F3) but is unused.
- **Drift anchors resolved**: DA-F12.1-7 (i18n keys complete), DA-F12.1-8 (mount position).
- **Commit message**: `feat(operacion): mount MiTurnoPanel in Dashboard and add es-CO i18n keys`

#### C-F5 (e2e + apply-progress) — playwright spec + apply-progress artifact

- **What to ship**:
  1. `apps/electron-sucursal/e2e/mi-turno.spec.ts` (~150 LOC): 2 scenarios — (a) KPIs visible after login, (b) Cerrar-turno navigates to `/caja/cerrar-turno`. Both wrapped in `test.skip("skip reason: sandbox F.6 — Playwright cannot launch real Electron", async () => { ... })` per F10.2/F11.x precedent (R-F12.1-3). Empty body logged with skip reason; assertion block documented in comments for post-sandbox runner.
  2. `openspec/changes/fase-12-1-mi-turno/apply-progress.md` (NEW): mirror the F11.2 archived apply-progress.md template — initial state, C-B1..C-F5 commit log, test results, drift-anchor coverage matrix, links to next phase.
- **Verify command**: `cd apps/electron-sucursal && pnpm playwright test e2e/mi-turno.spec.ts` — both scenarios `test.skip`, exit `0`.
- **Runtime harness**: N/A in sandbox F.6; scenarios are gated by `test.skip(...)` and the runner exits 0 on skipped tests.
- **Rollback boundary**: `git revert C-F5` removes the e2e file + apply-progress artifact; nothing else changes.
- **Drift anchors resolved**: DA-F12.1-8 (e2e coverage), R-F12.1-3 (sandbox precedent).
- **Commit message**: `test(operacion): add e2e mi-turno spec (sandbox-skipped) and apply-progress artifact`

#### C-F6 (housekeeping) — close Fase 12 backlog + capture learnings

- **What to ship**:
  1. `openspec/_meta/pending-fase-12.md` (NEW): one-line row capturing F12.1 closure — pointer to `archive/2026-09-21-fase-12-1-mi-turno/` once archive phase runs; carries forward any unresolved F12.x work (none in scope here).
- **Verify command**: read-back review (no executable test).
- **Runtime harness**: N/A — housekeeping commit.
- **Rollback boundary**: `git revert C-F6` removes the `_meta/pending-fase-12.md` row; no production code affected.
- **Drift anchors resolved**: R-CARRY-1 (F11.x carryover thresholds still apply; no Fase 12 carryovers introduced).
- **Commit message**: `chore(sdd): record F12.1 closure in pending-fase-12`

## Drift-anchor verification checklist

| Anchor | Severity | Resolved by commit | Verification |
|---|---|---|---|
| DA-F12.1-1 (BE/FE schema match) | High | C-B1, C-B2, C-F1, C-F2 | Static key-set test runs in BOTH `test_mi_turno_schema.py` (BE pytest) and `__tests__/mi-turno.test.ts` (FE vitest); both fail on drift. |
| DA-F12.1-2 (tenant pin) | High | C-B2 | Handler resolves `Sesion.uuid_sucursal` server-side; cross-branch returns 403 `sesion_cross_branch_forbidden` (test_mi_turno_endpoint.py scenario 3). |
| DA-F12.1-3 (15s polling vs F11.x 30s) | Med | C-F2, C-F1 | `useMiTurno.test.ts` scenario 3 asserts `refreshInterval: 15_000` + `dedupingInterval: 5_000`. AD-5 justifies cadence as operator-live turn metrics. |
| DA-F12.1-4 (zero-state) | Med | C-B2, C-F3, C-F1 | BE returns 200 + zeros (test_mi_turno_endpoint.py scenario 2); FE renders 0 without skeleton/error (MiTurnoPanel.test.tsx scenario 1, useMiTurno.test.ts scenario 2). |
| DA-F12.1-5 (Cerrar-turno button reuse) | Med | C-F2, C-F3, C-F1 | `CerrarTurnoButton.tsx` only calls `navigate('/caja/cerrar-turno')`; MiTurnoPanel.test.tsx scenario 5 asserts no `cerrarSesion` mutation. |
| DA-F12.1-6 (backend stub) | Low | C-B2 | Extend existing `api/v1/operacion.py` router (no new file); grep confirms `/mi-turno` route absent pre-C-B2. |
| DA-F12.1-7 (i18n keys) | Low | C-F4 | 8 keys added to `operacion.json`; grep confirms presence post-C-F4. |
| DA-F12.1-8 (test fixture) | Med | C-B2 | `sesion_with_ingresos_y_pagos` factory fixture in `tests/integration/conftest.py` (mirrors F1.13 pattern); used by test_mi_turno_endpoint.py scenarios 1, 2, 5. |
| DA-F12.1-9 (FE/BE drift) | High | C-B1, C-B2, C-F1, C-F2 | Defense-in-depth key-set lock in BOTH test pyramids runs on every CI build. |
| DA-F12.1-10 (no `uuid_sesion` on ingreso/salidas) | High | C-B2 | Sesion open-window temporal JOIN via `fecha_ingreso`/`fecha_salida` predicates; `python openspec/scripts/check_schema_match.py` exits 0 (no column added to `[L-E]`/`[A]`). |
| R-F12.1-1 (bi-temporal canon) | High | C-B2 | Open-window JOIN preserves `[L-E]`/`[A]` immutability; no migration script touched. |
| R-F12.1-2 (SUM helper reuse) | Med | C-B2 | `_sum_factura_pagos_by_medio_pago` reused verbatim; no new SUM helper in `repo/mi_turno.py`. |
| R-F12.1-3 (sandbox F.6 Playwright) | Low | C-F5 | Both e2e scenarios wrapped in `test.skip(...)`; runner exits 0 in sandbox. |
| R-F12.1-4 (15s polling load) | Med | C-F2, C-F1 | `prod.sesion` partial unique index bounds SUM cardinality to 1 active session per operator; `dedupingInterval: 5_000` cuts idle fetches. |
| R-CARRY-1 (F11.x thresholds) | Low | C-F6 | No occupancy thresholds in F12.1; inherited thresholds unchanged. |
| REQ-OPS-173 letter (F11.1) | Low | C-B2, C-F2 | REQ-OPS-184..190 added; REQ-OPS-173 untouched (verified via grep in spec archive). |
| REQ-OPS-177..183 (F11.2) | Low | C-B2, C-F2 | F12.1 deltas `operations` domain; F11.2 entries remain authoritative (verified via `openspec/specs/operations/spec.md` last entry check). |

## Test commands summary

### Backend

| Command | Purpose | Expected |
|---|---|---|
| `cd backend && uv run ruff check .` | Lint backend code | 0 errors |
| `cd backend && uv run mypy packages/parkos_core/src` | Type check backend (mypy --strict) | 0 errors |
| `cd backend && uv run pytest tests/unit/test_mi_turno_*.py -q` | Run BE unit tests (schema + SQL builder) | ≥5 scenarios green |
| `cd backend && uv run pytest tests/integration/test_mi_turno_endpoint.py -q --cov=parkos_core.operacion --cov-fail-under=80` | Run BE integration tests with coverage gate | ≥5 scenarios green; coverage ≥80% on new module |
| `cd backend && uv run pytest tests/ -q` | Full backend regression (F11.x + F10.x still green) | All pre-existing tests still pass |

### Frontend

| Command | Purpose | Expected |
|---|---|---|
| `cd apps/electron-sucursal && pnpm lint` | ESLint FE code | 0 errors |
| `cd apps/electron-sucursal && pnpm tsc -p tsconfig.renderer.json --noEmit` | TypeScript strict compile | 0 errors |
| `cd apps/electron-sucursal && pnpm vitest run src/features/operacion/ src/lib/api/schemas/__tests__/mi-turno.test.ts` | Run FE unit tests for F12.1 | ≥9 scenarios green (3 schema + 4 hook + 5 panel, with overlap) |
| `cd apps/electron-sucursal && pnpm vitest run` | Full FE regression (F11.x + F10.x still green) | All pre-existing tests still pass |
| `cd apps/electron-sucursal && pnpm playwright test e2e/mi-turno.spec.ts` | Run e2e spec | 2 scenarios `test.skip`, exit 0 |
| `cd apps/electron-sucursal && pnpm playwright test e2e/` | Full e2e regression | All pre-existing scenarios (skipped or green) still pass |

### Drift verification (post-merge)

| Command | Purpose | Expected |
|---|---|---|
| `python openspec/scripts/check_schema_match.py` | Verify ER.mmd ↔ migration match (no schema change for F12.1) | exits 0 |

## Plain-text guard lines (REQUIRED — literal match for downstream guards)

```
Decision: single-pr
Chained PRs: No
Chain strategy: n/a
Delivery strategy: ask-on-risk
Size exception: No (forecast 985 <= 2000 baseline)
Review budget risk: Med
Review budget hard limit: 2000 lines (meta-budget ratified)
Forecast ~985 LOC actual
```

## Review Workload Forecast (parseable)

| Field | Value |
|-------|-------|
| Estimated changed lines | ~985 |
| 800-line budget risk | High |
| 2000-line baseline risk | Low |
| Chained PRs recommended | No |
| Size exception needed | No |
| Decision needed before apply | No |

Forecast source: `design.md` "File changes" table totals ~485 LOC source + ~500 LOC tests = ~985 LOC across 14 NEW + 4 MODIFY files. Forecast sits below the 2,000-line meta-budget ratified in this session preflight; above the 800-line PR threshold from `config.yaml rules.tasks` (risk is HIGH per the heuristic, but the preflight explicitly ratified 2,000 as the operative cap for F12.1, so `Chained PRs recommended = No`). Delivery strategy `ask-on-risk` resolves to `Decision needed before apply = No` because the size exception is not required (forecast below 2,000 baseline).

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
2000-line baseline risk: Low

## Open decisions

None. All 7 design decisions (AD-1..AD-7) resolved. The 3 open questions from the spec phase (Q1 medio_pago tuples, Q2 `timestamp_calculo` source, Q3 query-vs-header for `uuid_sesion`) were resolved by the design phase and codified in AD-2, AD-3, AD-6.

## Risk acknowledgements (carried from `design.md` Risk acknowledgements table)

| ID | Severity | Mitigation in design |
|---|---|---|
| DA-F12.1-1 (BE/FE schema match) | High | AD-6: static key-set test in both pytest + vitest. |
| DA-F12.1-2 (tenant pin) | High | AD-2: server-side `Sesion.uuid_sucursal` resolution + 403 on mismatch. |
| DA-F12.1-3 (15s polling vs F11.x 30s) | Med | AD-5: partial unique index bounds SUM cardinality; `dedupingInterval: 5_000` cuts idle fetches. |
| DA-F12.1-4 (zero-state) | Med | AD-1: BE always 200 with zeros; AD-5: FE renders 0 without skeleton/error. |
| DA-F12.1-5 (Cerrar-turno button reuse) | Med | AD-4: button navigates only; F10.2 owns close logic. |
| DA-F12.1-6 (backend stub) | Low | AD-1: extend existing router; no new router file. |
| DA-F12.1-7 (i18n keys) | Low | AD-4: 8 keys added to `operacion.json` (es-CO only). |
| DA-F12.1-8 (test fixture) | Med | AD-7: `sesion_with_ingresos_y_pagos` factory fixture (F1.13 pattern). |
| DA-F12.1-9 (FE/BE drift) | High | AD-6: defense-in-depth key-set lock in both test pyramids. |
| DA-F12.1-10 (no `uuid_sesion` on ingreso/salidas) | High | AD-3: Sesion open-window temporal JOIN preserves bi-temporal canon. |
| R-CARRY-1 (F11.x thresholds) | Low | Inherited F11.1/F11.2 thresholds carry forward without modification — F12.1 has no occupancy thresholds. |
| REQ-OPS-173 letter (F11.1) | Low | Unchanged. F12.1 adds REQ-OPS-184..190; REQ-OPS-173 untouched. |
| REQ-OPS-177..183 (F11.2) | Low | Unchanged. F12.1 deltas `operations` domain; F11.2 entries remain authoritative. |
| Q3 (query-vs-header for uuid_sesion) | Low | Resolved in AD-2: query string for simplicity; matches existing `/operacion/ingresos?placa=X` precedent. Tradeoff: query params are URL-logged at proxy layer (no PII here — UUID only) — header alternative would force FE refactor and break F2.2 invariant. |
| R-F12.1-1 (bi-temporal canon) | High | AD-3: open-window JOIN via `fecha_ingreso` / `fecha_salida` predicates; no column added to `[L-E]`/`[A]`. |
| R-F12.1-2 (SUM helper reuse) | Med | AD-3: `_sum_factura_pagos_by_medio_pago` reused verbatim with canonical tuples. |
| R-F12.1-3 (sandbox F.6 Playwright) | Low | AD-7: e2e `test.skip(...)` per F10.2/F11.x precedent; vitest unit tests cover same surface. |
| R-F12.1-4 (15s polling load) | Med | AD-5: 1 active sesion per operator (partial unique index) bounds SUM cost. |

## Suggested work units (PR slice preview)

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Backend RED→GREEN (C-B1 + C-B2 + C-B3) | PR-12.1 (single PR with chained commits per Fase 11.x precedent) | `cd backend && uv run pytest tests/unit/test_mi_turno_*.py tests/integration/test_mi_turno_endpoint.py -q --cov=parkos_core.operacion --cov-fail-under=80` | pytest + testcontainers Postgres | `git revert C-B1..C-B3` removes 2 NEW files + 3 MODIFY lines + 1 docs section; no schema change |
| 2 | Frontend RED→GREEN (C-F1 + C-F2 + C-F3) | Same PR-12.1 (committed atop unit 1) | `cd apps/electron-sucursal && pnpm vitest run src/features/operacion/ src/lib/api/schemas/__tests__/mi-turno.test.ts` | vitest unit tests with mocked parkosFetch | `git revert C-F1..C-F3` removes 5 NEW files; mount in C-F4 still references them |
| 3 | Frontend mount + i18n + e2e + housekeeping (C-F4 + C-F5 + C-F6) | Same PR-12.1 (committed atop unit 2) | `cd apps/electron-sucursal && pnpm vitest run src/features/operacion/ src/lib/api/schemas/__tests__/mi-turno.test.ts && pnpm playwright test e2e/mi-turno.spec.ts` | vitest + playwright (sandbox-skipped) | `git revert C-F4..C-F6` removes 1 MODIFY + 1 NEW locale + 1 NEW e2e + 1 NEW housekeeping; panel exists but un-mounted |

Note: Forecast ~985 LOC is below the 2,000-line meta-budget ratified in this session preflight, so all 9 commits land in a single PR-12.1. If mid-apply the forecast approaches 1,500 LOC, the orchestrator should re-evaluate and propose a chain split between unit 1 (BE) and unit 2+3 (FE) per `delivery_strategy=ask-on-risk`.