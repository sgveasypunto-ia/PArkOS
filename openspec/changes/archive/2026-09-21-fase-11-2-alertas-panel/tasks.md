# Tasks: HU-F11.2 — Panel de alertas locales (AlertasPanel)

## Header

| Field | Value |
|---|---|
| Change | `fase-11-2-alertas-panel` |
| Phase | sdd-tasks (Phase 5 of SDD cycle) |
| Inputs read | `proposal.md` (144 lines, 14 drift anchors); `specs/spec.md` (333 lines, REQ-OPS-177..183); `design.md` (242 lines, 7 ADs, 23 file changes, 26 tests, ~1,530 LOC); `plan.md` lines 2303-2344; `apps/electron-sucursal/package.json` scripts; `apps/electron-sucursal/tsconfig.renderer.json` |
| Status | READY for sdd-apply |
| Preflight | pace=auto, artifact=hybrid (OpenSpec + Engram), delivery=ask-on-risk, budget=2000 LOC (Fase 11+ meta-budget), strict_tdd=true, test=vitest+playwright, author=`Parkos Dev <dev@parkos.local>` |

## Objective

As a branch operator, view the active alerts for my branch, understand what each one means, and mark them as resolved when appropriate — closing the last gap of Fase 11 by shipping `<AlertasPanel />` (list + filter chips + per-`tipo_alerta` drill-down + append-only "marcar revisada" transition), the 8-vs-11 client-side filter (`BUSINESS_ALERT_CODES`, ABIERTO-06), the drill-down router map keyed by `tipo_alerta`, and the reconciled FE Zod `estado` enum aligned to BE Pydantic `Literal["activa","descartada","resuelta"]` (DA-F11.2-9 GATING resolved). The corrected `GET /workflows/alerta` endpoint from HU-F1.1 is assumed working; F11.2 does not retouch the backend route.

## Work units

Strict-TDD work units, one deliverable behavior per commit. Each work unit ships RED → GREEN → REFACTOR inside a single commit boundary; no commit mixes concerns.

| Unit | Goal | Test command | Runtime harness | Rollback boundary |
|------|------|--------------|-----------------|-------------------|
| WU-1 (C1) | RED scaffold: 14 unit/RTL tests fail before any source change | `pnpm vitest run src/features/alertas/ src/lib/api/schemas/alertas.ts` | vitest with `vi.useFakeTimers` | delete 4 test files; no source yet exists |
| WU-2 (C2) | GREEN schemas + hook: 18-field Zod + canonical enum + SWR parallel fetch + merge | `pnpm vitest run src/features/alertas/ src/lib/api/schemas/alertas.ts` | vitest | revert `lib/api/schemas/alertas.ts` + `features/alertas/hooks/useAlertas.ts` |
| WU-3 (C3) | GREEN panel + components: list + filter chips + drill-down + resolver | `pnpm vitest run src/features/alertas/__tests__/AlertasPanel.test.tsx` | vitest + RTL | revert `components/AlertasPanel.tsx` + `features/alertas/components/*` |
| WU-4 (C4) | Mount `<AlertasPanel />` in shell + i18n keys (es-CO/en-US/pt-BR) | `pnpm lint && pnpm tsc -p tsconfig.renderer.json --noEmit` | renderer typecheck | revert App.tsx mount + i18n JSON deltas |
| WU-5 (C5) | Playwright e2e S1-S4 + testcontainers Postgres backend assertion | `pnpm playwright test e2e/alertas-panel.spec.ts` | playwright + testcontainers | delete `e2e/alertas-panel.spec.ts` |
| WU-6 (C6) | Delete F11.1 stub at `features/sync/components/AlertasPanel.tsx:17` and `useSyncEstado.ts:90-146` | `pnpm lint && pnpm tsc -p tsconfig.renderer.json --noEmit` | renderer typecheck | restore F11.1 stub files via git revert |
| WU-7 (C7) | Verify `pending-fase-11.md` row + create ABBC-F11.2-BE-1 entry | n/a (docs) | n/a | revert doc commit |

## Commit plan (final order)

### C1 (RED scaffold)

- **Goal**: Land RED tests that fail before any source change.
- **Files created**:
  - `apps/electron-sucursal/src/features/alertas/__tests__/AlertaSchema.test.ts` (~80 LOC) — 4 Zod scenarios (canonical state accepted, legacy `abierta` rejected, unknown field rejected, `datos_nuevos` optional)
  - `apps/electron-sucursal/src/features/alertas/__tests__/useAlertas.test.ts` (~120 LOC) — 5 SWR scenarios (30 s polling cadence, 401 cleanup, `alert_types` merge, `openAlertsCount` selector, parallel fetch)
  - `apps/electron-sucursal/src/features/alertas/__tests__/AlertasPanel.test.tsx` (~150 LOC) — 5 render scenarios (11 visible + 8 dropped, filter chips toggle without `parkosFetch`, drill-down navigation, resolver click, error state)
- **Verification**: `pnpm vitest run src/features/alertas/ src/lib/api/schemas/alertas.ts` MUST exit non-zero with 14 failures.
- **Closes drift anchors**: DA-F11.2-11 (RED bootstrap mandated).
- **Resolves spec rows**: REQ-OPS-177, REQ-OPS-178, REQ-OPS-179, REQ-OPS-180, REQ-OPS-181, REQ-OPS-182, REQ-OPS-183 RED side.

### C2 (GREEN schemas + hooks)

- **Goal**: Implement the Zod schema + canonical state enum + SWR hook with parallel fetches, client-side merge, and `openAlertsCount` derived selector.
- **Files created**:
  - `apps/electron-sucursal/src/lib/api/schemas/alertas.ts` (~80 LOC) — `AlertaSchema` (18 fields + canonical enum + `datos_nuevos` optional + `strict()`) + `AlertTypeSchema` + `AlertaReadListSchema`
  - `apps/electron-sucursal/src/features/alertas/types.ts` (~30 LOC) — TS types from `z.infer<typeof AlertaSchema>`
  - `apps/electron-sucursal/src/features/alertas/constants.ts` (~30 LOC) — `BUSINESS_ALERT_CODES` (11 entries from `plan.md:2311-2323`) + `TECHNICAL_ALERT_CODES` (8 entries)
  - `apps/electron-sucursal/src/features/alertas/hooks/useAlertas.ts` (~120 LOC) — two `useSWR` calls with `Promise.all` semantics + derived `mergedAlertas` + `openAlertsCount`
  - `apps/electron-sucursal/src/features/alertas/hooks/useResolverAlerta.ts` (~80 LOC) — POST `/workflows/alerta` with `{ uuid_alerta_padre, estado: 'resuelta', ... }` + SWR cache invalidate + typed toast on 403
  - `apps/electron-sucursal/src/features/alertas/__tests__/constants.test.ts` (~40 LOC) — O(1) `Set.has` perf sanity + 11/8 counts
  - `apps/electron-sucursal/src/features/alertas/__tests__/useResolverAlerta.test.ts` (~80 LOC) — append-only POST, SWR invalidate, 403 toast, no PUT/PATCH
- **Verification**: `pnpm vitest run src/features/alertas/ src/lib/api/schemas/alertas.ts` MUST exit 0 with all 21 tests GREEN.
- **Closes drift anchors**: DA-F11.2-1 (18 fields codified), DA-F11.2-5 (whitelist), DA-F11.2-6 (30 s polling), DA-F11.2-7 (derived selector), DA-F11.2-9 (canonical enum), DA-F11.2-10 (path b client-side merge), DA-F11.2-13 (resuelta bypass), DA-F11.2-14 (`datos_nuevos` optional).
- **Resolves spec rows**: REQ-OPS-177, REQ-OPS-179, REQ-OPS-180, REQ-OPS-181, REQ-OPS-182 production side.

### C3 (GREEN panel + components)

- **Goal**: Promote F11.1 `<AlertasPanel />` stub to production with 4 composed sub-components and the drill-down router.
- **Files created**:
  - `apps/electron-sucursal/src/lib/alertas/router.ts` (~50 LOC) — `DRILL_DOWN_ROUTES: Record<TipoAlerta, (alert) => string>` keyed by 11 business codes; `datos_nuevos.uuid_ingreso` for `capacidad_agotada_forzado`
  - `apps/electron-sucursal/src/features/alertas/components/AlertaCard.tsx` (~80 LOC) — severity badge + mensaje + drill-down button + resolver button
  - `apps/electron-sucursal/src/features/alertas/components/AlertaFilterChips.tsx` (~60 LOC) — severity + tipo_alerta chips with `aria-pressed`
  - `apps/electron-sucursal/src/features/alertas/components/DrillDownButton.tsx` (~50 LOC) — reads from `lib/alertas/router.ts` + `useNavigate`
  - `apps/electron-sucursal/src/features/alertas/components/ResolverAlertaButton.tsx` (~70 LOC) — calls `useResolverAlerta().resolve(alert)` + optimistic UI disabled
  - `apps/electron-sucursal/src/features/alertas/__tests__/AlertaCard.test.tsx` (~80 LOC) — severity badge color; drill-down routes; resolver click
  - `apps/electron-sucursal/src/features/alertas/__tests__/AlertaFilterChips.test.tsx` (~60 LOC) — chip toggles filter without re-fetch; `aria-pressed`
- **Files modified**:
  - `apps/electron-sucursal/src/components/AlertasPanel.tsx` (~120 LOC, MODIFY/rewrite) — orchestrator: SWR hook + filters + list + empty state + axe-core role structure
- **Verification**: `pnpm vitest run src/features/alertas/__tests__/AlertasPanel.test.tsx` MUST exit 0 with 5 render tests GREEN; full `pnpm vitest run src/features/alertas/` MUST show 0 failures across all RED→GREEN files.
- **Closes drift anchors**: DA-F11.2-2 (POST path), DA-F11.2-3 (client-side chips), DA-F11.2-4 (router map), DA-F11.2-8 (e2e backend assertion hookup in S3).
- **Resolves spec rows**: REQ-OPS-178, REQ-OPS-181 production UI side.

### C4 (mount + i18n)

- **Goal**: Mount `<AlertasPanel />` in App.tsx and add i18n keys for descriptions, severities, actions, and empty state across es-CO/en-US/pt-BR.
- **Files modified**:
  - `apps/electron-sucursal/src/renderer/App.tsx` — add `<AlertasPanel />` mount (side-drawer via `<Sheet>` OR dedicated route `/alertas`; whichever fits shell composition; design AD-2 precedent is banner-style mount in `<StatusBar>` / `<AppShell>`)
  - `apps/electron-sucursal/src/renderer/i18n/locales/es-CO.json` — add `alertas.desc.*` (11 entries), `alertas.severidad.{alta,media,baja}`, `alertas.actions.marcarRevisada`, `alertas.empty.noAlerts`, `alertas.panel.title`
  - `apps/electron-sucursal/src/renderer/i18n/locales/en-US.json` — same keys, English copy
  - `apps/electron-sucursal/src/renderer/i18n/locales/pt-BR.json` — same keys, Brazilian Portuguese copy
- **Verification**: `pnpm lint && pnpm tsc -p tsconfig.renderer.json --noEmit` MUST exit 0; `pnpm vitest run src/features/alertas/` MUST remain GREEN.
- **Closes drift anchors**: n/a (no new drift; integration only).
- **Resolves spec rows**: REQ-OPS-178 mount, REQ-OPS-182 i18n empty-state copy.

### C5 (e2e + apply-progress)

- **Goal**: Ship Playwright e2e S1-S4 with testcontainers Postgres backend assertion for S3, plus the apply-progress tracker.
- **Files created**:
  - `apps/electron-sucursal/e2e/alertas-panel.spec.ts` (~150 LOC) — 4 scenarios:
    - **S1** (no skip): 11 visibles + filterable — mocks `/workflows/alerta` to return 11 business alerts spanning 3 severidades; asserts `<ul>` has 11 `<li>`; clicks `severidad=alta` chip and asserts 3 `<li>` with `data-severidad="alta"`
    - **S2** (no skip): drill-down per router map — mocks `descuadre_critico` with `uuid_arqueo: Y`; clicks drill-down; asserts `page.url()` ends with `/caja/arqueo/Y`; repeats for `capacidad_agotada_forzado` using `datos_nuevos.uuid_ingreso`
    - **S3** (no skip): resolver backend state — mocks POST 200 with `{ uuid: B, uuid_alerta_padre: A, estado: 'resuelta' }`; clicks resolver; queries testcontainers `prod.alerta WHERE uuid_alerta_padre = 'A'` — asserts exactly 1 row with `estado='resuelta'`
    - **S4** (skip optional per F9.x precedent): 8 technical codes excluded — mocks 8 technical codes; asserts `<ul>` empty + `role="status"` empty-state copy + `console.error` NOT called
- **Files created by sdd-apply (not by sdd-tasks)**:
  - `openspec/changes/fase-11-2-alertas-panel/apply-progress.md` — implementation ledger populated by `sdd-apply` after each commit lands (per `config.yaml` `rules.tasks`)
- **Verification**: `pnpm playwright test e2e/alertas-panel.spec.ts` MUST exit 0 with S1/S2/S3 passing (S4 may be skipped); full `pnpm vitest run` MUST remain GREEN.
- **Closes drift anchors**: DA-F11.2-8 (backend assertion in S3), DA-F11.2-11 (e2e RED completed).
- **Resolves spec rows**: REQ-OPS-183 full coverage.

### C6 (delete F11.1 stub)

- **Goal**: Remove the F11.1 placeholder stub now that production code is wired and tests are GREEN.
- **Files deleted**:
  - `apps/electron-sucursal/src/features/sync/components/AlertasPanel.tsx` — F11.1 stub (placeholder `<ul>` only)
  - `apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.ts` lines 90-146 — `useAlertas`, `fetchAlertas`, `AlertaSchema`, `AlertaArraySchema`, `Alerta` type removed (replaced by `features/alertas/hooks/useAlertas.ts` + `lib/api/schemas/alertas.ts`)
- **Verification**: `pnpm lint && pnpm tsc -p tsconfig.renderer.json --noEmit && pnpm vitest run` MUST exit 0 (no broken imports, no stale references); `grep -r 'useSyncEstado.*useAlertas\|useSyncEstado.*AlertaSchema' apps/electron-sucursal/src/` MUST return empty.
- **Closes drift anchors**: DA-F11.2-12 (F11.1 stub deletion explicitly authorised in F11.1 verify-report R-F11.1-CARRY-2).
- **Resolves spec rows**: REQ-OPS-179 DELETE clause.

### C7 (housekeeping doc)

- **Goal**: Update `pending-fase-11.md` with F11.2 status and ABBC-F11.2-BE-1 entry.
- **Files modified**:
  - `openspec/changes/pending-fase-11.md` — mark F11.2 row as `DONE`; append ABBC-F11.2-BE-1 entry (backend delta: extend `AlertaRead` with JOIN to `alert_types` returning `severidad`, `descripcion`, `mensaje`; removes R-RES-F11.2-1 stale-merge risk)
- **Verification**: `grep -A3 'ABBC-F11.2-BE-1' openspec/changes/pending-fase-11.md` MUST show the entry.
- **Closes drift anchors**: n/a (backlog filing).
- **Resolves spec rows**: forward hooks section (ABBC-F11.2-BE-1 filed).

## Drift-anchor verification checklist

| Drift anchor | Severity | Resolved by commit | Verification |
|---|---|---|---|
| DA-F11.2-1 | High | C2 | 18 BE fields codified in `lib/api/schemas/alertas.ts`; RED test `AlertaSchema.test.ts` parses real BE row |
| DA-F11.2-2 | High | C2 + C3 | `useResolverAlerta` POSTs to `/workflows/alerta`; RED test mocks POST 200 + asserts SWR cache invalidate |
| DA-F11.2-3 | Med | C3 | `<AlertaFilterChips>` client-side only; RED test asserts no `parkosFetch` call on chip click |
| DA-F11.2-4 | Med | C3 | `lib/alertas/router.ts` map; RED test for `AlertaCard` exercises `descuadre_critico` → `/caja/arqueo/{uuid_arqueo}` |
| DA-F11.2-5 | Med | C2 | `constants.ts` whitelist Set; RED test for `useAlertas` mocks 19 rows and asserts mergedAlertas has 11 |
| DA-F11.2-6 | Low | C2 | `refreshInterval: 30_000` in `useSWR` config; RED test advances `vi.useFakeTimers` 30 s and asserts 1 re-fetch |
| DA-F11.2-7 | Low | C2 | `openAlertsCount` derived selector; RED test asserts `5` for 11 alerts (5 activa + 6 resuelta) |
| DA-F11.2-8 | Low | C5 | e2e S3 queries testcontainers `prod.alerta`; assertion `count(*) WHERE uuid_alerta_padre = 'A'` MUST equal 1 |
| **DA-F11.2-9** | **GATING** | C2 + C6 | Zod enum `z.enum(['activa','descartada','resuelta'])`; query param `?estado=activa`; F11.1 stub legacy deleted in C6 |
| **DA-F11.2-10** | **High** | C2 + C7 | Two `useSWR` calls + client-side merge in `useAlertas`; ABBC-F11.2-BE-1 filed in `pending-fase-11.md` via C7 |
| DA-F11.2-11 | High | C1 + C5 | RED tests land in C1 (unit + RTL); e2e RED lands in C5 (S1-S4) |
| DA-F11.2-12 | Med | C6 | F11.1 stub at `features/sync/components/AlertasPanel.tsx:17` deleted in C6 (R-F11.1-CARRY-2 authorised) |
| DA-F11.2-13 | Med | C2 | `useResolverAlerta.test.ts` asserts payload is `{ estado: 'resuelta' }` (never `'descartada'`); actor-check happy-path triple-checked |
| DA-F11.2-14 | Med | C2 + C3 | `AlertaSchema` declares `datos_nuevos: z.record(z.unknown()).nullable().optional()`; `router.ts` `capacidad_agotada_forzado` reads `datos_nuevos.uuid_ingreso`; RED test for both |
| **ABBC-F11.2-BE-1** | Backlog | C7 | Entry appended to `openspec/changes/pending-fase-11.md` (backend JOIN follow-up; out of F11.2 scope) |

## Test commands summary (in order)

```bash
cd apps/electron-sucursal && pnpm lint
cd apps/electron-sucursal && pnpm tsc -p tsconfig.renderer.json --noEmit
cd apps/electron-sucursal && pnpm vitest run src/features/alertas/ src/lib/api/schemas/alertas.ts tests
cd apps/electron-sucursal && pnpm vitest run
cd apps/electron-sucursal && pnpm playwright test e2e/alertas-panel.spec.ts
```

Per-commit expected gate:

| Commit | C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|---|---|---|---|---|---|---|---|
| `pnpm lint` | n/a | optional | optional | required | optional | required | n/a |
| `pnpm tsc -p tsconfig.renderer.json --noEmit` | n/a | optional | optional | required | optional | required | n/a |
| `pnpm vitest run src/features/alertas/ src/lib/api/schemas/alertas.ts tests` | RED (14 fails) | GREEN (21 pass) | n/a | n/a | n/a | n/a | n/a |
| `pnpm vitest run` | n/a | optional | required | required | required | required | n/a |
| `pnpm playwright test e2e/alertas-panel.spec.ts` | n/a | n/a | n/a | n/a | required | n/a | n/a |

## Plain-text guard lines

```
Decision: single-pr
Chained PRs: No
Chain strategy: n/a
Delivery strategy: ask-on-risk
Size exception: No (forecast 1530 ≤ 2000 baseline)
Review budget risk: Med
Review budget hard limit: 2000 lines (meta-budget ratified)
Forecast ~1530 LOC actual
```

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1530 |
| 800-line budget risk | High |
| 2000-line baseline risk | Low |
| Chained PRs recommended | No |
| Size exception needed | No |
| Decision needed before apply | No |

## Open decisions

None. D1..D7 are resolved by the design (7 ADs). The 14 drift anchors are all closed by the spec drift reconciliation table (DA-F11.2-9 GATING resolved in REQ-OPS-177 + REQ-OPS-180; DA-F11.2-10 HIGH resolved path-b in REQ-OPS-179 with ABBC-F11.2-BE-1 backend follow-up filed). F11.1 carry-overs (R-CARRY-1, REQ-OPS-173, R-F11.1-CARRY-2) reconciled in spec delta appendix. The four F11.2-spec `Open Questions` from the proposal are answered by the spec (AlertaRead has 18 fields not JOIN — path b; POST reuses create path at `/workflows/alerta`; `datos_nuevos` is `.optional()` today; F11.1 stub is placeholder per design inspection).

## Risk acknowledgements

| ID | Severity | Mitigation |
|---|---|---|
| R-RES-F11.2-1 | MED | FE `/workflows/alert-types` SWR (5 min refresh) may return a different version than `/workflows/alerta` (30 s refresh) on a hot-deploy. Stale `severidad` for ~5 min is acceptable. ABBC-F11.2-BE-1 (backend JOIN) removes this risk permanently. |
| R-RES-F11.2-2 | LOW | `<AlertasPanel />` rewrite replaces F11.1 stub — Risk R-F11.1-CARRY-2 (F11.1 verify-report) explicitly authorised this. No rollback concerns since stub never shipped. |
| R-RES-F11.2-3 | LOW | REQ-26 actor check on `descartada` will throw 403 in the resolver flow IF the operator attempts `descartada` self-redirect (not exercised in F11.2 — F11.2 only emits `resuelta`). Verified in `useResolverAlerta.test.ts` that the happy-path payload is `{ estado: "resuelta" }`. |
| R-RES-F11.2-4 | LOW | `datos_nuevos` JSONB column is currently absent on the BE `AlertaRead` contract (DA-F11.2-14 — speculative). The schema declares `.optional()` so parse succeeds today; ABIERTO-07 (filed in `pending-fase-11.md`) tracks the BE-side addition. |
| DA-F11.2-9 | GATING | Zod enum aligned to BE Pydantic `Literal["activa", "descartada", "resuelta"]`; legacy `abierta`/`cerrada` forbidden. F11.1 stub deleted in C6. |
| DA-F11.2-10 | High | Client-side merge via `/workflows/alert-types` SWR (path b). Path (a) — backend `AlertaRead` JOIN — flagged as ABBC-F11.2-BE-1 in `pending-fase-11.md` for follow-up. |
| DA-F11.2-11 | High | Strict-TDD: 14 RED tests land in C1 before any source change; 4 e2e scenarios land in C5. |
| DA-F11.2-12 | Med | F11.1 stub at `features/sync/components/AlertasPanel.tsx:17` deleted in C6 (R-F11.1-CARRY-2 authorised rewrite). |