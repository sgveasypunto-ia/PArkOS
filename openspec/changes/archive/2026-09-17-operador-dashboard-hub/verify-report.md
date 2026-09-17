```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:BD526A8F7A2BB3EB3333FE5DDEDBE93014E73FE076E2F583A86B28D0C4B59CC6
verdict: fail
blockers: 3
critical_findings: 4
requirements: 5/5
scenarios: 6/10
test_command: pnpm exec vitest run src/features src/renderer/store src/components 2>&1
test_exit_code: 1
test_output_hash: sha256:BD526A8F7A2BB3EB3333FE5DDEDBE93014E73FE076E2F583A86B28D0C4B59CC6
build_command: pnpm exec tsc -b 2>&1
build_exit_code: 1
build_output_hash: sha256:2A3A34106FF66C787F1166E52FA46FDD70251D4D8A9657CA6FDD4CFE9BB3AA9A
```

# Verification Report — `operador-dashboard-hub`

**Change**: operador-dashboard-hub
**Version**: 1 (REQ-OPS-136..140)
**Mode**: Standard
**Date**: 2026-09-17
**PRs**: PR-1..PR-6 stacked-to-main; 6 merge commits `49b90dc..d47af58` on `origin/dev`; feature branch deleted (clean).
**Files**: 36 changed; +3496/-75 (apps/electron-sucursal only).

## Completeness

| Metric | Value |
|---|---|
| Tasks total | 37 (tasks.md PR-1..PR-6) |
| Tasks complete | 37 (`all_done`) |
| Tasks incomplete | 0 |

## Build & Tests Execution

**Build (tsc -b)**: ❌ Failed (exit `1`).
Post-change TS errors = 94 vs pre-PR-1 baseline = 89. **Δ +5 NEW errors** introduced by this change (after subtracting 5 pre-existing errors that were line-shifted or relocated). Pre-existing log sha256 `617A4AA9…`. Post-change log sha256 `2A3A3410…`.

**Tests (vitest, full scope)**: ❌ 9 failed / 21 passed (test files); 13 failed / 168 passed (tests). Exit `1`.
All 9 failing files use `@testing-library/user-event` (F.6 sandbox dep missing) — pre-existing infra issue per AGENTS.md verify #4. **None of the failing test files were modified by this change** (`git diff 22823c2..d47af58` confirms only `useCotizacion.test.ts` + `Dashboard.test.tsx` are touched in this scope, both PASS).

**Tests (scope-of-change)**: ✅ 20/20 PASS across the 4 files this change adds/modifies (`dashboardDrawerStore`, `OcupacionPanel`, `useCotizacion`, `useFacturaElectronica`, `PagoSheet`, `SalidaPanel`, `Dashboard`).

**Coverage**: per-file line+branch coverage not yet wired in vitest config; threshold not enforced this change.

## Spec Compliance Matrix (5 REQ × 2 scenarios)

| REQ | Scenario | Test | Result |
|-----|----------|------|--------|
| REQ-OPS-136 | Dashboard loads post-turno | `Dashboard.test.tsx > U16` (sesion poblado → hub) | ✅ COMPLIANT |
| REQ-OPS-136 | Dashboard redirects pre-turno | `Dashboard.test.tsx > U15` (sesion=null → navigate('/caja/abrir-turno')) | ✅ COMPLIANT |
| REQ-OPS-137 | Section lazy-mount | `useCotizacion.test.ts > C1` + `SalidaPanel.test.tsx > S2` (uuid_ingreso=null → key=null) | ✅ COMPLIANT |
| REQ-OPS-137 | Panel refresh independence (ErrorBoundary) | (none found) | ⚠️ UNTESTED-traceable-to-design |
| REQ-OPS-138 | Single-drawer guard | `dashboardDrawerStore.test.ts > D3` + `PagoSheet.test.tsx > P5` (swap pago→arqueo) | ✅ COMPLIANT |
| REQ-OPS-138 | Esc key closure + focus-restore | (none found) | ❌ UNTESTED |
| REQ-OPS-139 | Cold Dashboard has 0 panel fetches | `useCotizacion.test.ts > C1` + `useFacturaElectronica.test.ts > F1` + `PagoSheet.test.tsx > P1` (closed by default) | ⚠️ PARTIAL — covers 3 of 5 panels; FacturaElectronicaRetryPanel exists but is NOT mounted in Dashboard.tsx or DrawerHost.tsx |
| REQ-OPS-139 | Cotizacion lazy-mount on active ingreso | `useCotizacion.test.ts > C2` (uuid set → fetches bare UUID) | ✅ COMPLIANT |
| REQ-OPS-140 | App.tsx global strip removed | manual inspection (`git show HEAD:apps/electron-sucursal/src/renderer/App.tsx`) — `<OcupacionStrip />` absent; comment block L11-21 documents the F4.3 "TEMPORAL" honour | ✅ COMPLIANT |
| REQ-OPS-140 | Inline panel matches global-strip baseline | `OcupacionPanel.test.tsx > P1..P5` (5/5 pass) | ✅ COMPLIANT |

**Compliance summary**: 6/10 scenarios COMPLIANT with passing test, 1 PARTIAL, 2 UNTESTED, 1 untested-traceable-to-design.

## Correctness (Static Evidence, ADR D1–D5)

| Decision | Status | Evidence |
|---|---|---|
| D1 — Route strategy: enrich `/` | ✅ PASS | `App.tsx:33-65` — same 4 routes (`/login`, `/`, `/caja/abrir-turno`, `/caja/cerrar-turno`, 404); no new route added. |
| D2 — Drawer state machine: Zustand | ✅ PASS | `renderer/store/dashboardDrawerStore.ts` (61 LOC): exports `useDashboardDrawerStore`, `DrawerKind` (6 kinds incl. `fe-retry`), `open(kind, anchorId)`, `close()`, `isDrawerOpen()`. Tests: 7/7 pass. |
| D3 — Lazy-mount threshold: SWR key gate | ✅ PASS | `useCotizacion.ts:78-107` — `key = uuid_ingreso && accessToken ? … : null`. Same idiom in `useFacturaElectronica`. `SalidaPanel.tsx:81` uses `useCotizacion(uuid_ingreso)`. |
| D4 — Sync-strip relocation | ✅ PASS | Global `<OcupacionStrip />` absent from `App.tsx`; `<OcupacionPanel />` mounts at `Dashboard.tsx:111` inside dashboard-section slot 1. |
| D5 — Translation namespaces | ✅ PASS | 10 locale files (was 7 — added `alertas.json`, `reimpresion.json`, `suscripciones.json`). `caja.json` extended with `dashboard.{turnoActivo,operar,ocupacion,suscripciones,sync,alertas}` = 6 keys as spec'd. |

## Coherence (Design)

| Spec component | File:line | Note |
|---|---|---|
| `<CotizacionPanel />` (referenced in REQ-OPS-139) | **MISSING** | Implementation embeds cotizacion `<dl>` inside `<SalidaPanel />` (`SalidaPanel.tsx:138-172`) instead of a standalone `<CotizacionPanel />`. Spec INTENT preserved (lazy-mount via SWR key=null), but component NAMES diverged. |
| `<FacturaElectronicaRetryPanel />` (referenced in REQ-OPS-139) | file exists, **never mounted** | `grep FacturaElectronicaRetryPanel src/**` returns only its own self-doc; dead code. |
| `<ArqueoSheet />`, `<CierreDiarioDialog />` mounted via DrawerHost with `uuid_sucursal={null} uuid_sesion={null}` | `DrawerHost.tsx:42,45` | Drawer shells render but lazy-gated — visible only when store open + UUID later provided by caller. Currently a SHELL: no caller wires non-null UUIDs. |
| `<PagoSheet uuid_ingreso={null} total_cop={0} onSubmit={async () => {}} />` | `DrawerHost.tsx:29-35` | PR-3 placeholder; submit is a no-op. |
| `SesionRead.vigente` derived client-side | `useSesionActiva.ts:87` (return `SesionRead \| null`) | The "vigente" derivation is implicit via `timestamp_cierre === null`; not asserted by any test. |

## Issues Found

**CRITICAL**:

1. **TS6307 drift** — `tsconfig.renderer.json:30-42` `include` block was NOT extended to include the 5 new feature folders. 7 NEW TS6307 errors: `Dashboard.tsx:44,27` (PagoSheet), `Dashboard.tsx:45,36` (SuscripcionesPanel), `Dashboard.tsx:46,33` (SyncStatusStrip), `Dashboard.tsx:47,30` (AlertasPanel), `SuscripcionesPanel.tsx:13,38` (useSuscripcionesList), `SyncStatusStrip.tsx:11,31` (useSyncEstado). DrawerHost.tsx had a similar error pre-change (1 removed). Net +5 NEW TS errors.
2. **TS6133 dead import** — `Dashboard.tsx:44` imports `PagoSheet` but never references it in JSX (PagoSheet mounts via `DrawerHost`). Dead import → TS6133.
3. **TS2322 `return null`** — `Dashboard.tsx:152` `return null` not assignable to `JSX.Element`. Pre-existing TS2322 at `Dashboard.tsx:87` was shifted to L152 by the rewrite; not a fresh regression but unaddressed.

**WARNING** (pre-existing / known / out-of-scope):

4. **F.6 sandbox missing `@testing-library/user-event`** — 9 vitest test files fail with `Failed to resolve import "@testing-library/user-event"` (`LoginForm`, `Login`, `AbrirTurno`, `CerrarTurno`, `TurnoActivoPanel`, `ForzarIngresoModal`, `PlacaInput`, `TiqueteModal`, `Principal`). Pre-existing — none touched by this change (per AGENTS.md verify #4: out of scope).
5. **Dead code: `<FacturaElectronicaRetryPanel />`** — file exists at `facturacion/components/FacturaElectronicaRetryPanel.tsx`, never mounted. Spec REQ-OPS-139 Scenario 1 references it.
6. **Drawer shells wired with null UUIDs** — DrawerHost.tsx mounts `<PagoSheet uuid_ingreso={null}>`, `<ArqueoSheet uuid_sesion={null}>`, `<CierreDiarioDialog uuid_sucursal={null} uuid_sesion={null}>`. Functionality exists in the components but the dashboard doesn't drive the flow.
7. **REQ-OPS-138 §Esc scenario UNTESTED** — `dashboardDrawerStore.test.ts` covers state transitions but no test asserts `document.activeElement === trigger` after close (jsdom viable).
8. **REQ-OPS-137 §ErrorBoundary scenario UNTESTED** — design.md Testing Strategy requires per-panel `<ErrorBoundary />` containment; no test asserts it.
9. **Pre-existing TS errors (useOcupacion.ts:91, StatusBar.test.tsx, useTiposVehiculo.test.ts)** — per AGENTS.md verify #4: out of scope.

**SUGGESTION**:

10. `<CotizacionPanel />` referenced by spec but implemented as inline `<dl>` block inside `SalidaPanel.tsx`. Spec INTENT preserved (lazy-mount via SWR gate); naming divergence is cosmetic. Consider extracting to its own component for testability of the `<dl>` rendering in isolation.
11. Use of `useDashboardDrawerStore.getState().close()` in DrawerHost onClose handlers — verify per-drawer focus restoration (REQ-OPS-138 §Esc) is wired in each component's `onOpenChange`.

## Verdict

**FAIL** — 3 substantive failures introduced by this change: (a) tsconfig.renderer.json was not extended to include the 5 new feature folders, blocking `tsc -b` from compiling the new files; (b) `PagoSheet` dead import in `Dashboard.tsx:44`; (c) pre-existing `return null` type mismatch not remediated by the Dashboard rewrite. 5/10 spec scenarios lack a passing covering test at the integration level (Esc/focus-restore, cold-Dashboard integration, error boundary containment). Live API confirmed post-merge via `qa-2026-09-17-bug-remediation` + manual QA replay (`openspec/changes/operador-dashboard-hub/manual-qa-replay.md`), so runtime behavior is OK; the verdict is rooted in static + unit-test evidence per the verify contract.

**next_recommended**: `sdd-apply` focused remediation: extend `tsconfig.renderer.json` include block with `src/features/{facturacion,reimpresion,suscripciones,sync,alertas}/**/*.{ts,tsx}`, remove dead `PagoSheet` import from `Dashboard.tsx:44`, fix `Dashboard.tsx:152` return type, then add 2 missing tests (`dashboardDrawerStore Esc + focus restore`; `Dashboard cold-mount network calls spy`). Expected delta: <30 LOC, single PR (`fix/dashboard-tsconfig-and-tests`).