# Delta for `operacion` — HU-F9.2 Listado y alerta de vencimiento

> **Domain**: operaciones/suscripciones | **Change**: `fase-9-2-listado-vencimiento` | **Type**: DELTA (extends existing F9.1 capability)

## ADDED Requirements

### Requirement: REQ-OPS-181 — `useSuscripcionesProximasVencer` hook + days calculation

The system SHALL export `useSuscripcionesProximasVencer(uuid_sucursal)` from
`apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesProximasVencer.ts`
as an SWR hook polling `GET /api/v1/suscripciones-cliente/proximas-vencer?uuid_sucursal=X`
with `refreshInterval: 60_000`. The hook MUST return a stable-shape
`{ data: ProximaVencer[] | undefined; error: Error | undefined; refresh: () => Promise<...> }`
and MUST calculate for each item
`dias_para_vencer = floor((fecha_vencimiento_ms - NOW_ms) / 86_400_000)`. Items where
`dias_para_vencer < 0` (ya vencidas) MUST be filtered out from the returned `data`
array. The returned array MUST be sorted by `fecha_vencimiento` ASCENDING
(closest expiry first). The hook MUST preserve the F3.1 invariant: on HTTP 401
the hook MUST call `useAuthStore.getState().clear()` and dispatch the
`parkos:auth:cleared` window event. [Cite: plan.md:2100-2102]

#### Scenario: filter excludes vencidas

- GIVEN 3 items: vence_en=5d, vence_en=10d, ya_vencida (-3d)
- WHEN the hook resolves with the array
- THEN `data` MUST contain only 2 items (the 5d and 10d ones)
- AND the `ya_vencida` item MUST NOT be present in `data`

#### Scenario: sort by fecha_vencimiento ASC

- GIVEN 3 items with `fecha_vencimiento` = T+10d, T+5d, T+15d
- WHEN the hook resolves
- THEN `data[0].dias_para_vencer` MUST equal 5
- AND `data[1].dias_para_vencer` MUST equal 10
- AND `data[2].dias_para_vencer` MUST equal 15

#### Scenario: empty array returns []

- GIVEN the backend returns `[]`
- WHEN the hook resolves
- THEN `data` MUST equal `[]`

### Requirement: REQ-OPS-182 — `<Listado />` page with DataTable + búsqueda cliente-side

The system SHALL export `<Listado />` from
`apps/electron-sucursal/src/features/suscripciones/pages/Listado.tsx` as a page
accessible at the route `/suscripciones`. The page MUST render a search input
(`data-testid="listado-search-input"`) above a table
(`data-testid="listado-table"`) with columns `cliente | plan | fecha_vencimiento |
dias_restantes | estado`. The search input MUST filter the table rows
CLIENT-SIDE (no new GET issued) by case-insensitive substring match against
either `placa` or `cliente_nombre` of each row. The table MUST render at least
one row per item returned by `GET /api/v1/suscripciones-cliente?uuid_sucursal=X&cursor=…`,
paginated by cursor. Items with `estado='vencida'` MUST render with the badge
text `t('suscripciones:vencida')`. [Cite: plan.md:2099-2103]

#### Scenario: búsqueda por placa filtra

- GIVEN the page is mounted with 3 rows: ABC123, DEF456, GHI789
- AND the operator types "ABC123" into the search input
- WHEN the search fires (debounced or immediate — implementation detail)
- THEN the DataTable MUST show only 1 row (the ABC123 one)
- AND no new GET request MUST be issued (verified by SWR deduping count)

#### Scenario: empty search shows all rows

- GIVEN the page is mounted with 3 rows
- AND the search input is empty
- THEN the DataTable MUST show all 3 rows

#### Scenario: render shows columns

- GIVEN the page is mounted with 1 row
- THEN the rendered HTML MUST contain the columns cliente, plan,
  fecha_vencimiento, dias_restantes, estado in the table head

### Requirement: REQ-OPS-183 — Principal.tsx banner integration with literal text

The system SHALL modify the F6.x hub page (`apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx`
on the current `dev` branch — referenced as "Principal.tsx" in plan.md
line 2122, a path that does not exist on `dev`; the actual file is
`Dashboard.tsx`) to render an inline banner when
`useSuscripcionesProximasVencer().data?.length > 0`. The banner MUST display
the LITERAL text **"Suscripción de esta placa vence en X días (fecha).
Considere renovación."** with `X` interpolated as
`data[0].dias_para_vencer` and `fecha` interpolated as `data[0].fecha_vencimiento`
formatted as `YYYY-MM-DD`. The banner element MUST expose
`data-testid="dashboard-vencimiento-banner"` for e2e and MUST include
`role="alert"`. The dashboard MUST additionally render a "Suscripciones por
vencer" panel (`data-testid="dashboard-vencimiento-panel"`) in the right
sidebar showing the TOTAL count (`data.length`) and a list of the first 5
items from the same array, each rendered with placa and dias_restantes.
[Cite: plan.md:2100-2101]

#### Scenario: banner with 1 suscripcion por vencer

- GIVEN `useSuscripcionesProximasVencer()` resolves to
  `[{ placa: 'ABC123', dias_para_vencer: 5, fecha_vencimiento: '2026-09-24', cliente_nombre: 'X', plan_nombre: 'Y' }]`
- WHEN the dashboard renders
- THEN the banner element MUST contain the EXACT text:
  `"Suscripción de esta placa vence en 5 días (2026-09-24). Considere renovación."`

#### Scenario: panel shows count + first 5

- GIVEN the hook resolves to 7 items
- WHEN the dashboard renders
- THEN the panel MUST display the text "7" as the total
- AND the panel MUST list items 0..4 (5 items total) sorted by fecha ASC

#### Scenario: no banner when data is empty

- GIVEN the hook resolves to `[]`
- WHEN the dashboard renders
- THEN the banner element MUST NOT be present in the DOM
- AND the panel MUST show "0" as the total

### Requirement: REQ-OPS-184 — ABIERTO-05 drift anchor: default 7 días global

The system SHALL export the constant
`DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7` from
`apps/electron-sucursal/src/features/suscripciones/lib/constants.ts` and MUST
use it as the single source of truth for the proximity threshold. The
per-suscripción override capability required by CU-06 BR4 SHALL remain as
**ABIERTO-05 follow-up** and is OUT OF SCOPE for F9.2 (no override column
in `subscripciones_cliente`; no override field in the schema; no override
input in the F9.1 wizard step 3). The mandatory AST drift guard:
`git grep -nE "dias_alerta_pre_vencimiento_override" apps/electron-sucursal/src`
MUST return zero matches at the pre-commit verification step. [Cite:
plan.md:2105]

#### Scenario: AST drift guard

- `git grep -nE "dias_alerta_pre_vencimiento_override" apps/electron-sucursal/src`
  MUST return 0 matches at pre-commit verification
- AND the constant `DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7` MUST be the
  single source of truth for the banner threshold

## Drift reconciliation

| Plan.md intent | F9.2 actual |
|---|---|
| `useSuscripcionesList.ts` SWR hook (F9.2 listing) | EXISTS on dev (read-only SWR query, F9.1 archive cleared dead stub) | F9.2 uses it as-is for `<Listado />` page data |
| `useSuscripcionesProximasVencer.ts` | NEW | F9.2 ships |
| `<Listado />` page | NEW | F9.2 ships |
| `Principal.tsx` banner | NEW | F9.2 integrates into `Dashboard.tsx` (actual file on dev) — Principal.tsx does not exist |
| `dias_alerta_pre_vencimiento` per-suscripción override | OUT per ABIERTO-05 | F9.2 ships global only |

## Out of scope

- Per-suscripción override of `dias_alerta_pre_vencimiento` (ABIERTO-05).
- Backend new endpoints (Path A reuses `/api/v1/suscripciones-cliente` listing + `/proximas-vencer` subroute).
- Push notifications, email reminders, print queue integration for proximity.
- F10.x arqueo / F11.x reimpresión work — not adjacent.

## Acceptance

- `useSuscripcionesProximasVencer()` filters vencidas (`dias < 0`) out.
- Banner literal text EXACT match per scenario "banner with 1 suscripcion por vencer".
- Top 5 sorted by fecha_vencimiento ASC.
- Drift guard returns 0 matches for `dias_alerta_pre_vencimiento_override`.
- 3 hook tests + 3 component tests + 2 e2e stub scenarios all present.
- Final diff vs `dev` ≤ 800 LOC.
