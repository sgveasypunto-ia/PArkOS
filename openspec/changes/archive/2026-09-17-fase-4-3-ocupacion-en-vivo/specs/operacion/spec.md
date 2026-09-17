# Delta for `operacion` — HU-F4.3 Occupancy Strip

This delta extends the `operacion` capability introduced by HU-F4.1 (`openspec/changes/fase-4-1-deteccion-tipo-vehiculo/specs/operacion/spec.md`) with the frontend consumer of the existing backend endpoint `GET /api/v1/operacion/ocupacion`. The endpoint contract (REQ-OPS-030, REQ-OPS-031) is **unchanged** — this delta describes the renderer behavior only.

## ADDED Requirements

### Requirement: Polling Cadence Aligned with Materialized View Refresh

The system MUST poll `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` every 10 000 ms (DEC-SUC-11 verbatim, in sync with `RefreshMvOcupacionWorker` backend). The interval MUST be exported as a single constant `OPERACION_REFRESH_INTERVAL_MS = 10_000` from a shared module (`src/features/operacion/constants.ts`) so a future change to the cadence breaks the build in both renderer and worker consumers. The hook MUST gate the SWR key on `useAuthStore.accessToken` — when the operator is not authenticated, the key is `null` and no fetch occurs (precedent F3.3 `useSesionActiva`, F4.1 `useTiposVehiculo`). The hook MUST set `dedupingInterval: 5_000` so multiple consumers (F4.4 dashboard, F6.x ingreso) sharing the same key do not trigger duplicate polls. **RFC 2119**: MUST (10 s, dedupe 5 s, key null pre-auth, constant export).

#### Scenario: Polling fires every 10 s while authenticated
- GIVEN the operator is authenticated and `<OcupacionStrip />` is mounted on screen
- WHEN 30 s elapse
- THEN the hook fires exactly 3 fetches against `/api/v1/operacion/ocupacion?uuid_sucursal=X` (10 s + 10 s + 10 s; dedup 5 s collapses intra-tick requests).

#### Scenario: Cold-boot pre-auth suppresses the poll
- GIVEN `useAuthStore.accessToken` is null
- WHEN `<OcupacionStrip />` mounts
- THEN the SWR key is `null` and no network request is issued until the operator logs in.

### Requirement: Per-Tipo Render with Color Threshold Map

The system MUST render one chip per item returned by the endpoint, with text `<Tipo>: <activos>/<cupo_maximo>`. Each chip MUST be colored by the percentage `activos / cupo_maximo` using the constant thresholds exported from `occupancyThresholds.ts`:

| Range | Color |
|-------|-------|
| `0 ≤ p < THRESHOLD_YELLOW (0.7)` | green |
| `THRESHOLD_YELLOW ≤ p ≤ THRESHOLD_RED (0.9)` | yellow |
| `p > THRESHOLD_RED` | red |

The function `classForPorcentaje(p: number): 'green' | 'yellow' | 'red'` MUST be a pure function exported from the same module — no DOM, no I/O — to make the unit test trivial. Color tokens MUST be shadcn semantic tokens (`bg-green-500`, `bg-amber-500`, `bg-destructive`) so the white-label per-tenant theme continues to apply. When `cupo_maximo === 0` (KD-6 valid negative — admin has not configured capacity, REQ-OPS-030 S3), the chip MUST render with the red color and tooltip `cupo_no_configurado` ("cupo no configurado, contacte al administrador"). **RFC 2119**: MUST (one chip per item, threshold map, pure function, semantic tokens, KD-6 negative interpretation).

#### Scenario: Auto at 23/50 renders green
- GIVEN the endpoint returns `{ tipo: 'Auto', cupo_maximo: 50, activos: 23 }`
- WHEN the strip renders
- THEN the Auto chip renders with text `Auto: 23/50` and `data-color="green"`.
- AND `classForPorcentaje(0.46) === 'green'`.

#### Scenario: Auto at 40/50 renders yellow
- GIVEN `{ tipo: 'Auto', cupo_maximo: 50, activos: 40 }` (p = 0.80)
- WHEN the strip renders
- THEN the Auto chip renders with `data-color="yellow"`.
- AND `classForPorcentaje(0.80) === 'yellow'`.

#### Scenario: Auto at 47/50 renders red
- GIVEN `{ tipo: 'Auto', cupo_maximo: 50, activos: 47 }` (p = 0.94)
- WHEN the strip renders
- THEN the Auto chip renders with `data-color="red"`.
- AND `classForPorcentaje(0.94) === 'red'`.

#### Scenario: Cupo not configured surfaces red chip + tooltip
- GIVEN `{ tipo: 'Auto', cupo_maximo: 0, activos: 3, disponible: -3 }`
- WHEN the strip renders
- THEN the Auto chip renders with `data-color="red"` and tooltip text `cupo_no_configurado`.

### Requirement: Live Update Without Page Reload

When a new ingreso or salida changes the breakdown, the strip MUST reflect the change in the next polling cycle (≤10 s) **without** a page reload, navigation event, or operator action. The update MUST be announced to assistive technologies via `aria-live="polite"` + `aria-atomic="false"` on each chip cell so screen readers read only the changed value, not the entire strip. **RFC 2119**: MUST (≤10 s, no reload, polite announcement, atomic-false).

#### Scenario: New ingreso increases activos
- GIVEN the strip shows `Auto: 23/50` and a new ingreso is registered against the local API
- WHEN the next poll fires (≤10 s)
- THEN the strip updates to `Auto: 24/50` with `data-color` recomputed from the new percentage.
- AND no `window.location.reload` or `navigate()` call is issued.

#### Scenario: Screen reader announces only the changed chip
- GIVEN an Auto chip changes from `23/50` to `24/50`
- WHEN the change is committed to the DOM
- THEN the Auto cell's `aria-live="polite"` + `aria-atomic="false"` announces only the new text, not the whole strip.

### Requirement: Polling Failure Preserves Last Known Value with Stale Marker

When a polling cycle fails (network error, 5xx, or `parkosFetch` rejection), the strip MUST NOT clear its visible value. Instead, it MUST keep the last successful response rendered, set `data-stale="true"` on the root element, and show an `AlertCircle` icon (lucide-react) with a tooltip `ocupacion_stale` ("ocupación desactualizada") — operator keeps situational awareness while the backend recovers. The marker MUST clear automatically on the next successful poll. **RFC 2119**: MUST (preserve last value, stale marker, auto-clear on recovery).

#### Scenario: Network error preserves last value
- GIVEN the strip successfully rendered `Auto: 23/50` at `t=0`
- WHEN the next poll at `t=10s` rejects with `NetworkError`
- THEN the strip still shows `Auto: 23/50` and the root element has `data-stale="true"`.
- AND the `AlertCircle` icon and `ocupacion_stale` tooltip are visible.

#### Scenario: Successful poll after failure clears stale marker
- GIVEN `data-stale="true"` from the previous failed poll
- WHEN the next poll succeeds
- THEN `data-stale` is removed from the root and the icon disappears.

### Requirement: AbortController Cleanup on Unmount

The hook MUST create a fresh `AbortController` per fetch cycle and MUST cancel the in-flight request in the `useEffect` cleanup function on unmount. The cancellation MUST also be triggered when the component re-renders with a different `uuid_sucursal` (operator switches branch in admin mode) — stale responses from the previous branch MUST NOT overwrite fresh data. **RFC 2119**: MUST (AbortController per cycle, cleanup on unmount, cleanup on key change).

#### Scenario: Unmount during in-flight fetch aborts the request
- GIVEN `<OcupacionStrip />` is unmounted while a poll is in flight
- WHEN React runs the cleanup function
- THEN the `AbortController.abort()` is called and the network request is cancelled (verified via `parkosFetch` mock that asserts the abort signal is honored).

#### Scenario: Branch change cancels the prior branch's poll
- GIVEN the strip is mounted for `uuid_sucursal=X` and a poll is in flight
- WHEN `uuid_sucursal` prop changes to `Y`
- THEN the in-flight fetch for X is aborted before the new fetch for Y starts.

### Requirement: Tooltip Legend on Hover

Each chip MUST have a `<Tooltip>` (shadcn primitive at `src/renderer/components/ui/tooltip.tsx`) on hover/focus that explains the threshold and the current status. The tooltip text MUST be one of:

- `ocupacion_legend_green` ("menos del 70% — hay cupo disponible")
- `ocupacion_legend_yellow` ("entre 70% y 90% — acercarse al lleno")
- `ocupacion_legend_red` ("más del 90% — casi lleno")
- `ocupacion_legend_stale` ("dato desactualizado por falla de polling")

The tooltip MUST be keyboard-accessible (focus + Escape to dismiss — Radix primitive default). **RFC 2119**: MUST (one tooltip per chip, i18n key per color, keyboard-accessible).

#### Scenario: Hover on green chip shows green legend
- GIVEN the Auto chip has `data-color="green"`
- WHEN the operator hovers or focuses the chip
- THEN the tooltip shows the `ocupacion_legend_green` text.

#### Scenario: Stale state shows stale legend on the root tooltip
- GIVEN the strip has `data-stale="true"`
- WHEN the operator hovers or focuses the root
- THEN the tooltip shows the `ocupacion_legend_stale` text.

### Requirement: WCAG 2.1 AA Conformance

The strip MUST pass `@axe-core/playwright` with tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` with zero violations (RNF-022 + DEC-SUC-10 verbatim). Specifically: every chip MUST have an accessible name (the visible text counts); the `aria-live` region MUST NOT include redundant `aria-atomic="true"` (we want per-cell granularity); color MUST NOT be the only carrier of meaning (the text `Auto: X/Y` is always present alongside color); contrast ratio of text against chip background MUST meet 4.5:1. **RFC 2119**: MUST (axe-core 0 violations, accessible name per chip, no color-only meaning, 4.5:1 contrast).

#### Scenario: axe-core reports 0 violations on the rendered strip
- GIVEN the strip renders with 2 chips
- WHEN `@axe-core/playwright` scans with the four WCAG tags
- THEN the violations array is empty.

## Error Catalog

| Code | Severity | When | UX behavior |
|------|----------|------|-------------|
| `ocupacion_endpoint_missing` | BLOCKER | `GET /api/v1/operacion/ocupacion` is not mounted in `api-sucursal` (HU-F1.5 not closed) | Stop SDD. Return `status: blocked`. Do NOT stub or invent the endpoint. |
| `ocupacion_stale` | WARNING | Poll fails after a successful response | Keep last value + `data-stale="true"` + `AlertCircle` + tooltip. |

## MODIFIED Requirements

None. This HU adds frontend behavior only — it does not modify the backend contract (REQ-OPS-030, REQ-OPS-031) nor any requirement in `openspec/changes/fase-4-1-deteccion-tipo-vehiculo/specs/operacion/spec.md`.

## REMOVED Requirements

None.

## RENAMED Requirements

None.
