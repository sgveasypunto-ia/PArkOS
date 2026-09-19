# Delta Spec: HU-F7.1 — Búsqueda tolerante y cotización (CU-02) + schema drift reconciliation

> **Change**: `fase-7-1-busqueda-tolerante-cotizacion`
> **Phase**: sdd-spec
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-apply`
> **HU ID**: HU-F7.1 (Fase 7 — Salida y cálculo de tarifa)
> **Base spec**: `openspec/specs/operations/spec.md` (canonical, requires REQ-OPS-001..142)
> **Next free REQ-OPS gap**: 143..151 (REQ-OPS-141 and REQ-OPS-142 are taken — `router_factory` guard for tables without `vigente_desde` and `GET /auth/me` + cookie + lockout, both shipped 2026-09-17). F7.1 starts at REQ-OPS-143.
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC`, strict_tdd=`true`, chain_strategy=`n/a`
> **Git identity**: `Parkos Dev <dev@parkos.local>` per AGENTS.md gitflow. No AI attribution.
> **Artifact language**: English (SDD canon); user-facing i18n keys in `operacion.json` stay in Spanish es-CO.
> **Skills loaded**: `react` (D-073 stack), `shadcn` (WCAG 2.1 AA, lucide-react único).

## Context

HU-F7.1 delivers the F6.x → F7.x operator pivot: from a registered `ingreso`
to a live `cotización` the operator can confirm or refresh before drawing
payment. The system MUST tolerate common typing errors
(DEC-SUC-22: `O↔0`, `I↔1`, `B↔8`) when searching for an active ingreso by
plate, MUST consume the canonical F1.8 discriminated-union wire contract
(`{cobrar, motivo?, subtotal?, iva?, total?, tiempo_minutos?,
tarifa_uuid?, vigente_hasta?}` per REQ-OPS-022..025), and MUST render the
breakdown as a semantic `<dl>` with a 15-minute countdown that turns red
when ≤2 minutes remain.

Concurrent with the net-new feature, F7.1 reconciles a documented schema
drift between the current `useCotizacion.ts` / `SalidaPanel.tsx`
(6-field flat shape: `{uuid_ingreso, uuid_tarifa_vigente,
minutos_transcurridos, base_cop, fraccion_cop, total_cop, generado_en}`)
and the canonical F1.8 discriminated-union contract. The drift is closed
in-place in F7.1 by rewriting the Zod schema (R1), migrating the `<dl>`
consumer in `SalidaPanel.tsx` (R2), swapping the i18n keys (R3), and
pinning the new contracts with tests (R4+R5). The drift reconciliation
ships as part of this single self-contained PR per the user ratification
2026-09-19 — no separate audit-then-fix split.

The user-facing payoff: the operator sees the same numbers the cashier
will charge, sees the calculation age, and can recalculate when the
validity window closes — without leaving the dashboard and without
trusting a client-side price formula (DEC-SUC-23 verbatim: the monto
lives only in `facturas`; `cotizar` is the sole authority on
`subtotal`/`iva`/`total`).

## New requirements

### REQ-OPS-143 — `<CotizacionPanel />` consumes the canonical F1.8 discriminated union

The system SHALL render the fiscal breakdown via the pure presentational
component `<CotizacionPanel data={cotizacion} secondsLeft={n}
onConfirmar={fn} onRecalcular={fn} />` where `cotizacion` is the
discriminated-union type `CotizarFacturacion | CotizarMensualidad`
defined as `z.infer<typeof CotizacionSchema>` from
`useCotizacion.ts` (Zod canonical schema mirroring
`backend/.../schemas/operacion.py:251-263`). [Cite: REQ-OPS-022..025 |
proposal.md §2.1 R1]

#### Scenario: rotación branch renders the full fiscal breakdown

- **Given** `cotizacion.cobrar === true` and the canonical discriminated
  payload `{cobrar: true, subtotal: 41000, iva: 7790, total: 48790,
  tiempo_minutos: 32.5, tarifa_uuid: '...', vigente_hasta: '...'}`
- **When** `<CotizacionPanel />` mounts in the operator dashboard
- **Then** the component MUST render a semantic `<dl>` with the keys
  `cotizar.subtotal`, `cotizar.iva`, `cotizar.total`,
  `cotizar.tiempo_minutos`, `cotizar.tarifa`, `cotizar.vigencia`
  (F4.2 i18n namespace precedent)
- **And** the monetary values MUST be rendered through `formatCOP(value)`
  from `apps/electron-sucursal/src/features/caja/lib/format.ts:31` (no
  raw `.toLocaleString('es-CO') + '$'` per REQ-OPS-147)
- **And** the `onConfirmar` callback MUST be wired by the parent to
  `useDashboardDrawerStore.open('pago', pagoAnchorId)` (REQ-OPS-138
  single-drawer invariant preserved).

#### Scenario: mensualidad branch short-circuits to the info banner

- **Given** `cotizacion.cobrar === false` and the payload
  `{cobrar: false, motivo: 'mensualidad_vigente'}`
- **When** `<CotizacionPanel />` mounts
- **Then** the component MUST NOT render the `<dl>` breakdown
- **And** MUST render the `cotizar.mensualidad.titulo` and
  `cotizar.mensualidad.descripcion` info banner
- **And** the confirm button MUST surface
  `cotizar.mensualidad.accion` ("Confirmar salida por mensualidad") and
  invoke `onConfirmar` with the mensualidad branch — a different parent
  handler than the rotación branch (forward to HU-F7.2
  `SalidaMensualidad` POST — out of scope for F7.1, but the prop
  interface supports it).

### REQ-OPS-144 — `buscarIngresoTolerante(placa)` applies DEC-SUC-22 tolerance and lives in a separate file

The system SHALL export `buscarIngresoTolerante(placa: string,
getIngresosByPlaca: (placa: string) => Promise<readonly Ingreso[]>):
Promise<ToleranteResultado>` from
`apps/electron-sucursal/src/lib/validation/placaTolerante.ts` — a
separate file from `apps/electron-sucursal/src/lib/validation/placa.ts`
per DEC-SUC-22. The function MUST apply the tolerance map
`O↔0`, `I↔1`, `B↔8` (exported as `TOLERANCIA_PLACA`) and return up to
N placa variants via `generarVariantesTolerantes(placa: string):
readonly string[]` for downstream `getIngresosByPlaca` queries.
[Cite: DEC-SUC-22 | proposal.md §2.1 T1 + §3.1 | F4.1 proposal.md line 17
"lives in a separate function in a separate file by design"]

#### Scenario: typo `AB0123` (O↔0) resolves to unique ingreso

- **Given** the branch DB holds one active `ingreso(X, ABC123)` (no
  salida, no anulación ejecutada)
- **When** the operator submits the form with the typo placa
  `buscarIngresoTolerante('AB0123', getIngresosByPlaca)`
- **Then** the function MUST generate the variants `[AB0123, ABC123]`
  (1 typo at position 4: `O↔0`)
- **And** MUST iterate the variants through `getIngresosByPlaca`
- **And** MUST return `{kind: 'found', uuid_ingreso: 'X', placaReal:
  'ABC123', varianteUsada: 'AB0123'}` (early-exit on first hit)
- **And** MUST NOT mutate the `ingreso` table or invoke
  `detectarTipoVehiculo` (DEC-SUC-22 strict detector stays in `placa.ts`).

### REQ-OPS-145 — `useCotizacion` polls at 1s with 5s timeout, 401 clears auth

The system SHALL export `useCotizacion(uuid_ingreso: string | null)`
from
`apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts`
as an SWR hook polling `GET /api/v1/operacion/cotizar?uuid_ingreso=X`
at `refreshInterval: OPERACION_COTIZAR_REFRESH_INTERVAL_MS = 1_000`
while the panel is mounted, with `refreshInterval: 0` (no polling) when
`uuid_ingreso === null`. Each fetch MUST abort after
`OPERACION_COTIZAR_TIMEOUT_MS = 5_000` via `AbortController`.
`shouldRetryOnError` MUST exclude 401/403/404. On HTTP 401, the hook
MUST call `useAuthStore.clear()` AND dispatch the `parkos:auth:cleared`
event (preserved invariant from current impl lines 96-105). [Cite:
proposal.md §2.1 T2 + R1 | plan.md:1685]

#### Scenario: HTTP 401 from cotizar clears auth and redirects to login

- **Given** an SWR key of `'/operacion/cotizar?uuid_ingreso=X'` and the
  branch API returns `401 Unauthorized` because the JWT expired during
  the polling window
- **When** `useCotizacion(X)` receives the 401 response
- **Then** the hook MUST invoke `useAuthStore.getState().clear()` AND
  emit `window.dispatchEvent(new Event('parkos:auth:cleared'))` (this
  is the F3.1 logout contract from REQ-OPS-107..110)
- **And** the hook MUST set `shouldRetryOnError` to `false` for that
  error so SWR does not re-poll the endpoint
- **And** the operator dashboard MUST redirect to `/login` via the
  F3.1 redirect rule (REQ-OPS-111).

### REQ-OPS-146 — 15-minute countdown turns red with `aria-live` ticks when secondsLeft < 120

The system SHALL wrap the countdown `<div>` inside `<CotizacionPanel />`
in `aria-live="polite"` (WCAG 2.1 AA, RNF-022) so screen readers
announce each tick. The countdown MUST turn `text-destructive` (shadcn
CSS variable `--destructive`), MUST render the `<AlertTriangle />` icon
from `lucide-react`, and MUST set `role="alert"` when
`secondsLeft < 120` (2-minute threshold). The countdown MUST reuse
`useCountdown(15 * 60)` from
`apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts` (F3.2
DEC-F3.2-01 drift-resistant `Date.now()` baseline). [Cite: REQ-OPS-113
| proposal.md §2.1 T3]

#### Scenario: countdown crosses the 2-minute red threshold

- **Given** `<CotizacionPanel data={cotizacion} secondsLeft={n} />` is
  mounted with `secondsLeft` decrementing once per second via
  `useCountdown(15 * 60)`
- **When** `useCountdown` transitions `secondsLeft` from `120` to `119`
  (2-minute threshold crossed)
- **Then** the countdown `<div>` MUST render with `className="text-destructive"`
  (shadcn semantic token), MUST show the `<AlertTriangle />` icon
  beside the countdown text, and MUST set `role="alert"`
- **And** the outer `<div>` MUST carry `aria-live="polite"` so screen
  readers announce each subsequent tick as the countdown approaches
  zero
- **And** MUST show the message `cotizar.countdown.expiring_soon`
  ("Cotización expira pronto — confirma o recalcula") when
  `secondsLeft < 120` and `secondsLeft > 0`
- **And** MUST show `cotizar.countdown.expirada` ("Cotización expirada
  — recalculando…") when `secondsLeft === 0` (the SWR re-fetch will
  produce a fresh `vigente_hasta` and the countdown resets).

### REQ-OPS-147 — `formatCOP(value)` for all monetary rendering (no raw `.toLocaleString('es-CO') + '$'`)

The system SHALL import and use `formatCOP(value: number): string` from
`apps/electron-sucursal/src/features/caja/lib/format.ts:31` (F3.3
shipped, tested at `format.test.ts:15-29`) for every monetary value
rendered by `<CotizacionPanel />`. Raw `.toLocaleString('es-CO')` +
literal `'$'` concatenation MUST NOT appear in
`<CotizacionPanel />`, `<SalidaPanel />`, or any new component this PR
introduces. [Cite: proposal.md §2.1 R2 | F3.3 format.ts:31]

#### Scenario: COP value `12300.00` formats as `"$ 12.300"` (es-CO locale)

- **Given** `formatCOP` is imported from `features/caja/lib/format.ts`
  and the test fixture is the canonical F3.3 verbatim test
- **When** `<CotizacionPanel />` renders `data.total = 12300`
- **Then** the visible text MUST equal `"$ 12.300"` (es-CO locale,
  thousands separator `.`, no decimals for COP)
- **And** an automated grep `git grep -nE
  "toLocaleString\\('es-CO'\\)" apps/electron-sucursal/src/features/operacion/`
  MUST return zero matches
- **And** an automated grep `git grep -nE "\\\$\\{?[^}]*\\.toLocaleString"`
  in the same directory MUST return zero matches.

### REQ-OPS-148 — `cotizar.errors.iva_no_configurado` surfaces a non-blocking banner (no crash)

The system SHALL render the `cotizar.errors.iva_no_configurado` info
banner in `<CotizacionPanel />` (NOT a thrown error, NOT a blank
panel) when `useCotizacion` returns
`{error: ParkosHttpError(500)}` from
`GET /operacion/cotizar?uuid_ingreso=X` with the body
`{"error": "iva_no_configurado"}`. The banner MUST be localizable via
the i18n key `cotizar.errors.iva_no_configurado` ("IVA no configurado
en el sistema. Contacte al administrador."), MUST NOT crash the
operator dashboard, and MUST keep the rest of the UI (occupancy strip,
ingreso form) usable. [Cite: proposal.md §2.1 R2 + Risks R3 |
plan.md:1665 KD-IVA]

#### Scenario: branch without `impuestos.IVA` seeded renders banner, not crash

- **Given** the branch DB has NO row in `prod.impuestos` with
  `codigo='IVA'` (pre-MIGRATION 0026 state, or KD-IVA blocker before
  HU-F14.2 Parte II seeding)
- **When** the operator submits a placa and `useCotizacion(X)` receives
  the 500 response with body `{"error": "iva_no_configurado"}`
- **Then** `<CotizacionPanel />` MUST render the
  `cotizar.errors.iva_no_configurado` banner with the localized message
- **And** the panel MUST NOT render the `<dl>` breakdown
- **And** the panel MUST NOT render the countdown (no
  `vigente_hasta` to count down to)
- **And** the operator dashboard MUST remain usable: the operator can
  see the occupancy strip (REQ-OPS-130), the ingreso form, and the
  other dashboard panels.

### REQ-OPS-149 — `useCotizacion.test.ts` covers rotación, mensualidad, and tiempo ≥ tarifa-plena

The system SHALL add 3 NEW hook tests to
`apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.test.ts`
covering the canonical discriminated union (per plan.md:1689): (1)
`rotación` mocks `cobrar:true` with the full fiscal breakdown and
asserts the SWR key + parser path; (2) `mensualidad` mocks
`cobrar:false` with `motivo:'mensualidad_vigente'` and asserts the
short-circuit branch; (3) `tiempo ≥ tarifa-plena` mocks a high
`tiempo_minutos` (≥ the tarifa_plena threshold, e.g. 24 hours = 1440)
with `total === valor_plena` and asserts no fraction accumulation.
The existing 3 tests in `useCotizacion.test.ts` (C1: null key no fetch,
C2: fetcher-closure, C3: 401 → useAuthStore.clear) MUST be migrated to
the canonical Zod schema mocks. The 4 existing tests in
`SalidaPanel.test.tsx` MUST be migrated to canonical schema mocks
asserting `formatCOP(x)` output (literal `"$ 50.000"` fixture) instead
of `'$'+x.toLocaleString('es-CO')`. [Cite: proposal.md §2.1 T4 + R4 +
R5 | plan.md:1689]

#### Scenario: all 6 useCotizacion tests pass with the canonical schema

- **Given** `useCotizacion.ts` exposes the rewritten Zod discriminated
  union schema (R1) and `useCotizacion.test.ts` declares the 3 migrated
  tests + 3 new tests (total 6)
- **When** `pnpm --filter electron-sucursal test -- --run
  useCotizacion` executes
- **Then** all 6 tests MUST pass (3 migrated: null key no fetch /
  fetcher-closure / 401 logout; 3 new: rotación / mensualidad /
  tiempo ≥ tarifa-plena)
- **And** the `SalidaPanel.test.tsx` 4 existing tests MUST pass with
  canonical schema mocks (assertions on `formatCOP` literal `"$ 50.000"`,
  not raw `'$'+x.toLocaleString`)
- **And** total new + migrated test count is 10 across both files; the
  coverage report MUST reflect ≥90% lines and ≥85% branches per
  REQ-OPS-150.

### REQ-OPS-150 — Per-file coverage thresholds added atomically with file creation

The system SHALL add 3 entries to `vitest.config.ts`
`perFileThresholds` (F4.x precedent at `vitest.config.ts:25-43`)
atomically with the file creation in this PR:
`apps/electron-sucursal/src/lib/validation/placaTolerante.ts`
(lines ≥95, functions ≥95, branches ≥90 — pure function mirror of
`placa.ts` thresholds);
`apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts`
(lines ≥90, functions ≥90, branches ≥85 — SWR hook + Zod
discriminated union);
`apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.tsx`
(lines ≥90, functions ≥90, branches ≥85 — presentational with two
render paths). [Cite: proposal.md §2.1 R6 | F4.1 vitest.config.ts
precedent]

#### Scenario: vitest gate passes with the 3 new per-file thresholds

- **Given** the 3 new per-file threshold entries are present in
  `vitest.config.ts` AND the 3 corresponding implementation files exist
  with their tests
- **When** `pnpm --filter electron-sucursal test:coverage` executes
- **Then** the coverage gate MUST pass for all 8 per-file thresholds
  (5 existing + 3 new)
- **And** any missing branch (e.g. the `cobrar === false` path
  untested) MUST drop coverage below threshold and fail CI before the
  PR can land
- **And** the threshold MUST be enforced from PR creation (no
  retrofitted gates after merge).

### REQ-OPS-151 — Client-side placa variant generation bounds the search space

The system SHALL export `generarVariantesTolerantes(placa: string):
readonly string[]` from
`apps/electron-sucursal/src/lib/validation/placaTolerante.ts` as a
pure deterministic function. The function MUST return the input placa
as the first entry (no-tolerance happy path), MUST emit at most one
variant per (position, confusable-class) pair (binary `O↔0`,
`I↔1`, `B↔8` — 3 confusable pairs), MUST skip two-position variants
if single-position variants exceed 50 entries (bounded heuristic),
and MUST bound the worst-case combinatorial explosion to ≤729 variants
(6 positions × 3 confusable classes × 3 binary replacements). The
realistic case (1 typo) yields ≤13 variants and the hook early-exits
on first hit. [Cite: proposal.md §2.1 R7 + §3.1 | F6.1 design.md
Decision Path 1 precedent]

#### Scenario: `ABC123` with no typo returns 1 variant; `AB0123` with 1 typo returns ≤13 variants

- **Given** `generarVariantesTolerantes` is imported from
  `apps/electron-sucursal/src/lib/validation/placaTolerante.ts`
- **When** the function is called with the canonical test fixtures
- **Then** `generarVariantesTolerantes('ABC123')` MUST return
  `['ABC123']` exactly (no confusables present in the input; 1
  variant, no false positives)
- **And** `generarVariantesTolerantes('AB0123')` MUST return
  `['AB0123', 'ABC123']` (1 confusable at position 3: `0↔O` — 2
  variants)
- **And** `generarVariantesTolerantes('OBC113')` MUST return ≤3
  variants (1 confusable at position 1: `O↔0`, plus the input)
- **And** the worst-case test fixture (a 6-char placa with 3
  confusables at all positions) MUST yield ≤729 variants, with the
  bounded heuristic skipping two-position variants if single-position
  variants exceed 50
- **And** `buscarIngresoTolerante` MUST short-circuit on the first
  hit, so realistic operator flows trigger ≤3 backend queries per
  placa.

## Out of scope

- **HU-F7.2 — Registrar salida**: separate change
  (`fase-7-2-registrar-salida`). `POST /operacion/salidas` +
  `POST /operacion/salidas/mensualidad` integration in `SalidaFlow` and
  `SalidaMensualidad`.
- **HU-F7.3 — Tiquetes de salida**: separate change
  (`fase-7-3-tiquetes-salida`). CU-15S (after pago, per DEC-SUC-27) and
  CU-15SM (immediate after monthly confirmation).
  `escposBuilder.build('salida', payload)` +
  `escposBuilder.build('salida_mensualidad', payload)`.
- **Tiquete CU-15S printing deferred to Fase 8**: `<CotizacionPanel />`
  `onConfirmar` only opens the pago drawer (REQ-OPS-138); the actual
  `escposBuilder.build('salida', payload)` call happens at pago
  confirmation (DEC-SUC-27 verbatim reordering).
- **KD-IVA seeding**: `impuestos.IVA` seeding is owned by HU-F14.2
  Parte II (not in scope of F7.1). Until seeded, every cotizar returns
  `500 iva_no_configurado` — `<CotizacionPanel />` MUST render the
  `cotizar.errors.iva_no_configurado` banner without crashing (REQ-OPS-148).
- **Server-side placa tolerance endpoint**: per F6.1 Path 1 precedent,
  tolerance is a renderer concern only. No backend endpoint changes;
  no PL/pgSQL additions; no migration. F7.1 only consumes the existing
  `GET /operacion/ingresos?placa=X` endpoint (F1.6 already mounted).
- **Mensualidad resolution refactor**: `resolve_active_subscription_for_exit`
  server-side (F1.4) stays untouched. The `cobrar:false` branch is
  purely a client render concern.
- **Vite cache invalidation post-merge**: handled by AGENTS.md
  post-merge script (Kill Vite on 5173 + restart with `--force`); not
  part of the F7.1 PR.
- **Release branch + tag**: per gitflow, this change goes to `dev` only;
  release branch + tag are post-merge operational concerns, not PR
  scope.

## Drift reconciliation traceability

The schema drift between the current `useCotizacion.ts` /
`SalidaPanel.tsx` (6-field flat shape) and the canonical F1.8
discriminated-union contract is captured by the following traceability
matrix. **The backend canonical contract (REQ-OPS-022..025) is
unchanged** — only the client consumer changes.

| Existing requirement | Status | F7.1 delta | Rationale |
|---|---|---|---|
| **REQ-OPS-022** (`GET /operacion/cotizar?uuid_ingreso` returns fiscal breakdown with `{cobrar:true, subtotal, iva, total, tiempo_minutos, tarifa_uuid, vigente_hasta}`) | UNCHANGED on the server. | `<CotizacionPanel />` consumes the canonical response verbatim per REQ-OPS-143. | The canonical wire shape is F1.8's authoritative truth (REQ-OPS-022..025). The drift was on the client consumer (`useCotizacion.ts` Zod schema did not match); F7.1 brings the consumer in line. |
| **REQ-OPS-023** (mensualidad short-circuit: `{cobrar:false, motivo:"mensualidad_vigente"}`) | UNCHANGED on the server. | `<CotizacionPanel />` renders the mensualidad info banner (REQ-OPS-143 scenario 2). | The `cobrar:false` branch is now rendered by the client instead of silently rendering an empty `<dl>` against the flat schema. |
| **REQ-OPS-024** (typed errors with precedence `ingreso_no_encontrado > tarifa_no_vigente > iva_no_configurado`) | UNCHANGED on the server. | `useCotizacion` maps the 4 HTTP status codes (200/404/422/500) to typed React states; `cotizar.errors.iva_no_configurado` renders per REQ-OPS-148. | The client surface is enriched (4 error i18n keys: `ingreso_no_encontrado`, `tarifa_no_vigente`, `iva_no_configurado`, `cotizacion_expirada`) but the server precedence is the source of truth. |
| **REQ-OPS-025** (`calcular_cotizacion` declares STABLE or VOLATILE + AST walk rejects mutations) | UNCHANGED on the server. | Not directly relevant — the AST walk protects the migration body, not the client consumer. | F7.1 does not modify any Alembic migration; the F1.8 PL/pgSQL function stays verbatim. |
| **REQ-OPS-132** (fetcher-closure `useCotizacion` SHELL — `useSyncEstado` precedent) | Augmented, NOT replaced. | The current `useCotizacion.ts` impl lines 96-105 (401 → useAuthStore.clear + `parkos:auth:cleared` event) MUST be preserved verbatim in the rewritten hook (REQ-OPS-145). | REQ-OPS-132 was the F11.1 fetcher-closure precedent; F7.1 extends it with the canonical Zod schema rewrite. The 401-clear invariant is preserved. |

**WHY the existing requirements are unchanged**: the drift was on the
client consumer (Zod schema + `<dl>` rendering), not on the backend
contract. The canonical F1.8 wire shape has been the source of truth
since 2026-09-14 (REQ-OPS-022..025 in `operations/spec.md:441-502`,
mirrored verbatim in `backend/.../schemas/operacion.py:251-263`). F7.1
brings the renderer in line with the canonical contract — a pure
renderer-side reconciliation. No backend change is required (no
migration, no PL/pgSQL change, no endpoint addition).

## Acceptance

The F7.1 PR is mergeable when ALL of the following hold:

- `<CotizacionPanel />` renders all canonical fields including the
  mensualidad short-circuit (`cobrar:false` info banner, no `<dl>`)
  and the rotación path (`cobrar:true` with full breakdown). [REQ-OPS-143]
- `buscarIngresoTolerante('AB0123')` resolves to the unique ingreso
  `ABC123` via the `O↔0` tolerance map; the function lives in
  `placaTolerante.ts`, separate from `placa.ts` per DEC-SUC-22.
  [REQ-OPS-144]
- `useCotizacion(X)` polls `GET /operacion/cotizar?uuid_ingreso=X` at
  1s cadence, clears auth on 401, and surfaces
  `cotizar.errors.iva_no_configurado` as a non-blocking banner when
  the backend returns 500. [REQ-OPS-145, REQ-OPS-148]
- The countdown turns `text-destructive` + `<AlertTriangle />` with
  `aria-live="polite"` ticks when `secondsLeft < 120`. [REQ-OPS-146]
- `formatCOP` is the only monetary formatter used; the
  `git grep` for `.toLocaleString('es-CO')` returns zero matches in
  the operacion feature tree. [REQ-OPS-147]
- All 10 hook/component tests pass (3 migrated + 3 new in
  `useCotizacion.test.ts` + 4 migrated in `SalidaPanel.test.tsx`).
  [REQ-OPS-149]
- `vitest run --coverage` meets all 8 per-file thresholds (5 existing
  + 3 new in `vitest.config.ts`). [REQ-OPS-150]
- `axe-core` reports 0 violations on `<CotizacionPanel />` (WCAG 2.1
  AA, RNF-022). [REQ-OPS-130 + REQ-OPS-146]
- `pnpm typecheck`, `pnpm lint`, `pnpm test` exit 0 across the
  `electron-sucursal` workspace.
- Final diff `≤ 800 LOC` per the preflight budget — no
  `size:exception` needed.