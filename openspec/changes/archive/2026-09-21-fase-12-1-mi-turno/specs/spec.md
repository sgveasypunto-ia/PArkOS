# Delta for operations — F12.1 "Mi turno" (per-turn KPI panel)

## Header

| Field | Value |
|---|---|
| Change | `fase-12-1-mi-turno` |
| Phase | 12 |
| Base spec | `openspec/specs/operations/spec.md` (last entry REQ-OPS-183 from F11.2) |
| Gap | No per-turn live KPI; F10.2 only aggregates at cierre |
| Preflight | pace=auto, hybrid, review_budget=2000, strict_tdd, git_author=`Parkos Dev <dev@parkos.local>` |
| Substrate verified | ORM `models/L_E/ingreso.py`, `models/A/salidas.py`, `models/L_S/sesion.py`; SUM helper `repo/arqueo.py::_sum_factura_pagos_by_medio_pago`; router `api/v1/operacion.py` (no `/mi-turno` stub); FE `Dashboard.tsx`, `OcupacionPanel.tsx`, `useSesionActiva.ts` |

## ADDED Requirements

### Requirement: REQ-OPS-184 — `GET /operacion/mi-turno?uuid_sesion=X` response shape

The system MUST return `MiTurnoRead` JSON with exactly 7 fields: `uuid_sesion: UUID`, `uuid_sucursal: UUID`, `timestamp_calculo: datetime`, `ingresos_count: int`, `salidas_count: int`, `total_cobrado_efectivo_cop: Decimal`, `total_cobrado_datafono_cop: Decimal`. All count/decimal fields MUST default to `0`. The response MUST carry `Cache-Control: no-store`. The handler MUST be appended to the existing `api/v1/operacion.py` router (NOT a new router file).

#### Scenario: Happy path — active session with mixed activity

- GIVEN an open `Sesion` X (timestamp_apertura=t0, timestamp_cierre IS NULL), 3 ingreso rows with `fecha_ingreso BETWEEN t0 AND NOW()`, 2 salidas rows with `fecha_salida BETWEEN t0 AND NOW()`, and `factura_pagos` rows for `uuid_sesion=X` totaling 50000 efectivo + 30000 datafono
- WHEN client sends `GET /operacion/mi-turno?uuid_sesion=X`
- THEN response is 200 with `ingresos_count=3`, `salidas_count=2`, `total_cobrado_efectivo_cop=50000`, `total_cobrado_datafono_cop=30000`, and `Cache-Control: no-store`

#### Scenario: Zero state — no events in window

- GIVEN an open `Sesion` X with no ingreso/salida/factura_pagos events in its window
- WHEN client sends `GET /operacion/mi-turno?uuid_sesion=X`
- THEN response is 200 with all count/decimal fields equal to `0` (NOT 404, NOT error)

### Requirement: REQ-OPS-185 — Tenant pin enforcement (DA-F12.1-2)

The handler MUST resolve `Sesion.uuid_sucursal` server-side via a SELECT keyed by `uuid_sesion` and reject with HTTP 403 `sesion_cross_branch_forbidden` when the resolved `uuid_sucursal` does NOT match the JWT issuer's pinned `ctx.sucursal_uuid` (operator scope). The handler MUST NOT trust any `uuid_sucursal` field on the query string or body (none is accepted).

#### Scenario: Cross-branch uuid_sesion rejected

- GIVEN operator JWT pinned to `uuid_sucursal=A`; request `uuid_sesion=S` whose `Sesion.uuid_sucursal=B`
- WHEN handler resolves session
- THEN response is 403 with error code `sesion_cross_branch_forbidden`

#### Scenario: Unknown uuid_sesion rejected

- GIVEN request `uuid_sesion=S` that does not exist in `prod.sesion`
- WHEN handler runs
- THEN response is 404 with error code `sesion_not_found`

### Requirement: REQ-OPS-186 — SQL aggregation strategy via Sesion open-window JOIN (DA-F12.1-10)

The backend MUST compute counts via `Sesion` open-window temporal JOIN (NOT via a `uuid_sesion` FK on ingreso/salidas — that column does not exist and MUST NOT be added; ER.mmd forbids mutating `[L-E]`/`[A]` bi-temporal tables). The derived branch scope `S_s` MUST equal the resolved `Sesion.uuid_sucursal` (per REQ-OPS-185).

- `ingresos_count = SELECT COUNT(*) FROM prod.ingreso WHERE uuid_sucursal = S_s AND fecha_ingreso >= S.timestamp_apertura AND (S.timestamp_cierre IS NULL OR fecha_ingreso <= S.timestamp_cierre)`
- `salidas_count = SELECT COUNT(*) FROM prod.salidas WHERE uuid_sucursal = S_s AND fecha_salida >= S.timestamp_apertura AND (S.timestamp_cierre IS NULL OR fecha_salida <= S.timestamp_cierre)`
- `total_cobrado_{efectivo,datafono}_cop` MUST reuse `repo/arqueo.py::_sum_factura_pagos_by_medio_pago(session, uuid_sesion=S, medios_pago=(...))` with the canonical medio_pago filter tuple per design (one tuple for efectivo, one for datafono; no new SUM helper).

#### Scenario: Closed-session window excludes post-turn events

- GIVEN Sesion X opened at t0, closed at t1; 5 ingreso rows: 3 with `fecha_ingreso < t1` (inside window), 2 with `fecha_ingreso > t1` (post-turn)
- WHEN handler aggregates
- THEN `ingresos_count = 3`; the 2 post-turn rows are excluded by the `fecha_ingreso <= S.timestamp_cierre` predicate

### Requirement: REQ-OPS-187 — `<MiTurnoPanel />` mount and Cerrar-turno button (DA-F12.1-4, DA-F12.1-5)

The frontend MUST mount `<MiTurnoPanel uuid_sesion={sesion?.uuid} />` inside `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` right sidebar, ABOVE the existing `<OcupacionPanel />`. The component MUST render a shadcn `Card` strip with 5 KPI cells (ingresos / salidas / total_cobrado / efectivo / datafono) and a footer `Button` labeled `miTurno.cerrarTurno` whose `onClick` calls `navigate('/caja/cerrar-turno')` only. The button MUST NOT call `useSesionActiva().cerrarSesion` directly (that is F10.2's responsibility). When `uuid_sesion` is `null`, the panel MUST render all-zero KPIs without skeleton or error.

#### Scenario: Panel appears after active session

- GIVEN operator opens turno via `AbrirTurno`
- WHEN `Dashboard` mounts
- THEN `<MiTurnoPanel />` renders above `<OcupacionPanel />` with current KPI values

#### Scenario: Cerrar-turno navigates only

- GIVEN `<MiTurnoPanel />` rendered with active session
- WHEN operator clicks the footer button
- THEN router navigates to `/caja/cerrar-turno`; NO `cerrarSesion` PUT or `arqueo` POST is issued by this component

### Requirement: REQ-OPS-188 — `useMiTurno` SWR hook (DA-F12.1-3)

The hook MUST use `useSWR` with `key = uuid_sesion && accessToken ? '/api/v1/operacion/mi-turno?uuid_sesion=' + uuid_sesion : null`, `refreshInterval: 15_000`, `dedupingInterval: 5_000`, `shouldRetryOnError` excluding 401/403/404, and `onError` triggering `useAuthStore.getState().clear()` + `window.dispatchEvent(new Event('parkos:auth:cleared'))` on 401. The hook MUST parse the response through `MiTurnoSchema` (Zod) before returning. The hook MUST render the zero state (`data === undefined`) without skeleton or error UI; the panel displays `0` for every KPI.

#### Scenario: 15s polling cadence

- GIVEN `uuid_sesion` non-null and access token present
- WHEN hook mounts
- THEN first fetch fires immediately; subsequent revalidations fire every 15s ± 5s deduping

#### Scenario: 401 mid-polling

- GIVEN hook is actively polling
- WHEN server returns 401
- THEN hook stops polling, auth store clears, `parkos:auth:cleared` event fires (F2.2 invariant)

### Requirement: REQ-OPS-189 — FE Zod schema matches BE Pydantic (DA-F12.1-1, DA-F12.1-9)

`apps/electron-sucursal/src/features/operacion/api/miTurnoApi.ts` MUST export `MiTurnoSchema = z.object({ uuid_sesion: z.string().uuid(), uuid_sucursal: z.string().uuid(), timestamp_calculo: z.string(), ingresos_count: z.number().int().nonnegative(), salidas_count: z.number().int().nonnegative(), total_cobrado_efectivo_cop: z.number().nonnegative(), total_cobrado_datafono_cop: z.number().nonnegative() })`. Field names MUST match the backend Pydantic `MiTurnoRead` exactly (snake_case verbatim, NOT camelCase). A static test MUST compare the Zod key set against the Pydantic key set and fail on mismatch.

#### Scenario: Schema drift caught at parse time

- GIVEN backend adds a new field to `MiTurnoRead`
- WHEN Zod parses a response missing the new field
- THEN `ZodError` is thrown; hook returns `error`; panel renders fallback (not crash)

### Requirement: REQ-OPS-190 — Test coverage contract (DA-F12.1-8)

Backend MUST ship pytest unit + integration tests against testcontainers Postgres, using a new `sesion_with_ingresos_y_pagos` factory fixture in `tests/integration/conftest.py` (per F1.13 pattern: seeds 1 Sesion + 2 ingreso + 1 salida + 3 factura_pagos). Frontend MUST ship vitest unit tests for `<MiTurnoPanel />` (loading / zero / non-zero / 401 / 5xx / polling scenarios) and Playwright e2e `apps/electron-sucursal/e2e/mi-turno.spec.ts` with 2 scenarios marked `test.skip(...)` per F10.2/F11.x sandbox F.6 precedent.

#### Scenario: Backend pytest covers all branches

- GIVEN the new `calcular_resumen_mi_turno` helper
- WHEN pytest runs against testcontainers Postgres
- THEN ≥10 scenarios pass: happy path, zero state, cross-branch 403, closed-session window, medio_pago breakdown, missing sesion 404, multi-pago medio_pago mix, plus ≥4 negative paths

#### Scenario: FE e2e marked test.skip in sandbox

- GIVEN Playwright runner in sandbox F.6 environment (real Electron cannot launch)
- WHEN `e2e/mi-turno.spec.ts` runs
- THEN both scenarios log "skip reason: sandbox F.6" and exit `0` without browser launch

## Drift reconciliation

| Anchor | Status | Resolution |
|---|---|---|
| DA-F12.1-1 (BE/FE schema match) | RESOLVED | REQ-OPS-184 (BE 7-field Pydantic) + REQ-OPS-189 (FE Zod) lock the wire shape; snake_case verbatim |
| DA-F12.1-2 (tenant pin) | RESOLVED | REQ-OPS-185 codifies lookup-then-403 via `Sesion.uuid_sucursal` server-side resolution |
| DA-F12.1-3 (polling cadence 15s) | RESOLVED | REQ-OPS-188: `refreshInterval: 15_000`, `dedupingInterval: 5_000`; design AD-3 justifies vs F11.x 30s as operator-live turn metrics |
| DA-F12.1-4 (zero-state) | RESOLVED | REQ-OPS-184 (BE always 200 + zeros) + REQ-OPS-188 (FE renders 0, no skeleton/error) |
| DA-F12.1-5 (Cerrar-turno button reuse) | RESOLVED | REQ-OPS-187: button calls `navigate()` only; F10.2 owns close logic |
| DA-F12.1-6 (backend stub) | RESOLVED | Extend `api/v1/operacion.py` (no new router); no existing `/mi-turno` route confirmed via codegraph |
| DA-F12.1-7 (i18n keys) | RESOLVED | Add to `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (es-CO only): `miTurno.titulo`, `miTurno.kpis.{ingresos,salidas,totalCobrado,efectivo,datafono}`, `miTurno.cerrarTurno` |
| DA-F12.1-8 (test fixture) | RESOLVED | REQ-OPS-190: add `sesion_with_ingresos_y_pagos` factory fixture to `tests/integration/conftest.py` |
| DA-F12.1-9 (FE/BE drift) | RESOLVED | REQ-OPS-189 + static key-set comparison test |
| DA-F12.1-10 (no uuid_sesion on ingreso/salidas) | RESOLVED | REQ-OPS-186 codifies Sesion open-window temporal JOIN using `fecha_ingreso` / `fecha_salida`; ORM verified at `models/L_E/ingreso.py:46-49` and `models/A/salidas.py:65-68` |

## Validation matrix

| Layer | Validator | Threshold |
|---|---|---|
| BE unit + integration | `pytest backend/tests` with testcontainers | ≥10 scenarios green; coverage ≥80% on `repo/mi_turno.py` |
| BE lint | `ruff check` + `mypy --strict` | 0 errors |
| FE unit | `pnpm --filter @apps/electron-sucursal vitest run` | ≥6 scenarios green (loading/zero/non-zero/401/5xx/polling) |
| FE types + lint | `tsc --noEmit` + `eslint` | 0 errors |
| e2e | `playwright test e2e/mi-turno.spec.ts` | 2 scenarios `test.skip` exit `0` |
| a11y | `@axe-core/playwright` on Dashboard | 0 WCAG 2.1 AA violations on `<MiTurnoPanel />` |
| schema drift | `python openspec/scripts/check_schema_match.py` | exits `0`; no migration needed (read-only aggregator) |

## Risk acknowledgements

- **R-F12.1-1** — `prod.ingreso` (L-E) and `prod.salidas` (A) lack `uuid_sesion`. F12.1 MUST NOT add the column — would mutate bi-temporal canon; ER.mmd forbids. Resolution: open-window temporal JOIN (REQ-OPS-186).
- **R-F12.1-2** — `_sum_factura_pagos_by_medio_pago` is the canonical SUM helper (F1.13); F12.1 reuses it via the `medios_pago` tuple argument. No new SUM helper introduced.
- **R-F12.1-3** — Sandbox F.6 limitation: Playwright cannot launch real Electron. e2e marked `test.skip` per F10.2/F11.x precedent; vitest unit tests cover the same surface.
- **R-F12.1-4** — Polling at 15s (vs F11.x 30s) increases DB load by ~2x on `factura_pagos` SUM. Mitigation: SUM helper already uses `coalesce(sum, 0)` and the `prod.sesion` partial unique index keeps cardinality to 1 active session per operator.

## F11.x carry-overs reconciliation appendix

- **R-CARRY-1 (thresholds)** — F12.1 has no occupancy thresholds (no inventory logic — that's `<OcupacionPanel />` / F4.3). Inherited F11.1/F11.2 thresholds carry forward without modification.
- **REQ-OPS-173 letter (F11.1)** — unchanged. F12.1 adds REQ-OPS-184..190; REQ-OPS-173 is untouched.
- **F11.2 carryover REQ-OPS-177..183** — unchanged. F12.1 deltas the `operations` domain; F11.2 entries remain authoritative until F12.1 archives.
