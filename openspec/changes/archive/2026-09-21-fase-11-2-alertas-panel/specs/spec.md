# Delta Spec: `operations` — Fase 11.2 Alertas Panel

## Header

| Field | Value |
|---|---|
| Change | `fase-11-2-alertas-panel` |
| Phase | Fase 11 — Operational telemetry and alerts (HU-F11.2 of 2) |
| Base spec | `openspec/specs/operations/spec.md` (last REQ-OPS-176 from F11.1) |
| Gap | Branch operators blind to 11 business alerts (`descuadre_critico`, `fe_error_toppoint`, `numeracion_toppoint_agotada`, etc.); F11.1 scaffolded `AlertasPanel` + `useAlertas` stub but never shipped. |
| Preflight | pace=auto, artifact=hybrid (OpenSpec + Engram), delivery=ask-on-risk, budget=2000 LOC (Fase 11+ meta-budget), strict_tdd=true, test=vitest+playwright, author=`Parkos Dev <dev@parkos.local>`. |
| Status | DELTA — 7 ADDED requirements (REQ-OPS-177..183). GATING anchors DA-F11.2-9 + DA-F11.2-10 RESOLVED in this spec. |

## Drift Anchors Resolved in This Spec

| Anchor | Severity | Resolution |
|---|---|---|
| DA-F11.2-9 | **GATING** — state vocabulary drift | RESOLVED. BE `AlertaCreate.estado: Literal["activa", "descartada", "resuelta"]` (`schemas/workflows.py:377`) is the canonical enum (AGENTS.md §API contract canon). FE `AlertaSchema` MUST align to this enum; query param MUST be `?estado=activa`. Codified in REQ-OPS-177 + REQ-OPS-180. |
| DA-F11.2-10 | **HIGH** — no JOIN in `AlertaRead` | RESOLVED — path (b). BE `AlertaRead` returns 18 fields, NONE of which are `severidad` / `descripcion` / `mensaje` (those live on `alert_types`). F11.2 ships a SECOND SWR query against `GET /workflows/alert-types` and merges client-side (REQ-OPS-179). Path (a) — backend delta extending `AlertaRead` with a JOIN to `alert_types` — is flagged as **ABBC-F11.2-BE-1** in `pending-fase-11.md` for follow-up. |

## ADDED Requirements

### REQ-OPS-177 — `GET /api/v1/workflows/alerta` response shape + canonical state vocabulary (DA-F11.2-9)

The client-side contract for `GET /api/v1/workflows/alerta?uuid_sucursal=X&estado=activa` MUST be the exact set of 18 fields emitted by backend `AlertaRead` Pydantic schema at `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py:328-353`:

| # | Field | Type |
|---|-------|------|
| 1 | `uuid` | UUID |
| 2 | `fecha_retencion_hasta` | date |
| 3 | `created_at` | datetime |
| 4 | `created_by` | UUID \| null |
| 5 | `sync_status` | str \| null |
| 6 | `sync_timestamp` | datetime \| null |
| 7 | `sync_attempts` | int \| null |
| 8 | `uuid_sucursal` | UUID \| null |
| 9 | `uuid_usuario` | UUID \| null |
| 10 | `uuid_arqueo` | UUID \| null |
| 11 | `tipo_alerta` | str \| null |
| 12 | `valor_diferencia_efectivo` | Decimal \| null |
| 13 | `valor_diferencia_datafono` | Decimal \| null |
| 14 | `uuid_alerta_padre` | UUID \| null |
| 15 | `timestamp_evento` | datetime \| null |
| 16 | `vigente_desde` | datetime \| null |
| 17 | `vigente_hasta` | datetime \| null |
| 18 | `estado` | `Literal["activa", "descartada", "resuelta"]` \| null |

The query parameter `estado` MUST be exactly `activa` (open alerts in business terms). The legacy vocabularies `abierta` / `cerrada` are NOT permitted at any layer (F11.1 stub will be deleted). The endpoint MUST NOT include `severidad`, `descripcion`, or `mensaje` (those live on `alert_types` and are merged client-side per REQ-OPS-179).

#### Scenario: Parses real backend response shape

- GIVEN an `operador-` JWT with `ctx.sucursal_uuid = X`
- WHEN the FE calls `GET /api/v1/workflows/alerta?uuid_sucursal=X&estado=activa` and receives `{ "uuid": "...", "uuid_sucursal": "X", "tipo_alerta": "descuadre_critico", "estado": "activa", ... }`
- THEN `AlertaSchema.parse(body)` MUST succeed
- AND the parsed object MUST carry `estado === "activa"` (NOT `"abierta"`).

#### Scenario: Query parameter accepts canonical values only

- GIVEN the FE calls the endpoint with `?estado=abierta`
- WHEN the request reaches the handler
- THEN the handler MUST return `400 Bad Request` with body `{"error": "estado_invalido"}` (legacy vocabulary rejected; canonical is `activa | descartada | resuelta`).

#### Scenario: Endpoint surfaces 18 fields, no display fields

- GIVEN a representative alert row
- WHEN the FE parses the response
- THEN the parsed object MUST NOT contain `severidad`, `descripcion`, or `mensaje` keys (those belong to the `alert_types` merge per REQ-OPS-179; their presence in the workflow response is a violation of the contract).

### REQ-OPS-178 — `<AlertasPanel />` list + filter chips + per-`tipo_alerta` drill-down router (DA-F11.2-4)

The `<AlertasPanel />` component (promoted from the F11.1 stub at `apps/electron-sucursal/src/features/sync/components/AlertasPanel.tsx:17`) MUST:

1. Render one `<AlertaCard>` per business alert in `useAlertas().data` (filtered through `BUSINESS_ALERT_CODES` per REQ-OPS-182).
2. Render `<AlertaFilterChips>` for client-side filtering by `severidad` (derived from `alert_types` merge) AND by `tipo_alerta` code (DA-F11.2-3 — no backend round-trip required; max ~19 alerts is trivial for client-side filtering).
3. Each `<AlertaCard>` MUST render a `<DrillDownButton>` whose target route is selected from the per-`tipo_alerta` router map at `lib/alertas/router.ts`:

| `tipo_alerta` (subset shown; full list canonical in constants) | Drill-down route | Reference field |
|---|---|---|
| `descuadre_critico` | `/caja/arqueo/{uuid_arqueo}` | `alert.uuid_arqueo` |
| `fe_error_toppoint` | `/facturacion/fe/{uuid}` | `alert.uuid` → FE lookup |
| `numeracion_toppoint_agotada` | `/admin/resoluciones` | none — admin link |
| `cache_desactualizado` | `/sync/detalle` | none |
| `capacidad_agotada_forzado` | `/caja/ingreso/{datos_nuevos.uuid_ingreso}` | `alert.datos_nuevos.uuid_ingreso` (JSONB; REQ-OPS-180) |
| (other 6 business codes) | `/alertas/{alert.uuid}` (default detail page) | none |

Each `<AlertaCard>` MUST render a `<ResolverAlertaButton>` per REQ-OPS-181.

#### Scenario: 11 business alerts render; 8 technical codes drop silently

- GIVEN `useAlertas.data` returns 11 rows whose `tipo_alerta` is in `BUSINESS_ALERT_CODES` and 8 rows whose `tipo_alerta` is technical (e.g. `hash_chain_anomaly`)
- WHEN `<AlertasPanel />` mounts
- THEN the rendered `<ul>` MUST contain exactly 11 `<li>` children
- AND the 8 technical codes MUST be dropped silently (DevTools `console.debug` log allowed per ABIERTO-06, NOT `console.error`).

#### Scenario: Filter chips toggle visibility client-side

- GIVEN `<AlertasPanel />` renders 11 alerts and the user clicks the `severidad=alta` chip
- WHEN the chip state updates
- THEN `<AlertasPanel />` MUST re-render with ONLY the `severidad=alta` subset (no `parkosFetch` re-validation triggered).

#### Scenario: Drill-down routes to source object per router map

- GIVEN an alert `{ tipo_alerta: "descuadre_critico", uuid_arqueo: "Y" }`
- WHEN the user clicks the drill-down button
- THEN `navigate("/caja/arqueo/Y")` MUST be invoked.

#### Scenario: Fallback for codes with no FK (`datos_nuevos` JSONB drill-down)

- GIVEN an alert `{ tipo_alerta: "capacidad_agotada_forzado", datos_nuevos: { uuid_ingreso: "Z" } }`
- WHEN the user clicks the drill-down button
- THEN `navigate("/caja/ingreso/Z")` MUST be invoked (DA-F11.2-14 — uses `datos_nuevos.uuid_ingreso` per the JSONB column).

### REQ-OPS-179 — `useAlertas` SWR hook + `alert_types` JOIN merge + derived `openAlertsCount` (DA-F11.2-10 path b, DA-F11.2-7)

`apps/electron-sucursal/src/features/alertas/hooks/useAlertas.ts` MUST be promoted from the F11.1 stub at `apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.ts:110`. The hook MUST:

1. Issue TWO independent SWR queries under one key namespace:
   - `useSWR(["/workflows/alerta", uuid_sucursal, "activa"], …)` — refreshInterval `30_000` (DA-F11.2-6; matches F11.1 SyncBanner precedent).
   - `useSWR(["/workflows/alert-types", uuid_sucursal], …)` — `refreshInterval: 300_000` (alert types change rarely; 5 min is sufficient).
2. Compose the JOIN client-side via a derived `mergedAlertas` selector: each alert row is enriched with `severidad`, `descripcion`, and `mensaje` from the matching `alert_types[tipo_alerta]` entry. Rows whose `tipo_alerta` is not present in `alert_types` MUST be excluded from `mergedAlertas` (defense — silent drop, not thrown, per ABIERTO-06).
3. Expose a derived `openAlertsCount` selector that returns `mergedAlertas.filter(a => a.estado === "activa" && BUSINESS_ALERT_CODES.has(a.tipo_alerta)).length` (DA-F11.2-7 — mirrors the `apiStatusStore`-derived selector pattern from F11.1 R-CARRY-1).
4. SWR key gate on `(uuid_sucursal && accessToken)` — `null` otherwise (REQ-OPS-132 fetcher-closure, F3.1 baseline).
5. On 401: clear `useAuthStore` + dispatch `parkos:auth:cleared` window event (verbatim F11.1 pattern from `SyncEstadoSchema` hook).

DELETE: `useAlertas`, `fetchAlertas`, `AlertaSchema`, `AlertaArraySchema`, `Alerta` type from `useSyncEstado.ts` (lines 90-146 of the F11.1 stub). Replace single import in `AlertasPanel.tsx` with `useAlertas` from the new module path.

#### Scenario: 30s polling matches F11.1 SyncBanner cadence

- GIVEN `useAlertas` is mounted with a valid `uuid_sucursal`
- WHEN `vi.useFakeTimers()` advances time by `30_000` ms
- THEN `parkosFetch` MUST be called once more for `/workflows/alerta` (matching F11.1 REQ-OPS-171 cadence).

#### Scenario: alert_types merge populates display fields

- GIVEN `/workflows/alerta` returns `[{ tipo_alerta: "descuadre_critico", ... }]` and `/workflows/alert-types` returns `[{ codigo: "descuadre_critico", severidad: "alta", descripcion: "...", mensaje: "..." }]`
- WHEN `useAlertas()` reads its derived `mergedAlertas` selector
- THEN the resulting array MUST carry `severidad: "alta"` and `mensaje: "..."` on the matching alert row.

#### Scenario: openAlertsCount counts only business alerts in `activa` state

- GIVEN `mergedAlertas` contains 11 business alerts (5 `estado: "activa"`, 6 `estado: "resuelta"`) and 8 technical codes
- WHEN the consumer reads `useAlertas().openAlertsCount`
- THEN the value MUST equal `5` (technical codes excluded by `BUSINESS_ALERT_CODES`, `resuelta` excluded by `estado === "activa"`).

### REQ-OPS-180 — `AlertaSchema` Zod enforces parity with `AlertaRead` + canonical state enum + `datos_nuevos` JSONB (DA-F11.2-1, DA-F11.2-9, DA-F11.2-14)

`AlertaSchema` (the FE schema that parses `GET /workflows/alerta` rows) MUST declare exactly the 18 fields from REQ-OPS-177, with the `estado` field constrained to `z.enum(['activa', 'descartada', 'resuelta'])` (canonical BE `Literal`, DA-F11.2-9 reconciled). The schema MUST `extra='forbid'`-equivalent reject any other field name at parse time (defense in depth against backend schema drift; precedent in F11.1 REQ-OPS-170).

The schema MUST additionally declare `datos_nuevos: z.record(z.unknown()).nullable().optional()` — this field is NOT exposed by `AlertaRead` today (DA-F11.2-14 is speculative until F11.2 lands); the field MUST be `.optional()` so the schema succeeds against the current BE response and gracefully picks up the column once the JOIN lands (ABBC-F11.2-BE-1 path a) OR once `datos_nuevos` is added to the canonical `AlertaRead`. The full backend reader-MUST-eventually-`datos_nuevos` hook is documented in the appendix.

#### Scenario: Schema rejects legacy `estado` enum

- GIVEN a row `{ ..., "estado": "abierta" }`
- WHEN `AlertaSchema.parse(row)` runs
- THEN `ZodError` MUST be raised (canonical is `activa`, not `abierta`).

#### Scenario: Schema accepts canonical state enum

- GIVEN a row `{ ..., "estado": "resuelta" }`
- WHEN `AlertaSchema.parse(row)` runs
- THEN the parsed object MUST carry `estado: "resuelta"`.

#### Scenario: Unknown fields rejected

- GIVEN a row carrying an unexpected field `legacy_msg`
- WHEN `AlertaSchema.parse(row)` runs (configured with `strict()` / `passthrough(false)`)
- THEN `ZodError` MUST be raised (defense against backend drift).

#### Scenario: datos_nuevos is optional today, mandatory when BE ships it

- GIVEN the current BE response omits `datos_nuevos` on every row
- WHEN `AlertaSchema.parse(row)` runs
- THEN parsing MUST succeed (the `.optional()` default allows `undefined`).
- AND WHEN a future BE row includes `datos_nuevos: { uuid_ingreso: "Z" }`
- THEN parsing MUST carry `datos_nuevos: { uuid_ingreso: "Z" }` typed as `Record<string, unknown> | null | undefined`.

### REQ-OPS-181 — Append-only `marcar revisada` action via `POST /workflows/alerta` (DEC-SUC-25, DA-F11.2-2)

`useResolverAlerta` (new hook at `apps/electron-sucursal/src/features/alertas/hooks/useResolverAlerta.ts`) MUST:

1. POST to `/api/v1/workflows/alerta` with body `{ uuid_sucursal, uuid_usuario, uuid_alerta_padre: original.uuid, tipo_alerta: original.tipo_alerta, estado: "resuelta", timestamp_evento: now() }`.
2. On `200 OK`: invalidate the `["/workflows/alerta", …]` SWR key (refresh cached list), re-render `<AlertasPanel />`.
3. On `403 Forbidden` with body `{"error": "actor_is_target"}`: surface a typed toast (descartada actor-check; per REQ-26-W-ALERTA-DESCARTADA this endpoint will reject when `uuid_usuario == ctx.actor_uuid`. For `resuelta` this MUST NOT trip the check; verify behavior is documented).
4. NEVER issue `PUT` or `PATCH` against `/workflows/alerta/{uuid}` — `prod.alerta` is `[A]` (append-only); corrections are modeled as new rows with `uuid_alerta_padre` set (DEC-SUC-25 canon from AGENTS.md §Architectural Principles).

#### Scenario: Successful resolve invalidates SWR cache

- GIVEN `<AlertasPanel />` shows the alert `A` and the user clicks `<ResolverAlertaButton>`
- WHEN the POST returns `200 OK` with body `{ uuid: "B", uuid_alerta_padre: "A", estado: "resuelta" }`
- THEN `useAlertas` MUST refetch within one SWR refresh cycle (`mutate(["/workflows/alerta", uuid_sucursal, "activa"])`)
- AND the next render of `<AlertasPanel />` MUST NOT include the original alert `A` (it has `uuid_alerta_padre: "B"` semantics, but the practical effect is that `A` was the original `estado: "activa"` alert and `B` is the new `estado: "resuelta"` row; the resolver surface is governed by `?estado=activa`).

#### Scenario: Backend persists a new row with `uuid_alerta_padre` pointing to the original

- GIVEN the operator submits the resolver via the panel
- WHEN the e2e test queries `prod.alerta WHERE uuid_alerta_padre = $original_uuid ORDER BY created_at DESC LIMIT 1`
- THEN exactly ONE row MUST be returned (DA-F11.2-8 — no UPDATE, only append).
- AND the new row's `estado` MUST equal `'resuelta'`.

#### Scenario: PUT/PATCH are NEVER issued against `/workflows/alerta/{uuid}`

- GIVEN a TypeScript test runs `getHTTPCalls()` against the parked `parkosFetch` mock during a resolver flow
- WHEN the resolver hook completes
- THEN the recorded calls MUST NOT include any `PUT` or `PATCH` method against `/workflows/alerta/*`.

### REQ-OPS-182 — `BUSINESS_ALERT_CODES` whitelist of 11; technical codes drop silently (ABIERTO-06, DA-F11.2-5)

`apps/electron-sucursal/src/lib/alertas/constants.ts` MUST export:

```ts
export const BUSINESS_ALERT_CODES = new Set<string>([
  // business alerts — render in <AlertasPanel />
]);

export const TECHNICAL_ALERT_CODES = new Set<string>([
  // technical alerts — silently dropped per ABIERTO-06
]);
```

The exact 11-code whitelist MUST be derived from the operational alerts surfaced in `plan.md:2303-2344` (subset ratified by F11.2): `{ descuadre_critico, fe_error_toppoint, numeracion_toppoint_agotada, …other 8 }`. The 8-code blacklist MUST be exactly: `{ hash_chain_anomaly, dian_rechazada, dian_timeout, dian_error, branch_offline_reauth_required, orphan_workflow_chain, fe_provider_error, fe_numbering_exhausted }`.

`useAlertas` MUST drop any row whose `tipo_alerta` is in `TECHNICAL_ALERT_CODES` (or not in `BUSINESS_ALERT_CODES`) before populating `mergedAlertas`. The drop MUST NOT throw, MUST NOT log at `error` level, and MUST emit exactly one `console.debug` per dropped code (per ABIERTO-06 — FE is the authority boundary for the 8-vs-11 filter; the cloud-side `JobSyncCloud` operator may still surface them in Grafana).

#### Scenario: Mixed payload renders only the 11 business codes

- GIVEN `/workflows/alerta` returns 19 rows: 11 in `BUSINESS_ALERT_CODES` and 8 in `TECHNICAL_ALERT_CODES` (e.g. `hash_chain_anomaly`)
- WHEN `<AlertasPanel />` mounts
- THEN `<ul>` MUST contain exactly 11 `<li>` children
- AND `console.debug` MUST be called once per technical code
- AND `console.error` MUST NOT be called.

#### Scenario: Whitelist membership is constant-time per row

- GIVEN the hook drops 8 technical codes from 19 input rows
- WHEN the test asserts the cost of the filter
- THEN the implementation MUST use `Set.has(...)` (O(1) per row) — NOT an array `.includes()` (O(n)).

### REQ-OPS-183 — `e2e/alertas-panel.spec.ts` covers 11 visible + drill-down + resolver + 8 excluded (DA-F11.2-8, DA-F11.2-11)

`apps/electron-sucursal/e2e/alertas-panel.spec.ts` MUST cover, at minimum, the following four scenarios (per plan.md lines 2303-2344):

1. **(S1) 11 visibles + filterable** — Mock `/workflows/alerta` to return 11 business alerts spanning 3 `severidad` values. Assert `<AlertasPanel />` renders 11 `<li>` elements. Click the `severidad=alta` filter chip, assert re-render shows only the alta subset.
2. **(S2) drill-down per `tipo_alerta`** — Mock an alert of type `descuadre_critico` with `uuid_arqueo: "Y"`. Click the drill-down button, assert `page.url()` ends with `/caja/arqueo/Y`. Repeat for `capacidad_agotada_forzado` using `datos_nuevos.uuid_ingreso`.
3. **(S3) marcar revisada — BACKEND state verified** (DA-F11.2-8): Mock POST `/workflows/alerta` to return `200 OK` with `{ uuid: "B", uuid_alerta_padre: "A", estado: "resuelta" }`. After the click, query the **backend test DB** (`SELECT count(*) FROM prod.alerta WHERE uuid_alerta_padre = 'A'`) — assert exactly one row exists. This scenario MUST NOT rely solely on local UI state (DA-F11.2-8); it MUST verify the persisted row via a backend assertion harness (testcontainers Postgres fixture, per F1.2 precedent).
4. **(S4) 8 technical codes excluded** — Mock `/workflows/alerta` to return 8 technical codes (`hash_chain_anomaly`, `dian_rechazada`, …). Assert `<AlertasPanel />` renders 0 alerts (empty list with the `aria-live` empty-state copy). Assert `console.error` was NOT called for any of the dropped codes.

#### Scenario: S1 passes — 11 visibles, filter works

- GIVEN the panel is mounted with 11 mocked alerts (3 `severidad=alta`, 4 `severidad=media`, 4 `severidad=baja`)
- WHEN the page loads and the user clicks the `severidad=alta` chip
- THEN `<ul>` MUST contain exactly 3 `<li>` children with `data-severidad="alta"`.

#### Scenario: S3 — backend asserts new row in `prod.alerta`

- GIVEN the operator clicks `<ResolverAlertaButton>` on alert `A`
- AND the backend POST returns `200 OK`
- WHEN the test queries `prod.alerta WHERE uuid_alerta_padre = 'A'`
- THEN the row count MUST be exactly 1
- AND that row's `estado` MUST be `'resuelta'`.

#### Scenario: S4 — 8 technical codes do not render

- GIVEN the panel is mounted with mocked data containing only the 8 technical codes
- WHEN the page loads
- THEN `<ul>` MUST be empty
- AND `<p role="status">` carrying the empty-state copy MUST be present
- AND no `console.error` call was recorded.

## Drift reconciliation table

| Anchor | Severity | Status | Resolution |
|---|---|---|---|
| DA-F11.2-1 | High | RESOLVED | Codified 18 BE fields in REQ-OPS-177 + REQ-OPS-180. Drift closed. |
| DA-F11.2-2 | High | RESOLVED | `useResolverAlerta` POSTs to `/workflows/alerta` (DEC-SUC-25; same path as F11.1 stub). Codified in REQ-OPS-181. |
| DA-F11.2-3 | Med | RESOLVED | Client-side filter chips (severidad + tipo_alerta); 19 max is trivial; no BE filter endpoint required (REQ-OPS-178). |
| DA-F11.2-4 | Med | RESOLVED | Per-`tipo_alerta` router map at `lib/alertas/router.ts` (REQ-OPS-178). |
| DA-F11.2-5 | Med | RESOLVED | `BUSINESS_ALERT_CODES` whitelist of 11 + `TECHNICAL_ALERT_CODES` blacklist of 8 (REQ-OPS-182). |
| DA-F11.2-6 | Low | RESOLVED | SWR `refreshInterval: 30_000` (REQ-OPS-179). |
| DA-F11.2-7 | Low | RESOLVED | Derived `openAlertsCount` selector in `useAlertas` (REQ-OPS-179). |
| DA-F11.2-8 | Low | RESOLVED | E2E verifies backend via `prod.alerta` SELECT in S3 (REQ-OPS-183). |
| **DA-F11.2-9** | **GATING** | **RESOLVED** | FE Zod enum aligned to BE `Literal["activa", "descartada", "resuelta"]`; query param `?estado=activa`; legacy `abierta`/`cerrada` forbidden (REQ-OPS-177 + REQ-OPS-180). F11.1 stub deleted. |
| **DA-F11.2-10** | **High** | **RESOLVED** | Path (b) — FE compose from `/workflows/alert-types` SWR; client-side merge for `severidad`/`descripcion`/`mensaje` (REQ-OPS-179). Path (a) — `AlertaRead` JOIN — flagged as **ABBC-F11.2-BE-1** in `pending-fase-11.md`. |
| DA-F11.2-11 | High | RESOLVED | RED tests for `AlertaSchema`, `useAlertas`, `AlertaReadList`, `<AlertasPanel />` land in C1 of apply (spec §Validation matrix below; strict_tdd enforcement). |
| DA-F11.2-12 | Med | RESOLVED | F11.1 stub at `AlertasPanel.tsx` inspected: it is a placeholder (renders `<ul>` without filter chips, drill-down, or resolver). Spec mandates a clean rewrite (REQ-OPS-178). |
| DA-F11.2-13 | Med | RESOLVED | REQ-26-W-ALERTA-DESCARTADA actor check applies to `descartada` ONLY (BE Pydantic `AlertaCreate.estado: Literal[...]` enforces; F11.2 only emits `estado: "resuelta"`, so the check is never tripped in the resolver flow — REQ-OPS-181). |
| DA-F11.2-14 | Med | RESOLVED | `AlertaSchema` declares `datos_nuevos: z.record(z.unknown()).nullable().optional()` (REQ-OPS-180); router map uses `datos_nuevos.uuid_ingreso` for `capacidad_agotada_forzado` drill-down (REQ-OPS-178). |

## Validation matrix

| What | Test type | File | Must exist before apply T1 |
|---|---|---|---|
| FE Zod parses BE `AlertaRead` (18 fields + canonical state enum) | vitest unit | `AlertaSchema.test.ts` | YES |
| FE rejects `estado: 'abierta'` | vitest unit | `AlertaSchema.test.ts` | YES |
| FE rejects unknown fields (`strict()`) | vitest unit | `AlertaSchema.test.ts` | YES |
| `useAlertas` SWR 30s polling cadence | vitest unit (`vi.useFakeTimers`) | `useAlertas.test.ts` | YES |
| `useAlertas` 401 → `useAuthStore.clear()` + `parkos:auth:cleared` event | vitest unit | `useAlertas.test.ts` | YES |
| `useAlertas` `alert_types` merge populates `severidad`/`descripcion`/`mensaje` | vitest unit | `useAlertas.test.ts` | YES |
| `useAlertas` `openAlertsCount` filters business + `activa` only | vitest unit | `useAlertas.test.ts` | YES |
| `useResolverAlerta` POST append-only + SWR cache invalidate | vitest unit | `useResolverAlerta.test.ts` | YES |
| `<AlertasPanel />` renders 11 + drops 8 technical codes | vitest RTL + axe | `AlertasPanel.test.tsx` | YES |
| `<AlertaCard />` drill-down router map (per-`tipo_alerta`) | vitest RTL | `AlertaCard.test.tsx` | YES |
| `<AlertaFilterChips />` toggles visibility without re-fetching | vitest RTL | `AlertaFilterChips.test.tsx` | YES |
| `BUSINESS_ALERT_CODES` whitelist membership `O(1)` per row | vitest unit (perf sanity) | `constants.test.ts` | YES |
| S1 — 11 visibles + filterable | playwright e2e | `e2e/alertas-panel.spec.ts` | YES |
| S2 — drill-down per router map | playwright e2e | `e2e/alertas-panel.spec.ts` | YES |
| S3 — resolver backend row persisted | playwright e2e + testcontainers Postgres | `e2e/alertas-panel.spec.ts` | YES |
| S4 — 8 technical codes excluded | playwright e2e | `e2e/alertas-panel.spec.ts` | YES |
| axe-core WCAG 2.1 AA | playwright e2e (final block) | `e2e/alertas-panel.spec.ts` | YES |

## Risk acknowledgements (residual)

- **R-RES-F11.2-1** (MED): FE `/workflows/alert-types` SWR (5 min refresh) may return a different version than `/workflows/alerta` (30 s refresh) on a hot-deploy. Stale `severidad` for ~5 min is acceptable. ABBC-F11.2-BE-1 (backend JOIN) removes this risk permanently.
- **R-RES-F11.2-2** (LOW): `<AlertasPanel />` rewrite replaces F11.1 stub — Risk R-F11.1-CARRY-2 (F11.1 verify-report) explicitly authorised this. No rollback concerns since stub never shipped.
- **R-RES-F11.2-3** (LOW): REQ-26 actor check on `descartada` will throw 403 in the resolver flow IF the operator attempts `descartada` self-redirect (not exercised in F11.2 — F11.2 only emits `resuelta`). Verify in `useResolverAlerta.test.ts` that the happy-path payload is `{ estado: "resuelta" }`.
- **R-RES-F11.2-4** (LOW): `datos_nuevos` JSONB column is currently absent on the BE `AlertaRead` contract (DA-F11.2-14 — speculative). The schema declares `.optional()` so parse succeeds today; ABIERTO-07 (filed in `pending-fase-11.md`) tracks the BE-side addition.

## Forward hooks

- **F12.x (observability)** MAY export `openAlertsCount` as a Prometheus gauge for Grafana (mirroring F11.1's forward hook for `consecutiveFailures`).
- **v2 WebSocket sync** will remove the 30s SWR refresh and stream alerts over the same WS channel; `useAlertas` will retain its merge semantics from `alert_types` (REQ-OPS-179 invariant).
- **ABBC-F11.2-BE-1** (flagged for `pending-fase-11.md`) — backend delta: extend `AlertaRead` with a JOIN to `prod.alert_types` returning `severidad`, `descripcion`, and `mensaje` as top-level fields. This removes the two-SWR cost and deprecates R-RES-F11.2-1. Out of F11.2 scope.

## F11.1 Spec-Delta Appendix (carry-overs reconciled)

The following items were flagged as F11.1-SPEC follow-ups in the F11.1 verify-report and are reconciled here (non-blocking, no conflict with F11.2):

- **R-CARRY-1** — derived `estado` thresholds in `apiStatusStore`. F11.2 spec does NOT modify `apiStatusStore` (F11.1 REQ-OPS-173 contract remains intact). Future hook: F11.2 MAY consume `apiStatusStore.consecutiveFailures` to suppress alert rendering while `>= 3` (avoid redundant noise with `<LocalApiDownBanner />`); deferred.
- **REQ-OPS-173** — `LOCAL_API_DOWN_THRESHOLD = 3` constant. F11.2 spec uses a separate `alertas.*` i18n namespace (no collision). REQ-OPS-173 contract unchanged.
- **R-F11.1-CARRY-2** — rewrite of `<AlertasPanel />` stub explicitly authorised in F11.1 verify-report; F11.2 REQ-OPS-178 codifies the rewrite.

---

**End of delta spec.** Total: 7 ADDED requirements (REQ-OPS-177..183); GATING anchors DA-F11.2-9 + DA-F11.2-10 RESOLVED; F11.1 carry-overs (R-CARRY-1, REQ-OPS-173) reconciled in appendix; ABBC-F11.2-BE-1 flagged in `pending-fase-11.md` for backend JOIN follow-up.
