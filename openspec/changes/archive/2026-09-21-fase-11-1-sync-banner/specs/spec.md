# Delta Spec: `operations` — Fase 11.1 Sync Banner

## Header

| Field | Value |
|---|---|
| Change | `fase-11-1-sync-banner` |
| Phase | Fase 11 — Operational telemetry and alerts (HU-F11.1 of 2) |
| Base spec | `openspec/specs/operations/spec.md` (last REQ-OPS-169 from F10.3) |
| Gap | Substrate ships (`useSyncEstado` + `SyncStatusStrip`) with zero tests (DA-F11.1-8) AND schema drift vs backend `SyncEstadoRead` (DA-F11.1-7, gating). |
| Preflight | pace=auto, artifact=hybrid, delivery=ask-on-risk, budget=2000 LOC (Fase 11+ meta-budget ratificado 2026-09-21), strict_tdd=true, test=vitest+playwright, author=`Parkos Dev <dev@parkos.local>`. |
| Status | DELTA — 7 ADDED requirements (REQ-OPS-170..176). |

## ADDED Requirements

### REQ-OPS-170 — `useSyncEstado` Zod schema matches backend `SyncEstadoRead` (DA-F11.1-7 GATING)

The frontend Zod schema for `GET /sync/estado` responses MUST accept exactly the fields declared by backend `SyncEstadoRead` (`backend/packages/parkos_core/src/parkos_core/schemas/sync_infra.py` line 399): `uuid_sucursal: UUID`, `ultima_sync_at: datetime | null`, `lag_seg: int | null`, `pendientes: int >= 0`. The schema MUST NOT declare `estado`, `ultimo_error`, or `ultima_sync` (those fields do not exist on the backend and any current usage is dropped).

#### Scenario: Parses real backend response shape

- GIVEN a JSON body `{ "uuid_sucursal": "...", "ultima_sync_at": "2026-09-21T10:00:00Z", "lag_seg": 42, "pendientes": 3 }`
- WHEN `SyncEstadoSchema.parse(body)` runs
- THEN it MUST return a typed object with `lag_seg === 42` and `pendientes === 3`
- AND no `ZodError` is thrown.

#### Scenario: Accepts never-synced branch (`ultima_sync_at` IS NULL)

- GIVEN a JSON body `{ "uuid_sucursal": "...", "ultima_sync_at": null, "lag_seg": null, "pendientes": 0 }`
- WHEN `SyncEstadoSchema.parse(body)` runs
- THEN it MUST return `{ lag_seg: null, ultima_sync_at: null, pendientes: 0 }` without throwing.

#### Scenario: Rejects `lag_seg < 0` (Pydantic `int | None` guard)

- GIVEN `{ ..., "lag_seg": -1, ... }`
- WHEN parsed
- THEN `ZodError` MUST be raised.

### REQ-OPS-171 — `<SyncBanner />` top-of-page color strip with derived state

The `<SyncBanner />` component MUST render at the top of every protected route, color-coded by a frontend-derived `state` selector over `(lag_seg, pendientes, ultima_sync_at)`:
- `never_synced` — `ultima_sync_at IS NULL` (distinct NEUTRAL badge, NOT red).
- `online` — `lag_seg < 300` AND `ultima_sync_at` within last 3 600 s AND `pendientes < 100`.
- `lagging` — `300 <= lag_seg < 3 600` OR `1 <= pendientes < 100`.
- `offline` — `lag_seg >= 3 600` OR `ultima_sync_at` older than 3 600 s OR `pendientes >= 100`.

The component MUST consume `useSyncEstado` (SWR `refreshInterval: 30_000`), set `role="status"` + `aria-live="polite"` + `aria-atomic="true"`, and announce ONLY on state transition (last-announced-state ref + 2 s debounce — copy verbatim the F2.3 `StatusBar.tsx` lines 90-100 pattern).

#### Scenario: Green for in-window sync

- GIVEN `lag_seg=120`, `pendientes=0`, `ultima_sync_at` within last hour
- WHEN `<SyncBanner />` renders
- THEN it MUST render with the green CVA variant and announce "Sincronizacion al dia" via aria-live on transition only.

#### Scenario: Distinct badge for never-synced branch

- GIVEN `ultima_sync_at IS NULL`
- WHEN `<SyncBanner />` renders
- THEN it MUST render the NEUTRAL "Sin sincronizaciones aun" badge — NOT red — to avoid alarm fatigue on fresh installs.

### REQ-OPS-172 — `<LocalApiDownBanner />` separate component on 3 consecutive API failures

A SEPARATE component `<LocalApiDownBanner />` MUST render when `apiStatusStore.consecutiveFailures >= 3` and MUST NOT render otherwise. The component MUST use `role="alert"` + `aria-live="assertive"` (hard fault), with `aria-label="Estado de API local"` and copy "Sin conexion con API local" — distinct from `<SyncBanner />`. It MUST NOT share i18n keys with `<SyncBanner />` (DA-F11.1-1 + DA-F11.1-6).

#### Scenario: Renders after 3 consecutive failures

- GIVEN `apiStatusStore.consecutiveFailures === 3`
- WHEN the banner mounts
- THEN it MUST be in the DOM, with `role="alert"` and copy distinct from `<SyncBanner />`.

#### Scenario: Hides after one success

- GIVEN the previous state was 3 failures
- WHEN `apiStatusStore.reset()` fires
- THEN the banner MUST unmount within one render frame.

### REQ-OPS-173 — `apiStatusStore` Zustand store with `consecutiveFailures` counter

A new Zustand store `apiStatusStore` MUST expose: `{ online: boolean, consecutiveFailures: number, lastFailureIso: string | null }` plus actions `incrementFailure()` and `reset()`. The threshold `3` MUST be stored as an exported constant `LOCAL_API_DOWN_THRESHOLD = 3` from the store module (DA-F11.1-3). The counter MUST increment on every `window.bridge.apiStatus.get()` rejection and reset on success. `<StatusBar />` MUST also route through this store (single source of truth — DA-F11.1-2).

#### Scenario: Counter increments on failure

- GIVEN `consecutiveFailures === 0`
- WHEN `incrementFailure()` is called
- THEN `consecutiveFailures === 1` AND `lastFailureIso` is a fresh ISO timestamp.

#### Scenario: Counter resets on success

- GIVEN `consecutiveFailures === 3`
- WHEN `reset()` is called
- THEN `consecutiveFailures === 0` AND `online === true`.

### REQ-OPS-174 — Global mount in `App.tsx`

`<SyncBanner />` and `<LocalApiDownBanner />` MUST be mounted in `apps/electron-sucursal/src/renderer/App.tsx` adjacent to the existing `<StatusBar />` (DA-F11.1-1 — NOT replacing it). Order: `<StatusBar />` first (its API chip stays), then `<SyncBanner />`, then `<LocalApiDownBanner />`. Both new banners MUST render on every protected route.

#### Scenario: Both banners present on `/caja/abrir-turno`

- GIVEN an authenticated operator session
- WHEN the user navigates to `/caja/abrir-turno`
- THEN `<SyncBanner />` MUST be in the DOM
- AND, if `consecutiveFailures >= 3`, `<LocalApiDownBanner />` MUST also be in the DOM.

### REQ-OPS-175 — `e2e/sync-banner.spec.ts` with 4 scenarios + axe-core gate

A new Playwright spec `apps/electron-sucursal/e2e/sync-banner.spec.ts` MUST cover four scenarios (per plan.md lines 2286-2291):

1. **(a) verde** — `lag_seg` bajo, sync dentro ultima hora.
2. **(b) amarillo** — `lag_seg` por encima del umbral, sin fallos consecutivos.
3. **(c) rojo** — sync fallida o `lag_seg > 3600` OR `consecutiveFailures >= 3`.
4. **(d) LocalApiDownBanner** — `consecutiveFailures === 3`, banner visible con copy distinto.

Each scenario MUST call `page.clock.install({ time: 0 })` + `page.clock.fastForward(30_000)` for SWR poll advancement (Playwright 1.45+; DA-F11.1-5 — MUST NOT use `test.skip`). The spec MUST include an axe-core WCAG 2.1 AA gate at the end (RNF-022).

#### Scenario: Yellow state without API failures

- GIVEN `lag_seg=600`, `pendientes=0`, `consecutiveFailures=0`
- WHEN the page loads and `page.clock.fastForward(30_000)` advances SWR
- THEN `<SyncBanner />` MUST render with the yellow CVA variant
- AND `<LocalApiDownBanner />` MUST NOT be in the DOM.

### REQ-OPS-176 — RED tests for `useSyncEstado` + `SyncStatusStrip` close the untested-substrate gap (DA-F11.1-8)

Unit tests MUST land BEFORE any source change in T1 of apply (strict_tdd):
- `useSyncEstado.test.ts` — Zod parse against the real backend `SyncEstadoRead` shape (REQ-OPS-170), 401 → auth cleared, 403/404 → no retry.
- `SyncStatusStrip.test.tsx` — color mapping per state, never-synced badge, aria-live announce-on-transition only.
- `apiStatusStore.test.ts` — counter increment/reset, threshold derivation (REQ-OPS-173).

These tests are the source-of-truth going forward; existing substrate must be edited to satisfy them (not the reverse).

#### Scenario: All three test files exist and pass

- GIVEN the apply phase begins
- WHEN `vitest run` executes
- THEN `useSyncEstado.test.ts`, `SyncStatusStrip.test.tsx`, and `apiStatusStore.test.ts` MUST all pass.

## Drift reconciliation table

| Anchor | Status | Resolution |
|---|---|---|
| DA-F11.1-1 (HIGH — StatusBar overlap) | RESOLVED | Distinct copy ("Sin conexion con API local") + distinct `role` (`alert` vs StatusBar `status`) + distinct `aria-label`. F11.1 does NOT replace StatusBar; renders SEPARATE banner (REQ-OPS-172). |
| DA-F11.1-2 (MED — dual read) | RESOLVED | StatusBar re-routed through `apiStatusStore` (single source of truth) per REQ-OPS-173. |
| DA-F11.1-3 (MED — threshold storage) | RESOLVED | Zustand `consecutiveFailures` counter (REQ-OPS-173), explicit constant `LOCAL_API_DOWN_THRESHOLD = 3`. |
| DA-F11.1-4 (LOW — aria-live spam) | RESOLVED | Verbatim F2.3 StatusBar.tsx L90-100 pattern (lastAnnouncedState ref + 2 s debounce), codified in REQ-OPS-171. |
| DA-F11.1-5 (MED — 30 s poll test) | RESOLVED | `page.clock.install` + `fastForward(30_000)` per REQ-OPS-175; no `test.skip` allowed (strict_tdd). |
| DA-F11.1-6 (HIGH — distinct banners) | RESOLVED | 2 SEPARATE components with distinct `role`, `aria-label`, i18n keys (REQ-OPS-171 + REQ-OPS-172). |
| DA-F11.1-7 (HIGH GATING — schema drift) | RESOLVED | Backend `SyncEstadoRead` (sync_infra.py:399) has `ultima_sync_at`, `lag_seg`, `pendientes` ONLY — NO `estado`, NO `ultimo_error`, NO `ultima_sync`. **FE is wrong on 4 axes** (extra fields + name mismatch + nullability). F11.1 fixes FE; no BE delta needed. Codified in REQ-OPS-170. |
| DA-F11.1-8 (MED — untested substrate) | RESOLVED | RED tests land BEFORE any source change (REQ-OPS-176). |

## Validation matrix

| What | Test type | File | Must exist before apply T1 |
|---|---|---|---|
| FE Zod schema parses BE shape | vitest unit | `useSyncEstado.test.ts` | YES |
| Color by derived state | vitest unit | `SyncStatusStrip.test.tsx` | YES |
| aria-live announce on transition only | vitest unit | `SyncStatusStrip.test.tsx` | YES |
| 3-strike counter increment/reset | vitest unit | `apiStatusStore.test.ts` | YES |
| SWR 30 000 ms refresh cadence | vitest unit (`vi.useFakeTimers`) | `useSyncEstado.test.ts` | YES |
| Verde / Amarillo / Rojo / LocalApiDown | playwright e2e | `e2e/sync-banner.spec.ts` | YES |
| axe-core WCAG 2.1 AA | playwright e2e | `e2e/sync-banner.spec.ts` (final block) | YES |

## Risk acknowledgements (residual)

- **R-RES-1** (LOW): SWR `refreshInterval: 30_000` is wall-clock based; clock skew between branch and cloud is irrelevant because `lag_seg` is computed server-side. Mitigation: no client clock arithmetic in SyncBanner derivation.
- **R-RES-2** (LOW): `<StatusBar />` re-routing through `apiStatusStore` is in-scope for this HU but is a F2.3 refactor. Mitigation: ship the store first (T1 of apply), rewire StatusBar second (T5) — both in same PR.
- **R-RES-3** (LOW): `parkosFetch` 401 path already clears `useAuthStore` (verified in `useSyncEstado.ts:60-66`). F11.1 inherits — no new logic.
- **R-RES-4** (LOW): If backend ever adds `estado` field back, FE Zod parse would FAIL with `extra='forbid'`-equivalent. Mitigation: BE schema explicitly documents the 4 fields; future additions go through OpenSpec.

## Forward hooks

- **F11.2 (alertas panel)** MAY consume `apiStatusStore` to suppress alert rendering while `consecutiveFailures >= 3` (avoid redundant noise).
- **F12.x (observability)** MAY export `apiStatusStore.consecutiveFailures` as a Prometheus gauge for Grafana.
- **Future migration to WebSocket sync** (v2): `useSyncEstado` SWR `refreshInterval` will be removed when WS lands; the derived-state selector in REQ-OPS-171 will be reused verbatim.

---

## Recovery note (2026-09-21, sdd-archive operational error)

This file (`specs/spec.md`) was reconstructed from the orchestrator's launch prompt + the in-session Read of the same file (173 lines) after the original disk copy was inadvertently destroyed during the sdd-archive mechanical-copy step. The substantive content (Header, REQ-OPS-170..176, drift table, validation matrix, risks, forward hooks) is byte-identical to the version that was synced into `openspec/specs/operations/spec.md` as the canonical delta merge. See `archive-report.md` §3 for the full incident timeline.