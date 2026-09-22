# Proposal: HU-F7.2 — Registrar salida (rotación + mensualidad) — UI integration

> **Change**: `fase-7-2-registrar-salida`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F7.2 (Fase 7 — Salida y cálculo de tarifa, UI pivot)
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC`, strict_tdd=`true`, chain_strategy=`n/a`
> **Git identity**: `Parkos Dev <dev@parkos.local>` (per AGENTS.md gitflow). No AI attribution in commits.
> **Inputs read**: `plan.md` lines 1700-1741 (F7.2 block + sequence diagram); lines 396-410 (DEC-SUC-21 derivation model); lines 411-419 (DEC-SUC-23/24/27 + amortización invariants); lines 813-815 (HU-F1.7 backend canonical source); `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/proposal.md` (F1.7 DEC-MONO-01 + REQ-OPS-042..052); `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:322` (live `POST /operacion/salidas` handler with `SalidaCreateForzado`/`SalidaReadForzado`); `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py:392-422` (`SalidaReadForzado` shape with `tipo_salida` derivation); `openspec/changes/archive/2026-09-19-fase-7-1-busqueda-tolerante-cotizacion/proposal.md` (F7.1 archive — CotizacionPanel + REQ-OPS-143..151); `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (F7.1 host with `handleOpenPago` wired to `open('pago', pagoAnchorId)`); `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.tsx` (F7.1 presentational with rotación/mensualidad branches + countdown); `apps/electron-sucursal/src/features/operacion/components/SalidaSheet.tsx` (F7.1 sheet wrapper); `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` (F7.1 SWR polling); `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts` (REQ-OPS-138 single-drawer store); `openspec/specs/operations/spec.md` lines 5825-5910 (F7.1 REQ-OPS-143..151 baseline).
> **Skills loaded**: `sdd-propose` (this proposal phase), `_shared/sdd-phase-common` (Section B/C/D envelope).

## 1. Intent

HU-F7.2 closes the F7.1 → CU-04 pivot: from a confirmed cotización (rotación) or mensualidad detection, the operator confirms the salida. The backend `POST /operacion/salidas` (F1.7, REQ-OPS-042..052, already shipped) performs the append-only INSERT into `prod.salidas` with server-side `tipo_salida` derivation, releases the cupo immediately via `cantidad_vehiculos_sucursal` recompute, and returns `uuid_salida` + `tipo_salida` to the renderer. F7.2 wires the F7.1 `<CotizacionPanel onConfirmar />` callback to that endpoint with `Idempotency-Key` per DEC-SUC-04. For rotación: response `tipo_salida='ROTACION'` → proceed to PagoModal (HU-F8.1, separate change). For mensualidad: response `tipo_salida='MENSUALIDAD'` → print tiquete CU-15SM immediately (HU-F7.3, separate change).

**Critical drift reconciliation** (between `plan.md` and the merged `dev` branch):
- `plan.md` lines 1715, 1724 references `POST /operacion/salidas/mensualidad` and `mensualidad_no_vigente` (400). F1.7's DEC-MONO-01 consolidated to **ONE** endpoint `POST /operacion/salidas` with `tipo_salida = 'MENSUALIDAD' | 'ROTACION'` derived server-side from F1.8's `cobrar` flag (see `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/proposal.md` decision D-HU-F1.7-1/DEC-MONO-01). `grep -r 'salidas/mensualidad' backend/` → 0 matches; `grep -r 'mensualidad_no_vigente' backend/` → 0 matches.
- F7.2 reflects the actual shipped endpoint. Both `SalidaFlow` (rotación) and `SalidaMensualidad` (mensualidad) call the same `POST /operacion/salidas` — the response's `tipo_salida` discriminates downstream UX (PagoModal vs. CU-15SM print).
- The user's original brief was based on `plan.md` text written before F1.7's DEC-MONO-01 was ratified. This proposal honors the merged reality, not the plan text. Drift is called out as Risk R-DRIFT (§6).

The user-facing payoff: from a confirmed cotización, one click fires a backend mutation that releases the cupo, persists the lifecycle event without ever persisting the monetary amount (DEC-SUC-23), and routes the operator to the next step without page navigation.

## 2. Scope

### 2.1 In scope (T1..T3 + I1..I2 + E1)

- **T1 — `SalidaFlow.tsx`** (NEW): the F7.1 → CU-04 pivot orchestrator. Mounts the existing `<CotizacionPanel />` with `onConfirmar` wired to `useRegistrarSalida({ modo: 'rotacion', uuid_ingreso, uuid_cotizacion_ref })`. After 201 response → routes to PagoModal drawer via `useDashboardDrawerStore.open('pago', pagoAnchorId)` (REQ-OPS-138 invariant preserved). On 409 `salida_duplicada` → renders a non-blocking banner + disables the confirm button. Inherits all F7.1 invariants: WCAG 2.1 AA, axe-core, REQ-OPS-138 single-drawer, formatCOP reuse, no auto-submit.
- **T2 — `SalidaMensualidad.tsx`** (NEW): a 1-screen shortcut page mounted when `<CotizacionPanel />` short-circuits to `cobrar: false`. Renders the existing F7.1 mensualidad banner + a "Confirmar salida por mensualidad" button. Submit calls `useRegistrarSalida({ modo: 'mensualidad', uuid_ingreso })` against the same `POST /operacion/salidas` endpoint. After 201 → routes to tiquete CU-15SM print (F7.3 owns the print pipeline; F7.2 emits the `bridge.imprimir('salida_mensualidad', payload)` event envelope only — F7.3 fills the payload shape).
- **T3 — `SalidaSheet` wrapper composition** (UPDATE): `<SalidaSheet />` (F7.1) wraps `<SalidaPanel />` which composes `<CotizacionPanel />` which exposes `onConfirmar`. The composition chain is: `<SalidaSheet />` → `<SalidaPanel />` → `<CotizacionPanel onConfirmar={handleRegistrarSalida} />` where `handleRegistrarSalida` dispatches `useRegistrarSalida()`. No new component/visual container is added — `SalidaFlow` and `SalidaMensualidad` are hooks/orchestrators, not new visible panels.
- **I1 — `useRegistrarSalida.ts`** (NEW): SWR `useSWRMutation` hook (no polling, mutation-only). Endpoint `POST /api/v1/operacion/salidas` (F1.7, REQ-OPS-042). Body `{ uuid_ingreso, uuid_cotizacion_ref? }`. Headers: `Idempotency-Key` = `sha256(method + path + canonicalJson(body))` (DEC-SUC-04 + DEC-IDEM-01 reuse from F1.6). Returns `{ trigger, isMutating, error, data }`. The mutation result `data` is `SalidaReadForzado` (F1.7 schema) — discriminated by `tipo_salida`. Hook auto-detects `modo` from input.
- **I2 — `idempotency.ts`** (NEW): pure helper `buildIdempotencyKey(method: string, path: string, body: unknown): string` returning `sha256` hex. Reuses the canonical JSON serializer from `apps/electron-sucursal/src/features/operacion/lib/canonicalJson.ts` (F7.1 shipped, test mirror at `canonicalJson.test.ts`) — same input always produces same hash, independent of property order (RFC 8785 / JSON canonicalization).
- **E1 — `e2e/salida.spec.ts`** (NEW): Playwright e2e with 3 cases per `plan.md:1729`:
  1. Salida rotación: cotización vigente → confirm → expect 201 → expect `tipo_salida='ROTACION'` → expect `PagoSheet` drawer opened (REQ-OPS-138 anchor restored); expect cupo decremented in `<OcupacionPanel />` within `refreshInterval: 10000` (F4.3).
  2. Salida mensualidad: mensualidad vigente → confirm → expect 201 → expect `tipo_salida='MENSUALIDAD'` → expect tiquete CU-15SM print envelope fired (mocked `bridge.imprimir` spy).
  3. Doble clic idempotente: confirm twice in <500ms → expect 201 + 1 `prod.salidas` row (verified via API GET or via backend log mock) — server-side cache deduplicates by `Idempotency-Key`.

### 2.2 Out of scope

- **HU-F8.1 — PagoModal (rotación → CU-04)**: separate change. F7.2 only triggers `open('pago', anchorId)` after a successful 201; the modal logic itself lives in F8.1.
- **HU-F7.3 — Tiquetes CU-15S + CU-15SM print pipeline**: separate change. F7.2 fires the print event envelope (typed) for the mensualidad branch only; F7.3 owns the `escposBuilder.build('salida_mensualidad', payload)` builder + `bridge.imprimir` payload shape + DEC-SUC-27 verbatim reordering (CU-15S prints after pago, not at salida).
- **Server-side `Idempotency-Key` cache logic**: backend owns. F1.6 already shipped `IdempotencyKeyMiddleware` (PR2) with 24h TTL; F7.2 only sends the header.
- **New `POST /operacion/salidas/mensualidad` endpoint**: does not exist and will not be created. Drift resolution: plan.md is stale; F1.7 DEC-MONO-01 consolidates. The frontend calls the SAME endpoint for both modes; downstream UX is discriminated by `response.tipo_salida`.
- **Mensualidad detection client-side refactor**: `CotizacionPanel` already short-circuits on `data.cobrar === false` (REQ-OPS-143). F7.2 only consumes that state via `onConfirmar`.
- **Backend changes**: zero. F1.7 ships the canonical endpoint + `SalidaReadForzado` schema; F7.2 only consumes.
- **`vigente_hasta` countdown re-validation on confirm**: the existing `useCountdown(15 * 60)` in `CotizacionPanel` (REQ-OPS-146) governs the operator UX. If the countdown hits 0 before the operator clicks Confirm, `CotizacionPanel` re-fetches via `onRecalcular` (REQ-OPS-145). Backend independently re-validates via V5 (REQ-OPS-047) and returns 422 `cotizacion_expirada` if stale — frontend surfaces the banner "El cálculo expiró, recalculando…" and re-renders.
- **Vite cache invalidation post-merge**: handled by AGENTS.md post-merge script. Not part of the F7.2 PR.
- **Release branch + tag**: per gitflow, this change goes to `dev` only.

## 3. Approach

### 3.1 Decision Path 1 — SalidaFlow as composition + useSWRMutation (F7.1 inline-composition precedent)

`<SalidaFlow />` is **not** a new visual component. It is a hook + composition layer that connects F7.1's `<CotizacionPanel onConfirmar={...} />` to F1.7's backend endpoint. The composition chain stays inline (per F7.1 R2 precedent at `SalidaPanel.tsx:179-191`):

```typescript
// Conceptual composition (SalidaPanel.tsx after F7.2 lands)
<CotizacionPanel
  data={cotizacion}
  error={cotError}
  secondsLeft={secondsLeft}
  onConfirmar={handleRegistrarSalida}  // F7.2 wires here
  onRecalcular={() => void refresh()}
/>
```

`handleRegistrarSalida` invokes `useRegistrarSalida({ uuid_ingreso, uuid_cotizacion_ref })().trigger()` with `Idempotency-Key` set. On `data.tipo_salida === 'ROTACION'` → `open('pago', pagoAnchorId)` (REQ-OPS-138). On `data.tipo_salida === 'MENSUALIDAD'` → fire `bridge.imprimir` event envelope for CU-15SM (typed payload, F7.3 fills the shape).

### 3.2 Decision Path 2 — `useSWRMutation` for the discrete mutation (vs raw `fetch`)

`useSWRMutation` (SWR's first-class mutation hook) is the canonical mutation surface in this codebase (precedent: `useIngresoActivo.ts` consumer pattern at F6.1, `useCotizacion.ts:170` `mutate()` pattern). It provides `trigger`, `isMutating`, `error`, `data` in a single object — eliminates ad-hoc `useState<{loading, error, data}>` plumbing. SWR's `dedupingInterval` is irrelevant here (single discrete POST, no caching desired), so the hook runs at default settings.

Alternative rejected: raw `fetch` in event handler — duplicates `parkosFetch` error handling (401/403/network) and breaks the F1.2 `Idempotency-Key` middleware integration test surface.

### 3.3 Decision Path 3 — Idempotency via SHA-256 closure (DEC-SUC-04 verbatim)

```typescript
// apps/electron-sucursal/src/features/operacion/lib/idempotency.ts
import { canonicalJson } from './canonicalJson';  // F7.1 shipped
export function buildIdempotencyKey(method: string, path: string, body: unknown): string {
  const payload = `${method.toUpperCase()}\n${path}\n${canonicalJson(body)}`;
  return sha256Hex(payload);  // Web Crypto API (browser) — see pure-helper test below
}
```

Pure function: same `(method, path, body)` triple always returns the same hex digest. Independent of property order, whitespace, or platform byte-order. Mirrors `canonicalJson` precedent at `apps/electron-sucursal/src/features/operacion/lib/canonicalJson.ts` (F7.1, RFC 8785).

The hook calls `buildIdempotencyKey('POST', '/api/v1/operacion/salidas', body)` once per `trigger()` invocation, captures the digest, and sends it as the `Idempotency-Key` HTTP header. Server-side `IdempotencyKeyMiddleware` (PR2, F1.6) caches by header for 24h; re-submission within that window returns the cached 201 without re-INSERT.

### 3.4 Drift Reconciliation — One Endpoint, Two UX Paths

| Aspect | `plan.md` text (line 1715, 1724) | F1.7 reality (operacion.py:322) | F7.2 alignment |
|---|---|---|---|
| Endpoint | `POST /operacion/salidas` + `POST /operacion/salidas/mensualidad` | `POST /operacion/salidas` (single, DEC-MONO-01) | One endpoint; F7.2 calls the same `POST /operacion/salidas` for both `modo='rotacion'` and `modo='mensualidad'`. |
| `tipo_salida` source | Client-derived from pre-classification | Server-derived from F1.8 `cobrar` flag | Client is **indifferent** to the path; reads `response.tipo_salida` and routes. |
| `mensualidad_no_vigente` (400) | Listed as a 400 error on `/salidas/mensualidad` | Does not exist (zero grep) | Backend never returns `mensualidad_no_vigente`; the mensualidad path either succeeds (with `tipo_salida='MENSUALIDAD'`) or fails for a different reason (V2 `subscripcion_inactiva_o_vencida` 422, V5 `tarifa_vigente_no_encontrada` 422). |
| Error surface | Plan.md enumerates 3 codes | F1.7 handler returns: 400 `missing_sucursal_context`, 403 `tenant_scope_violation`, 404 `ingreso_no_encontrado`, 409 `salida_duplicada`, 422 set (V2/V3/V4/V5), 500 `iva_no_configurado` (post-0026: never) | F7.2 UI error handler covers the full F1.7 taxonomy. `mensualidad_no_vigente` is removed from UI strings. |

## 4. Affected files

| File | Action | LOC est. | Notes |
|---|---|---|---|
| `apps/electron-sucursal/src/features/operacion/pages/SalidaFlow.tsx` | NEW | 90 | Orchestrator hook composition (Decision Path 1). Calls `useRegistrarSalida()` + `useDashboardDrawerStore.open('pago', anchorId)` on `tipo_salida='ROTACION'` + `bridge.imprimir('salida_mensualidad', {})` event on `tipo_salida='MENSUALIDAD'`. REQ-OPS-138 invariant preserved. |
| `apps/electron-sucursal/src/features/operacion/pages/SalidaMensualidad.tsx` | NEW | 50 | 1-screen page (Decision Path 2). Mounts `<CotizacionPanel />` mensualidad branch (already short-circuits per REQ-OPS-143). Submit button calls `useRegistrarSalida({ modo: 'mensualidad' })`. After 201 → print envelope. |
| `apps/electron-sucursal/src/features/operacion/hooks/useRegistrarSalida.ts` | NEW | 70 | `useSWRMutation` hook (Decision Path 2). Endpoint: `POST /api/v1/operacion/salidas` (F1.7 REQ-OPS-042). Body: `{ uuid_ingreso, uuid_cotizacion_ref? }`. Header: `Idempotency-Key` from `idempotency.ts`. 401 → `useAuthStore.clear()` (preserved F7.1 invariant at `useCotizacion.ts:155-159`). |
| `apps/electron-sucursal/src/features/operacion/lib/idempotency.ts` | NEW | 25 | `buildIdempotencyKey(method, path, body)` — sha256 hex of `method\npath\ncanonicalJson(body)`. Pure function. Unit test for property-order independence. |
| `apps/electron-sucursal/src/features/operacion/api/salidaApi.ts` | NEW | 40 | Thin wrapper composing `parkosFetch` + the hook's input shape. Mirrors F7.1 `ingresoApi.ts` precedent. Exports Zod schema `SalidaCreateForzado` mirror + `SalidaReadForzado` discriminated by `tipo_salida`. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` | UPDATE | +20 (delta) | Replace `handleOpenPago = open('pago', pagoAnchorId)` (line 115-117) with `handleRegistrarSalida` that calls the hook and routes by `response.tipo_salida`. Mensualidad branch: fire print envelope. `useId` for `pagoAnchorId` preserved. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaSheet.tsx` | UPDATE | +5 (delta) | Pass through `initialPlaca` + pass-through `uuid_ingreso` from `useDashboardDrawerStore` (new field). Sheet composition unchanged. |
| `apps/electron-sucursal/e2e/salida.spec.ts` | NEW | 100 | 3 scenarios per `plan.md:1729`: rotación, mensualidad, doble clic idempotente. Playwright + axe-core WCAG gate. |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | UPDATE | +6 keys (delta) | `salida.confirmar_rotacion`, `salida.confirmar_mensualidad`, `salida.errors.salida_duplicada`, `salida.errors.network`, `salida.errors.cotizacion_expirada`, `salida.success.uuid`. Locale es-CO primary. |
| **Total new LOC** | | **+375** | Within 800 LOC budget; no `size:exception` needed. |
| **Total updated LOC (deltas)** | | **+31** | |
| **Grand total LOC** | | **~406** | |

## 5. Dependencies

### 5.1 Already-merged prerequisites (verified on `dev`)

- **F1.7 — `POST /operacion/salidas` backend** (merged, `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/`): ships the canonical endpoint, `SalidaCreateForzado` + `SalidaReadForzado` schemas, V1..V5 validations, DEC-MONO-01 single-endpoint, server-side `tipo_salida` derivation, partial unique index `one_exit_per_ingreso` for 409 mapping. **Required** — the entire F7.2 backend contract.
- **F7.1 — Cotización + tolerancia** (merged, `openspec/changes/archive/2026-09-19-fase-7-1-busqueda-tolerante-cotizacion/`): ships `<CotizacionPanel />`, `useCotizacion`, `placaTolerante`, `buscarIngresoTolerante`, REQ-OPS-143..151 baseline. **Required** — the host component + discriminated-union data source.
- **F1.8 — `GET /operacion/cotizar`** (merged): ships the canonical cotizar endpoint that F7.1 consumes; F1.7's V5 (REQ-OPS-047) calls the same PL/pgSQL function. **Required transitively** for the `cobrar` flag that drives `tipo_salida` derivation.
- **F1.6 — `IdempotencyKeyMiddleware`** (merged, PR2): the backend 24h cache middleware. **Required** — F7.2 only sends the header.
- **F4.3 — `useOcupacion` polling** (merged): ships `OPERACION_REFRESH_INTERVAL_MS=10000` for the live occupancy strip. **Required** to verify cupo is released after the INSERT.
- **F2.x — `parkosFetch` + `useAuthStore`** (merged): the canonical HTTP client + auth store. **Required** — `useRegistrarSalida` composes both.
- **F6.1 — `getIngresosByPlaca`** (merged): the placa lookup used by `SalidaPanel`'s `buscarIngresoTolerante` glue. **Required** — F7.2 inherits the placa resolution chain.
- **`useDashboardDrawerStore`** (F6.1, `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts`): REQ-OPS-138 single-drawer store. **Required** — F7.2's `open('pago', anchorId)` call goes through it.

### 5.2 Forward-dependents (do NOT block F7.2)

- **HU-F8.1 — PagoModal**: consumes F7.2's `open('pago', pagoAnchorId)` trigger after `tipo_salida='ROTACION'` 201.
- **HU-F7.3 — Tiquetes CU-15S/SM**: consumes F7.2's `bridge.imprimir('salida_mensualidad', payload)` event envelope after `tipo_salidad='MENSUALIDAD'` 201. F7.3 owns the payload shape + `escposBuilder`.
- **HU-F1.2 — Backend idempotency cache** (already shipped as F1.6 PR2): validates the 24h dedup window the F7.2 frontend relies on.

### 5.3 Skill + tooling prerequisites

- `react` skill (loaded by parent) — D-073 stack, Vite 5, shadcn/ui único, RHF + Zod, i18next es-CO, WCAG 2.1 AA via axe-core.
- `shadcn` skill (loaded by parent) — atomic-design, `<Sheet>` primitive reuse, `<Card>`/`<Button>` semantic markup.
- `python` skill (loaded by parent for backend reading) — FastAPI/Pydantic/SQLAlchemy 2.0 async conventions, but F7.2 ships no backend code.

## 6. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **`salidas.estado` does not flip from `PENDIENTE_PAGO` to `PAGADO` after Fase 8 if F8.1 fails** — ingreso queda "huérfano" con salida pendiente, cupo no se libera completamente. | MED | (a) DEC-SUC-23: `salidas` has NO `valor` column; only `estado` flips at pago completion (F8.1 owns that UPDATE). (b) F7.2's INSERT never blocks on this — verify-phase tests assert F7.2 only fires INSERT (no UPDATE). (c) F8.1 carry-over risk tracked separately. |
| **R2** | **Doble clic could fire 2 POSTs if the network is slow and the hook's in-flight guard races** — backend `Idempotency-Key` cache should dedup, but UI must also disable the button during the mutation. | LOW | (a) `useSWRMutation` exposes `isMutating` — `<CotizacionPanel />` disables the Confirm button while `isMutating === true` (CotizacionPanel wraps the button, parent passes `isMutating` via prop). (b) `Idempotency-Key` derived from `buildIdempotencyKey(...)` — same body → same key, server dedup. (c) e2e test E1-S3 verifies only 1 row created after double-click. |
| **R3** | **`useCountdown` expires between Confirm click and 201 response** — backend V5 (REQ-OPS-047) re-validates; if stale, returns 422 `cotizacion_expirada`. UI must surface a non-blocking "Recalcular y reintentar" path. | LOW | (a) `<CotizacionPanel />` countdown already triggers `onRecalcular` (REQ-OPS-145) when `secondsLeft === 0`. (b) `useRegistrarSalida` on 422 maps to a localized banner (i18n key `salida.errors.cotizacion_expirada`). (c) Backend's V5 lock continuity (KD-S7) minimizes the window — INSERT happens in the same TX as the `calcular_cotizacion` call. |
| **R4** | **Mensualidad path prints CU-15SM but DEC-SUC-27 mandates the print fires after pago for CU-15S** — F7.2 only fires the mensualidad print envelope, but a regression could fire both. | MED | (a) `useRegistrarSalida` reads `response.tipo_salida` and only fires `bridge.imprimir('salida_mensualidad', {})` when `tipo_salida === 'MENSUALIDAD'`. (b) AST walk `tests/static/test_salida_handler_no_print_when_rotacion.ts` (verify-phase) asserts no `bridge.imprimir` call exists in the rotación branch. (c) F7.3 owns the actual print builder — F7.2 only emits the typed envelope. |
| **R-DRIFT** | **`plan.md` references `POST /operacion/salidas/mensualidad` and `mensualidad_no_vigente` (400), but F1.7 DEC-MONO-01 consolidated to ONE endpoint with server-side `tipo_salida` derivation** — proposal risk: a future reader of `plan.md` may revert F7.2 to call the non-existent endpoint. | MED | (a) Drift reconciled explicitly in §1 Intent + §3.4 Decision Path. (b) Verify-phase `tests/static/test_salida_endpoint_count.py` asserts `grep -r 'POST.*salidas/mensualidad' apps/` returns 0 matches. (c) Drift documented in `apply-progress.md` as a known spec-vs-ER mismatch resolved in F1.7. |
| **R5** | **`Idempotency-Key` collision if `canonicalJson` normalizes differently on client vs server** — RFC 8785 is well-defined, but a server-side parser bug could yield a different hash. | LOW | (a) Server-side `IdempotencyKeyMiddleware` hashes the raw request body bytes (not re-serialized JSON). F7.2's client-side hash is an OPTIMIZATION for the happy path (same client re-click), not the canonical server-side key — server always falls back to body-bytes hash on cache miss. (b) `canonicalJson` unit-tested for property-order independence at `canonicalJson.test.ts`. (c) E1-S3 e2e verifies the second click within 24h returns the cached 201, not a new INSERT. |

## 7. Open decisions to ratify

Two open decisions require user ratification before `sdd-spec` locks them.

### OD-1 — Where does the `tipo_salida`-driven routing live?

**Proposal**: in the `useRegistrarSalida` hook wrapper itself — after the 201 response, the hook returns `{ data: SalidaReadForzado, ... }` and the consumer (SalidaPanel/SalidaMensualidad) inspects `data.tipo_salida` to decide the next step.

**Alternatives**: (a) `useRegistrarSalida` exposes `data.tipo_salida` via a separate `useEffect` watcher in SalidaPanel — adds a reactive layer that can drift from the actual response. (b) `useRegistrarSalida` returns a discriminated `route` object `{ kind: 'pago' | 'print-mensualidad' | 'error', payload }` — encapsulates the routing decision in the hook but couples hook to UI concerns.

**Ratification needed**: confirm the inspection-in-consumer pattern (proposal) is acceptable.

### OD-2 — `useSWRMutation` vs raw `fetch` for the POST

**Proposal**: `useSWRMutation('/api/v1/operacion/salidas', fetcher, { populateCache: false })` (SWR first-class mutation hook, no cache writes — the response is consumed imperatively).

**Alternatives**: (a) Raw `fetch` + `useState` for `loading`/`error`/`data` — explicit but verbose. (b) Custom thin wrapper around `parkosFetch` returning `{ trigger, state }` — no SWR dep but reinvents `isMutating` semantics.

**Ratification needed**: confirm `useSWRMutation` is the canonical mutation surface.

## 8. PR shape

### 8.1 Single PR topology

| Field | Value |
|---|---|
| Branch | `feature/hu-f7-2-registrar-salida` |
| Target | `dev` (gitflow — NEVER `main`) |
| Work units | T1, T2, T3 + I1, I2 + E1 (6 commits) |
| Commit strategy | `work-unit-commits` skill — each T/I is a separate reviewable commit |
| Conventional Commits | strict (no `Co-authored-by` AI trailers per AGENTS.md canon) |
| LOC budget | 800 lines per PR; F7.2 forecast = ~406 LOC |
| `size:exception` required | No (under 800 LOC threshold) |
| Chained PRs | No (single PR, all commits to `feature/hu-f7-2-...` → `dev`) |

### 8.2 Commit plan (work-unit-commits skill)

Each commit MUST compile + pass all tests independently (strict TDD).

| # | Commit | Type | Scope | Files | TDD phase |
|---|---|---|---|---|---|
| 1 | `feat(operacion): idempotency helper + 4 unit tests` | feat | operacion | NEW idempotency.ts, NEW idempotency.test.ts | RED (4 tests fail) → GREEN |
| 2 | `feat(operacion): salidaApi Zod schema mirror of SalidaReadForzado + 3 tests` | feat | operacion | NEW salidaApi.ts, NEW salidaApi.test.ts | RED (3 tests fail) → GREEN |
| 3 | `feat(operacion): useRegistrarSalida SWR mutation hook + 4 tests` | feat | operacion | NEW useRegistrarSalida.ts, NEW useRegistrarSalida.test.ts | RED (4 tests fail) → GREEN: rotación success + mensualidad success + 409 salida_duplicada + 422 cotizacion_expirada |
| 4 | `feat(operacion): SalidaFlow + SalidaMensualidad composition pages + 5 tests` | feat | operacion | NEW SalidaFlow.tsx, NEW SalidaMensualidad.tsx, NEW SalidaFlow.test.tsx, NEW SalidaMensualidad.test.tsx | RED (5 tests fail) → GREEN |
| 5 | `refactor(operacion): SalidaPanel wires onConfirmar to useRegistrarSalida` | refactor | operacion | UPDATE SalidaPanel.tsx (+20 delta), UPDATE SalidaSheet.tsx (+5 delta), UPDATE SalidaPanel.test.tsx | RED (existing tests fail on `onPagoSubmit` removal) → GREEN |
| 6 | `test(operacion): e2e/salida.spec.ts with 3 scenarios (rotación, mensualidad, doble clic)` | test | operacion | NEW e2e/salida.spec.ts, UPDATE playwright.config.ts | E2E green |
| 7 | `feat(i18n): operacion.json salida.* keys + REQ-OPS-152..157 spec deltas` | docs | operacion | UPDATE operacion.json (+6 keys), UPDATE openspec/specs/operations/spec.md | Spec sync |

### 8.3 PR title + body

- **Title**: `feat(operacion): HU-F7.2 registrar salida (rotación + mensualidad) — UI integration`
- **Body**: Conventional Commits footer with `Refs: HU-F7.2`, `Refs: REQ-OPS-152..157`, `Closes: plan.md:1700-1741`. Bullet list of the 7 T/I/E work units. Drift reconciliation note (§3.4) inline. Rollback plan: revert the single commit (`feature/hu-f7-2-...` → `dev`), no DB migration, no backend change, no other consumer depends on `useRegistrarSalida`/`idempotency.ts` until HU-F8.1 / F7.3 lands.

### 8.4 Verification gate (pre-merge)

- [ ] `git diff dev..feature/hu-f7-2-...` ≤ 800 LOC
- [ ] `pnpm --filter electron-sucursal lint` exits 0
- [ ] `pnpm --filter electron-sucursal typecheck` exits 0
- [ ] `pnpm --filter electron-sucursal test:coverage` exits 0 with per-file thresholds met (new entries for idempotency.ts, salidaApi.ts, useRegistrarSalida.ts, SalidaFlow.tsx, SalidaMensualidad.tsx)
- [ ] `pnpm --filter electron-sucursal e2e -- salida.spec.ts` exits 0 with 3 scenarios passing
- [ ] `grep -r 'POST.*salidas/mensualidad' apps/electron-sucursal/src` returns 0 matches (drift guard)
- [ ] `grep -r 'mensualidad_no_vigente' apps/electron-sucursal/src` returns 0 matches (drift guard)
- [ ] `gh pr merge --squash --body-file` produces a squash commit with no `Co-authored-by` AI trailer

### 8.5 Post-merge (per AGENTS.md gitflow + override rule 2026-09-17)

1. `git checkout dev` + `git merge --ff-only feature/hu-f7-2-registrar-salida` (or `--no-ff` if not direct descendant).
2. `git push origin dev`.
3. `git branch -d feature/hu-f7-2-registrar-salida` + `git push origin --delete feature/hu-f7-2-registrar-salida`.
4. Vite cache invalidation: kill port 5173 + restart with `--force` per AGENTS.md.
5. Engram `mem_save` of the canonical `useRegistrarSalida` + `idempotency.ts` decisions (post-merge convention).

## 9. Success criteria

1. Operator types placa + cotiza → confirms → backend returns 201 with `uuid_salida` + `tipo_salida='ROTACION'` (rotación) or `tipo_salida='MENSUALIDAD'` (mensualidad).
2. On `tipo_salida='ROTACION'` → `useDashboardDrawerStore.open('pago', pagoAnchorId)` fires (REQ-OPS-138 invariant).
3. On `tipo_salida='MENSUALIDAD'` → `bridge.imprimir('salida_mensualidad', payload)` event fires (F7.3 will own the actual print).
4. Doble clic en "Confirmar salida" → `Idempotency-Key` duplicate → server returns cached 201 → no duplicate row.
5. `useRegistrarSalida.test.ts` covers 4 scenarios: rotación success, mensualidad success, 409 `salida_duplicada`, 422 `cotizacion_expirada`.
6. `idempotency.test.ts` covers property-order independence (RFC 8785).
7. `salidaApi.test.ts` Zod parse accepts canonical `SalidaReadForzado` shape; rejects injections of `tipo_salida` in input (DEC-SUC-21-NEW).
8. `e2e/salida.spec.ts` passes 3 scenarios: rotación / mensualidad / doble clic.
9. `useOcupacion` with `refreshInterval: 10000` (F4.3) shows cupo decremented within 10s of the INSERT (F1.7 backend recomputes `cantidad_vehiculos_sucursal` view).
10. WCAG 2.1 AA: axe-core reports 0 violations on `<SalidaFlow />` and `<SalidaMensualidad />`.
11. Drift guards pass: `grep -r 'POST.*salidas/mensualidad' apps/` returns 0 matches.
12. `pnpm typecheck`, `pnpm lint`, `pnpm test` exit 0 across the full `electron-sucursal` workspace.

## 10. Out of scope (re-iterated for emphasis)

- HU-F8.1 — PagoModal (separate change).
- HU-F7.3 — Tiquetes CU-15S + CU-15SM (separate change).
- New `POST /operacion/salidas/mensualidad` endpoint — does not exist (F1.7 DEC-MONO-01 consolidates to one endpoint).
- `mensualidad_no_vigente` error code — does not exist; replaced by server-side `tipo_salida` derivation.
- Server-side `Idempotency-Key` cache logic — backend owns (F1.6 PR2).
- Backend changes — zero. F1.7 already ships `POST /operacion/salidas` + `SalidaReadForzado`.
- Mensualidad detection client-side refactor — F7.1 already short-circuits on `cobrar: false` (REQ-OPS-143).
- `vigente_hasta` countdown re-validation on confirm — `CotizacionPanel` + backend V5 already handle it.
- Release branch + tag — post-merge operational, not PR scope.
- Vite cache invalidation post-merge — handled by AGENTS.md script.

## 11. Relevant files (canonical pointers)

**OpenSpec / plan / spec**:
- `openspec/changes/fase-7-2-registrar-salida/proposal.md` (this file)
- `openspec/changes/fase-7-2-registrar-salida/exploration.md` (sdd-explore phase, future)
- `openspec/changes/fase-7-2-registrar-salida/specs/operations/spec.md` (sdd-spec delta, REQ-OPS-152..157)
- `openspec/changes/fase-7-2-registrar-salida/design.md` (sdd-design phase, future)
- `openspec/changes/fase-7-2-registrar-salida/tasks.md` (sdd-tasks phase, future)
- `openspec/changes/fase-7-2-registrar-salida/apply-progress.md` (sdd-apply phase, future)
- `openspec/changes/fase-7-2-registrar-salida/verify-report.md` (sdd-verify phase, future)
- `plan.md` lines 1700-1741 (F7.2 block + sequence diagram)
- `openspec/specs/operations/spec.md` lines 5825-5910 (F7.1 REQ-OPS-143..151 baseline — F7.2 extends with REQ-OPS-152..157)

**Archive precedents**:
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/{proposal,design,tasks,verify-report}.md` (canonical F1.7 backend + DEC-MONO-01)
- `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/{proposal,tasks}.md` (canonical cotizar schema)
- `openspec/changes/archive/2026-09-19-fase-7-1-busqueda-tolerante-cotizacion/{proposal,design,tasks,verify-report}.md` (F7.1 host components)

**Backend canonical (live on `dev`)**:
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:322-400` (`POST /operacion/salidas` handler)
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py:392-422` (`SalidaReadForzado` shape)
- `backend/packages/parkos_core/src/parkos_core/repo/salida.py` (V1+V5+INSERT helpers)
- `backend/packages/parkos_core/migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py` (partial unique index)

**Frontend source**:
- `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (F7.1 host, target of +20 LOC delta)
- `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.tsx` (F7.1 presentational, REQ-OPS-143 baseline)
- `apps/electron-sucursal/src/features/operacion/components/SalidaSheet.tsx` (F7.1 sheet wrapper, target of +5 LOC delta)
- `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` (F7.1 SWR cotizar polling)
- `apps/electron-sucursal/src/features/operacion/lib/canonicalJson.ts` (F7.1 RFC 8785 helper — reused by idempotency.ts)
- `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts` (REQ-OPS-138 single-drawer)

**Files NOT touched (deliberate)**:
- `backend/**` (zero backend changes; F1.7 already ships the canonical endpoint + schemas)
- `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.tsx` (F7.1 closed; F7.2 only consumes its `onConfirmar` prop)
- `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` (F7.1 closed; F7.2 only reads the data)
- `apps/electron-sucursal/src/lib/validation/placaTolerante.ts` (F7.1 closed)
- `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts` (REQ-OPS-138 stable; F7.2 only invokes `open('pago', anchorId)`)

## 12. Next steps

1. **sdd-spec** (`fase-7-2-registrar-salida`): author the delta spec against `openspec/specs/operations/spec.md` (add REQ-OPS-152..157 with 6 scenarios: REQ-OPS-152 `<SalidaFlow />` composición, REQ-OPS-153 `<SalidaMensualidad />` atajo, REQ-OPS-154 `useRegistrarSalida` SWR mutation, REQ-OPS-155 `Idempotency-Key` SHA-256, REQ-OPS-156 doble-clic dedup, REQ-OPS-157 409 `salida_duplicada` UI handling). Drift reconciliation captured as REQ-OPS-152 MUST requirement that `SalidaFlow`/`SalidaMensualidad` consume ONLY `POST /operacion/salidas` (not `/salidas/mensualidad` which doesn't exist).
2. **sdd-design**: technical design for `useRegistrarSalida` + `idempotency.ts` + composition wiring. Cite F7.1 inline-composition precedent verbatim. Cite F1.7 DEC-MONO-01 verbatim. Show the canonical request/response wire shape from `operacion.py:322`.
3. **sdd-tasks**: 7-commit plan from §8.2 mapped to T-HU-F7.2-1..N task IDs with RED/GREEN/REFACTOR phases per commit.
4. **sdd-apply**: implement + verify + merge to `dev` per AGENTS.md gitflow + override rule.
5. **sdd-verify**: run verification per §8.4 success criteria; produce `verify-report.md` with drift-guard grep outputs.
6. **sdd-archive**: sync delta specs to `openspec/specs/operations/spec.md` (canonical), archive the change folder.