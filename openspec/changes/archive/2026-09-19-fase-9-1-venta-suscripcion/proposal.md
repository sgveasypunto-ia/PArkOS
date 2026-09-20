# Proposal: HU-F9.1 — Venta de suscripción desde caja (wizard 4 pasos)

> **Change**: `fase-9-1-venta-suscripcion`
> **Folder**: `openspec/changes/fase-9-1-venta-suscripcion/`
> **Phase**: propose (sdd-propose)
> **HU ID**: HU-F9.1 (Fase 9 — Suscripciones y mensualidades operativas, CU-06)
> **Plan.md ref**: lines 2012-2093 (HU-F9.1 block + sequence diagram + NOTA DE ALCANCE)
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC/PR`, strict_tdd=`true`, chain_strategy=`n/a`
> **Git identity**: `Parkos Dev <dev@parkos.local>` (per AGENTS.md gitflow). No AI attribution in commits.

## Inputs read

- `plan.md` lines 2012-2093 (HU-F9.1 block + ACs + sequence diagram; line 2016 NOTA DE ALCANCE on producto amplificación, NOT literal CU-06)
- `plan.md` line 460 (A-09 prorrateo — no `monto_prorrateado` column on `subscripciones_cliente`)
- `plan.md` line 1053 (T2 day > 15 trigger — A-09 decay rule)
- `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesList.ts` (F9.2 baseline + **stub `useVentaSuscripcion` at lines 80-98** that F9.1 MUST extract into a dedicated module)
- `apps/electron-sucursal/src/features/suscripciones/components/SuscripcionesPanel.tsx` (F9.2 dashboard widget — F9.1 does NOT touch)
- `apps/electron-sucursal/src/features/operacion/hooks/useRegistrarSalida.ts` (F7.2 SWR mutation pattern — canonical template for `useVentaSuscripcion`)
- `apps/electron-sucursal/src/features/operacion/lib/idempotency.ts` (F7.2 `buildIdempotencyKey` SHA-256 helper — **reused as-is** by F9.1)
- `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` (F8.1 SWR mutation pattern — `Idempotency-Key` closure + 401/409 error mapping mirror)
- `apps/electron-sucursal/src/renderer/i18n/locales/suscripciones.json` (F9.2 baseline keys — F9.1 EXTENDS with wizard keys)
- `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/{proposal,specs/operations/spec.md,design.md}` (F1.12 backend canonical — REQ-OPS-083..090 + XR5 + KD-VENTA-01 single-commit + DEC-VENTA-06 no-store)
- `openspec/changes/archive/2026-09-19-fase-8-1-pago-modal-fe/proposal.md` (F8.1 — PagoModal RHF + Zod discriminated union + vueltos live + recibo_pago builder precedent)
- `openspec/changes/archive/2026-09-19-fase-7-2-registrar-salida/proposal.md` (F7.2 — `useRegistrarSalida` + `buildIdempotencyKey` + 409 `salida_duplicada` mapping precedent)
- `modelo_datos_er.mmd` (subscriptions domain — no new columns; A-09 prorrateo persistence lives in `factura_detalle` ONLY, NOT in `subscripciones_cliente`)

## Skills loaded

- `sdd-propose` (this phase)
- `_shared/sdd-phase-common` (Section B/C/D envelope + Return Envelope contract)

---

## 1. Intent

HU-F9.1 delivers the operador's **venta de suscripción** from the caja screen. Today an operador has no path to sell a monthly plan at the counter: subscription creation is admin-only and decoupled from cobro/FE. F9.1 closes that gap with a **wizard 4 pasos** (cliente → vehículos → plan → pago) that calls the already-shipped **`POST /api/v1/clientes/venta-suscripcion`** backend (F1.12, merged at `a6ff5e3`) and reuses F8.1's `PagoModal` shell for the pago step.

**NOTA DE ALCANCE — producto amplificación** (`plan.md:2016`): the CU-06 corpus describes admin-only subscription creation (no cobro, no FE). F9.1 is an operational amplification — the wizard + atomic backend combo that lets the operador sell at the counter is NOT a literal CU-06 requirement. The explicit scope decision is recorded here.

**User-facing payoff**: operador vende mensualidad en el mismo mostrador sin salir de la pantalla de venta; el sistema valida placa duplicada + tipo de vehículo + cantidad máxima antes de aceptar el pago.

## 2. Scope

### 2.1 In scope (T1..T4 + I1)

- **T1 — `Venta` page** (NEW `apps/electron-sucursal/src/features/suscripciones/pages/Venta.tsx`): 4-paso wizard with per-step Zod validation. Step 1 cliente (NIT/nombre/email; embedded cliente via `cliente.tipo_identificador` XOR `uuid_cliente` reference, mirrors F1.12 discriminated union). Step 2 vehículos (1-2 placas; F1.6 `FORMATO_AUTO`/`FORMATO_MOTO` reuse). Step 3 plan (tipo_subscripciones vigente). Step 4 pago (F8.1 PagoModal reuse; F1.12 request body carries `cobrar_ahora`/`medio_pago`/`emitir_factura_electronica`).
- **T2 — `useVentaSuscripcion` SWR mutation hook** (NEW `apps/electron-sucursal/src/features/suscripciones/hooks/useVentaSuscripcion.ts`): single POST to `/api/v1/clientes/venta-suscripcion` with `Idempotency-Key` SHA-256 closure (F7.2 `buildIdempotencyKey` reused verbatim). 401 → `useAuthStore.clear()` + `parkos:auth:cleared` (F3.1 invariant). Maps backend error codes to typed subclasses (`SuscripcionDuplicadaPlacaError` 422, `TipoVehiculoIncompatibleError` 422, `CantidadMaximaExcedidaError` 422). **MOVE** the existing stub at `useSuscripcionesList.ts:80-98` here.
- **T3 — Prorrateo display** (NEW `apps/electron-sucursal/src/features/suscripciones/lib/prorrateo.ts` + UI integration): pure helper `calcularMontoProporcional(plan, fecha_inicio)` mirroring F1.12 backend `repo/venta_suscripcion.py::calcular_prorrateo` (A-09 formula: `valor_dia = plan.valor / plan.duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes` IF `fecha.day > 15` ELSE `null`). UI shows "Monto prorrateado: $X" badge in wizard step 4 BEFORE the pago confirmation. Plan.md:460 forbids persisting on `subscripciones_cliente` — backend persists in `factura_detalle` ONLY when `cobrar_ahora=true`.
- **T4 — `e2e/suscripcion-venta.spec.ts`** (NEW): 4 scenarios per `plan.md:2047-2052`: (1) cliente nuevo: creates `clientes` + `vehiculos` + `subscripciones_cliente` in one TX; (2) cliente existente: reuses `clientes` row; (3) plan `mismo_tipo_vehiculo=true` + placas mixed tipos → `422 tipo_vehiculo_incompatible`; (4) placa con suscripción vigente → `422 suscripcion_duplicada_placa`.

### 2.2 Out of scope (explicit)

- **HU-F9.2 — listado + alerta vencimiento** (`plan.md:2094`): F9.2 owns the listing page + `dias_alerta_pre_vencimiento` banner. F9.1 only consumes the write endpoint.
- **Backend `POST /clientes/venta-suscripcion`** — F1.12 owns (`openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/`). F9.1 ships ZERO backend code.
- **Admin CRUD de planes / tipo_subscripciones** — Fase 14 (admin). F9.1 only reads `tipo_subscripciones` via the existing list endpoint.
- **`Convenios B2B` / `clientes_b2b`** (`plan.md:2016` literal): explicitly OUT — CU-06 BR5 calls it "un caso de uso aparte". `ClientesB2B` ORM model exists but F9.1 does NOT touch it.
- **Renovación / anulación / cambio de plan mid-cycle** — future HU, Fase 9.x+.
- **Multi-sucursal suscripción** (one cliente + N branches) — out per F1.12 §12.
- **Pago mixto (efectivo + datáfono)** — out per `plan.md:1875` (F8.1 scope).

## 3. Capabilities

### New Capabilities

- **`subscription-sale`**: the operador-facing wizard that sells a subscription (cliente + vehículos + plan + cobro opcional + FE opcional) at the counter in a single transaction. Covers T1 (Venta page wizard), T2 (useVentaSuscripcion hook), T3 (prorrateo display), T4 (e2e scenarios). Becomes `openspec/specs/subscription-sale/spec.md` (new full spec).

### Modified Capabilities

- **None.** F9.1 consumes existing capabilities (`operations` for `POST /clientes/venta-suscripcion`, `facturacion` for PagoModal, `subscriptions-listing` for plan reference data) without modifying their contracts. No delta specs required.

## 4. Approach

### 4.1 Decision Path 1 — Wizard 4 pasos with per-step Zod validation

The wizard state lives in `useState<{paso: 1|2|3|4, cliente, placas, plan, medio_pago}>` inside `Venta.tsx`. Each step has its own Zod schema; advancing triggers `zodResolver`-driven validation BEFORE `setPaso(paso + 1)`. This matches F7.1/F7.2/F8.1 patterns (per-step validation, NOT a single big schema at submit time) and keeps each step's error rendering local.

### 4.2 Decision Path 2 — Single mutation hook for atomic backend POST

`useVentaSuscripcion().trigger({...})` calls the ONE F1.12 endpoint that handles everything transactionally (KD-VENTA-01 single-commit). Mirrors F7.2 `useRegistrarSalida` and F8.1 `useRegistrarPago` pattern verbatim (`useSWRMutation` + `buildIdempotencyKey` SHA-256 + 401 handler + typed error subclasses). The stub at `useSuscripcionesList.ts:80-98` MUST be moved to its own file (single responsibility; F9.2 listing file stays focused on SWR query, F9.1 file owns the mutation).

### 4.3 Decision Path 3 — Prorrateo display client-side

`calcularMontoProporcional(plan, fecha_inicio)` is a pure helper (no I/O, easy to unit test in isolation) that mirrors F1.12 backend `calcular_prorrateo` (DEC-VENTA-03). Wizard step 4 displays "Monto prorrateado: $X" if `fecha.day > 15` AND `monto_proporcional !== null`, BEFORE the pago confirmation. The same formula runs server-side; if the client calc drifts, F1.12 `factura_detalle.valor_unitario` is the authoritative source (the wizard's `monto_proporcional` field is informational).

### 4.4 Decision Path 4 — Error code mapping (typed subclasses)

F1.12 backend error bodies carry `{error: <code>, ...}` (e.g. `{error: "suscripcion_duplicada_placa", placa: "ABC123"}`). The hook parses these into typed subclasses:

| Backend error code | HTTP | Typed class | Wizard surface |
|---|---|---|---|
| `suscripcion_duplicada_placa` | 422 | `SuscripcionDuplicadaPlacaError(placa)` | Step 2 inline: "Esta placa ya tiene una suscripción vigente" |
| `tipo_vehiculo_incompatible` | 422 | `TipoVehiculoIncompatibleError(tipos_encontrados)` | Step 2 inline: "Este plan exige que todas las placas sean del mismo tipo" |
| `cantidad_maxima_excedida` | 422 | `CantidadMaximaExcedidaError(max)` | Step 2 inline: blocks adding more placas |
| `plan_duracion_dias_invalido` | 422 | `PlanDuracionDiasInvalidoError` | Step 3 inline |
| `idempotency_conflict` | 409 | `IdempotencyConflictError` | Step 4 toast |
| `unauthorized` (401) | 401 | (handled by F3.1 invariant) | Auth redirect |

## 5. Affected Areas

| Area | Action | Description |
|---|---|---|
| `apps/electron-sucursal/src/features/suscripciones/pages/Venta.tsx` | NEW | 4-paso wizard + per-step Zod + paso state. ~250 LOC. |
| `apps/electron-sucursal/src/features/suscripciones/pages/Venta.test.tsx` | NEW | Component tests for each step + happy path + 3 error scenarios. ~200 LOC. |
| `apps/electron-sucursal/src/features/suscripciones/hooks/useVentaSuscripcion.ts` | NEW | SWR mutation hook + typed error subclasses. ~100 LOC. |
| `apps/electron-sucursal/src/features/suscripciones/hooks/useVentaSuscripcion.test.ts` | NEW | Hook tests: happy path + 3 error mappings + 401 handler. ~150 LOC. |
| `apps/electron-sucursal/src/features/suscripciones/api/ventaSuscripcionApi.ts` | NEW | Zod schema mirror of F1.12 `VentaSuscripcionCreate` + `VentaSuscripcionResponse`. ~70 LOC. |
| `apps/electron-sucursal/src/features/suscripciones/lib/prorrateo.ts` | NEW | Pure `calcularMontoProporcional(plan, fecha)` + helpers. ~30 LOC. |
| `apps/electron-sucursal/src/features/suscripciones/lib/prorrateo.test.ts` | NEW | Unit tests: day=10 → null, day=20 → valor_dia × dias_restantes, duracion_dias=0 → throws. ~40 LOC. |
| `apps/electron-sucursal/src/renderer/i18n/locales/suscripciones.json` | UPDATE | +20 keys: `venta.titulo`, `venta.paso1.*`, `venta.paso2.*`, `venta.paso3.*`, `venta.paso4.*`, `venta.errors.suscripcion_duplicada_placa`, `venta.errors.tipo_vehiculo_incompatible`, `venta.errors.cantidad_maxima_excedida`, `venta.prorrateo.label`, `venta.prorrateo.dia15_aviso`. |
| `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesList.ts` | UPDATE | Remove stub `useVentaSuscripcion` (lines 80-98). F9.2 file becomes read-only (SWR query). Net delta: −20 LOC. |
| `apps/electron-sucursal/e2e/suscripcion-venta.spec.ts` | NEW | 4 Playwright scenarios + axe-core WCAG gate. ~80 LOC. |
| **Total new LOC** | | **~940** (forecast 940 + test fixtures) |
| **Total updated LOC (deltas)** | | **−20** (useSuscripcionesList stub removal) |

## 6. Risks

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| **R1** | **F9.1 forecast ~940 LOC > 800 budget** — needs `size:exception`. Wizard 4 pasos is integral (cannot split without leaving the form or the prorrateo helper incomplete). | **HIGH** | (a) RATIFIED in tasks phase — single-PR with `size:exception`. F7.1 (935 LOC) + F8.1 (1140 LOC) precedents accepted by user 2026-09-17/19. (b) Drift guard `tests/static/test_venta_suscripcion_is_atomic.py` asserts Venta + useVentaSuscripcion + ventaSuscripcionApi + prorrateo + i18n keys all ship in the same commit. (c) 5-commit work-unit plan (§8.2) keeps each commit reviewable. |
| **R2** | **Backend error code drift** — F1.12 may emit different error codes/shapes after refactor. | MED | (a) Verify against F1.12 spec at `archive/2026-09-15-hu-f1-12-venta-suscripcion/specs/operations/spec.md` (REQ-OPS-089..090). (b) `ventaSuscripcionApi.ts` Zod schemas assert response shape; drift breaks `pnpm typecheck`. (c) 3 unit tests per error subclass catch drift at RED phase. |
| **R3** | **Prorrateo client-side calc drift from F1.12 backend** — if the formulas diverge, the wizard shows one amount and the backend bills another. | MED | (a) The `calcularMontoProporcional` helper is a verbatim mirror of F1.12 `calcular_prorrateo` (DEC-VENTA-03): `valor_dia = plan.valor / plan.duracion_dias`; `dias_restantes_mes = (lastDayOfMonth - fecha.day)`; `monto_proporcional = valor_dia * dias_restantes_mes` IF `fecha.day > 15` ELSE `null`. (b) Prorrateo.test.ts covers the exact reference cases (`plan.valor=30000`, `duracion_dias=30`, `fecha.day=20` → 10000). (c) Authoritative source remains `factura_detalle.valor_unitario` (A-09); wizard `monto_proporcional` is informational. |
| **R4** | **Stub removal breaks F9.2** — `useSuscripcionesList.ts:80-98` exposes `useVentaSuscripcion` today (probably imported nowhere on dev). Removing it could break imports. | LOW | (a) Grep `grep -r "useVentaSuscripcion" apps/electron-sucursal` returns zero imports outside `useSuscripcionesList.ts` itself (the stub is dead code). (b) Drift guard: `grep -r "from.*useSuscripcionesList.*useVentaSuscripcion" apps/electron-sucursal/src` MUST return zero matches before stub removal. (c) F9.2 listing file remains focused on its SWR query. |
| **R5** | **Doble-click during in-flight venta** — duplicate INSERT or 409. | LOW | (a) `useSWRMutation.isMutating` UI disable on Confirm button (mirror F7.2 R2 invariant). (b) `Idempotency-Key` SHA-256 closure on the single POST — server-side 24h cache dedup (F1.6 middleware, DEC-IDEM-01). (c) e2e rapid-click scenario in `suscripcion-venta.spec.ts`. |
| **R6** | **Wizard state machine bloat — 4 steps × N inputs = 12+ Zod validations to test** | LOW | (a) E2E covers happy path + 3 error scenarios. (b) Per-step unit tests cover each Zod schema independently. (c) Total validation coverage: 4 per-step Zod tests + 4 e2e scenarios = 8 verification points. |
| **R7** | **`emitir_factura_electronica` flag default drift** — F1.12 default is `false`; F9.1 wizard does NOT toggle this flag, so the FE always defaults off. F8.1's PagoModal already toggles FE con datos within the FE flow itself. | LOW | (a) F9.1 sends `emitir_factura_electronica=false` per `plan.md:2024` implicit (the wizard's pago step delegates to F8.1 PagoModal which handles FE on its own). (b) `emitir_factura_electronica` becomes relevant only when the operador wants a FACTURA_ELECTRONICA outside the pago flow (rare). (c) Drift guard: `grep -r "emitir_factura_electronica" apps/electron-sucursal/src/features/suscripciones` MUST show explicit `false` default. |

## 7. Rollback Plan

**Per-commit revert** — each commit on `feature/hu-f9-1-venta-suscripcion` is a self-contained reviewable unit (RED → GREEN → REFACTOR per `work-unit-commits` skill):

1. `git revert <commit-sha>` per commit — no DB migration, no backend change, no shared infrastructure.
2. The 5 commits can be reverted individually without breaking the build (each compiles + tests independently per strict TDD).
3. The full branch revert (`git revert --no-commit dev..feature/hu-f9-1-...`) restores the `dev` state — `useSuscripcionesList.ts` re-exposes the stub `useVentaSuscripcion`, all F9.1 files deleted.

**Post-revert validation**:
- [ ] `pnpm --filter electron-sucursal typecheck` exits 0
- [ ] `pnpm --filter electron-sucursal test` exits 0 (no F9.1 tests run)
- [ ] F9.2 dashboard widget (`SuscripcionesPanel.tsx`) still renders + lists subscriptions
- [ ] F8.1 PagoModal unaffected (no shared component touched)

## 8. Dependencies

### Already-merged prerequisites (verified on `dev`)

- **F1.12 — `POST /api/v1/clientes/venta-suscripcion`** (REQ-OPS-083..090 + XR5): the canonical backend endpoint F9.1's hook calls. **Required** (no fallback if missing).
- **F8.1 — `<PagoModal />` + `useRegistrarPago` + `Idempotency-Key` SHA-256** (merged): F9.1 reuses PagoModal inside the wizard step 4 (decision path 1, §4.1).
- **F8.1 — `validarNitModulo11`** (merged): F9.1 reuses for cliente NIT validation in wizard step 1.
- **F7.2 — `buildIdempotencyKey` SHA-256 helper** (merged at `apps/electron-sucursal/src/features/operacion/lib/idempotency.ts`): F9.1 imports verbatim.
- **F7.2 — `useRegistrarSalida` SWR mutation pattern** (merged): F9.1's `useVentaSuscripcion` mirrors the pattern (`useSWRMutation` + 401 handler + typed error subclass).
- **F1.6 — placa format validators `FORMATO_AUTO`/`FORMATO_MOTO`** (merged): F9.1 reuses for step 2 placa validation.
- **F4.2 — `formatCOP`** (merged): F9.1 reuses in prorrateo display.
- **F2.x — `parkosFetch` + `useAuthStore`** (merged): canonical HTTP + auth store.
- **F9.2 — `useSuscripcionesList` SWR query** (merged): F9.1 REMOVES the dead stub from this file.
- **DEC-SUC-06 — RHF + Zod (`zodResolver`)** (verified at `plan.md:421`): F9.1 follows verbatim.

### Forward-dependents (do NOT block F9.1)

- **HU-F9.2 — listado + alerta vencimiento**: F9.1 ships wizard; F9.2 ships listing + banner. F9.1's `useVentaSuscripcion` does NOT need F9.2 (forward-only).
- **HU-F8.2 — FE polling + retry panel**: F9.1 sets `uuid_fe` state via `useVentaSuscripcion` response; F8.2's polling wires later (out of F9.1 scope).
- **Admin CRUD planes (Fase 14)**: F9.1 reads `tipo_subscripciones` via existing list endpoint; admin CRUD is independent.

### Skill + tooling prerequisites

- `react` skill (parent loads) — React 18 PWA + Vite 5 + shadcn/ui + RHF + Zod + i18next es-CO + WCAG 2.1 AA via axe-core.

## 9. Open Decisions to Ratify

Two open decisions require user ratification before `sdd-spec` locks them.

### OD-1 — Cliente existente search por NIT antes de wizard step 1?

**Proposal**: **YES** — auto-fill if NIT matches an existing `clientes` row (via `GET /api/v1/clientes?nit=X`). The operador types the NIT, the wizard fetches the existing cliente, and the form auto-fills nombre/email/telefono. The operador can still edit any field if the existing data is stale.

**Alternatives**: (a) **NO** — operador enters all cliente data every time (slower; duplicates the data if the same cliente buys a second suscripción).

**Ratification needed**: confirmar auto-fill. F9.1's spec defaults to YES; user may override.

### OD-2 — Reuse PagoModal from F8.1 inside wizard step 4?

**Proposal**: **YES** — embed F8.1 `<PagoModal />` as the inline pago step (avoids duplicate UI; F8.1 PagoModal already handles vueltos live + FE con datos + voucher manual + NIT módulo 11).

**Alternatives**: (a) Build a new simplified pago form inline (duplicates F8.1 logic; loses vueltos live + FE con datos + NIT validation).

**Ratification needed**: confirmar reuse. F9.1's spec defaults to YES; user may override.

## 10. PR Shape

### 10.1 Single PR topology

| Field | Value |
|---|---|
| Branch | `feature/hu-f9-1-venta-suscripcion` |
| Target | `dev` (gitflow — NEVER `main`) |
| Work units | T1, T2, T3, T4 + I1 (5 commits) |
| Commit strategy | `work-unit-commits` skill — each T/I is a separate reviewable commit |
| Conventional Commits | strict (no `Co-authored-by` AI trailers per AGENTS.md canon) |
| LOC budget | 800 lines per PR; F9.1 forecast = ~940 LOC |
| `size:exception` required | **YES** — 940 LOC > 800 budget (+140, +17.5%) |
| Chained PRs | **NO** — wizard 4 pasos + per-step Zod + pago modal reuse + prorrateo helper are integral; cannot split without leaving the form or the helper incomplete |

### 10.2 Commit plan (work-unit-commits skill)

Each commit MUST compile + pass all tests independently (strict TDD).

| # | Commit | Type | Scope | Files | TDD phase |
|---|---|---|---|---|---|
| 1 | `feat(suscripciones): prorrateo pure helper + 5 unit tests (A-09 DEC-VENTA-03 mirror)` | feat | suscripciones | NEW prorrateo.ts, NEW prorrateo.test.ts | RED (5 tests fail: day=10→null, day=20→valor_dia×dias_restantes, duracion_dias=0→throws, Feb 28 days, last day of month) → GREEN |
| 2 | `feat(suscripciones): ventaSuscripcionApi Zod schemas mirror of F1.12 backend contracts` | feat | suscripciones | NEW ventaSuscripcionApi.ts | RED (Zod parse tests fail: extra='forbid' rejects `vigente_desde`, plates range 0/3 reject) → GREEN |
| 3 | `feat(suscripciones): useVentaSuscripcion SWR mutation + 4 typed errors (mirror useRegistrarSalida)` | feat | suscripciones | NEW useVentaSuscripcion.ts, NEW useVentaSuscripcion.test.ts, UPDATE useSuscripcionesList.ts (stub removal) | RED (4 tests fail: happy path, 422 suscripcion_duplicada_placa, 422 tipo_vehiculo_incompatible, 422 cantidad_maxima_excedida) → GREEN |
| 4 | `feat(suscripciones): Venta page wizard 4 pasos + per-step Zod + PagoModal reuse (F8.1)` | feat | suscripciones | NEW Venta.tsx, NEW Venta.test.tsx, UPDATE suscripciones.json (+20 keys) | RED (4 tests fail: paso 1 Zod reject, paso 2 placa range reject, paso 3 plan null reject, paso 4 happy path) → GREEN; 5 PagoModal tests still pass (reused unchanged) |
| 5 | `docs(sdd): F9.1 spec delta in operations/spec.md + i18n keys + drift guards + e2e` | docs | sdd | NEW e2e/suscripcion-venta.spec.ts, UPDATE openspec/changes/fase-9-1-venta-suscripcion/specs/operations/spec.md, UPDATE openspec/specs/operations/spec.md | Spec sync + drift guards + 4 e2e scenarios |

### 10.3 PR title + body

- **Title**: `feat(suscripciones): HU-F9.1 wizard venta suscripción 4 pasos (size:exception 940 LOC)`
- **Body**: Conventional Commits footer with `Refs: HU-F9.1`, `Refs: REQ-OPS-191..195`, `Closes: plan.md:2012-2093`. Bullet list of the 5 T/I/E work units. Drift reconciliation note inline — explicit acknowledgement that the `useVentaSuscripcion` stub from F9.2's `useSuscripcionesList.ts` is moved to a dedicated module (single responsibility). Rollback plan per-commit revert + `useSuscripcionesList` stub restoration. **Producto amplificación** note (NOTA DE ALCANCE) verbatim — explicitly NOT a literal CU-06 requirement.

### 10.4 Verification gate (pre-merge)

- [ ] `git diff dev..feature/hu-f9-1-...` ≤ 940 LOC (with `size:exception` ratified)
- [ ] `pnpm --filter electron-sucursal lint` exits 0
- [ ] `pnpm --filter electron-sucursal typecheck` exits 0
- [ ] `pnpm --filter electron-sucursal test` exits 0 with all Venta + useVentaSuscripcion + ventaSuscripcionApi + prorrateo tests green
- [ ] `pnpm --filter electron-sucursal e2e -- suscripcion-venta.spec.ts` exits 0 with 4 scenarios passing
- [ ] Drift guard: `grep -r "useVentaSuscripcion" apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesList.ts` returns 0 matches (stub removed)
- [ ] Drift guard: `grep -r "calcularMontoProporcional" apps/electron-sucursal/src/features/suscripciones` returns ≥3 matches (lib definition + Venta caller + test import)
- [ ] Drift guard: `grep -r "SuscripcionDuplicadaPlacaError" apps/electron-sucursal/src/features/suscripciones` returns ≥3 matches (hook definition + Venta inline display + test import)
- [ ] Drift guard: `tests/static/test_venta_suscripcion_is_atomic.py` asserts Venta + useVentaSuscripcion + ventaSuscripcionApi + prorrateo + i18n keys all ship in the same branch
- [ ] axe-core WCAG 2.1 AA: 0 violations on `<Venta />` wizard (per-step focus management; paso indicator visible)
- [ ] F8.1 PagoModal + 5 PagoSheet tests still pass (no shared component touched)
- [ ] F9.2 SuscripcionesPanel still renders + lists subscriptions
- [ ] `gh pr merge --squash --body-file` produces a squash commit with no `Co-authored-by` AI trailer

### 10.5 Post-merge (per AGENTS.md gitflow + override rule 2026-09-17)

1. `git checkout dev` + `git merge --ff-only feature/hu-f9-1-venta-suscripcion` (or `--no-ff` if not direct descendant).
2. `git push origin dev`.
3. `git branch -d feature/hu-f9-1-venta-suscripcion` + `git push origin --delete feature/hu-f9-1-venta-suscripcion`.
4. Vite cache invalidation: kill port 5173 + restart with `--force` per AGENTS.md.
5. Engram `mem_save` of the canonical wizard composition + useVentaSuscripcion mirror + prorrateo client-side helper + stub removal decisions (post-merge convention).
6. F9.2 developer notification: `useSuscripcionesList.ts` no longer exposes `useVentaSuscripcion`; the F9.2 listing file is now read-only SWR query (no stub).

## 11. Success Criteria

1. `<Venta />` mounts a 4-paso wizard with per-step Zod validation; advancing triggers `zodResolver` validation BEFORE `setPaso(paso + 1)`.
2. `useVentaSuscripcion().trigger({cliente, placas, plan, medio_pago, cobrar_ahora, emitir_factura_electronica})` POSTs to `/api/v1/clientes/venta-suscripcion` with `Idempotency-Key` SHA-256 closure (F7.2 helper reuse).
3. 401 → `useAuthStore.clear()` + `parkos:auth:cleared` (F3.1 invariant preserved).
4. 422 `suscripcion_duplicada_placa` → `SuscripcionDuplicadaPlacaError(placa)` rendered inline in wizard step 2 (per `plan.md:2041`).
5. 422 `tipo_vehiculo_incompatible` → `TipoVehiculoIncompatibleError(tipos_encontrados)` rendered inline in wizard step 2 (per `plan.md:2042`).
6. 422 `cantidad_maxima_excedida` → `CantidadMaximaExcedidaError(max)` rendered inline in wizard step 2 (per `plan.md:2043`).
7. Prorrateo display: `calcularMontoProporcional(plan={valor:30000, duracion_dias:30}, fecha_inicio='2026-09-20')` returns `10000`; wizard step 4 shows "Monto prorrateado: $10.000" badge BEFORE pago confirmation.
8. Prorrateo null case: `calcularMontoProporcional(plan, '2026-09-10')` returns `null`; wizard step 4 does NOT show the badge.
9. PagoModal reuse: F8.1 `<PagoModal />` mounts inside wizard step 4 with `total_cop` = `monto_proporcional ?? plan.valor`; vueltos live + FE con datos + voucher manual still work (F8.1 5 PagoSheet + 7 PagoModal tests still pass).
10. e2e 4 scenarios pass: cliente nuevo creates `clientes`+`vehiculos`+`subscripciones_cliente` in one TX; cliente existente reuses the row; plan `mismo_tipo_vehiculo=true` + mixed tipos → 422 `tipo_vehiculo_incompatible`; placa con suscripción vigente → 422 `suscripcion_duplicada_placa`.
11. Drift guards pass: Venta + useVentaSuscripcion + ventaSuscripcionApi + prorrateo + i18n keys all ship in the same branch (no PR split).
12. Stub removal: `grep -r "useVentaSuscripcion" apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesList.ts` returns 0 matches.
13. `pnpm typecheck`, `pnpm lint`, `pnpm test` exit 0 across the full `electron-sucursal` workspace.
14. F9.2 dashboard widget (`SuscripcionesPanel.tsx`) unaffected — still lists subscriptions + shows "vence pronto" banner.
15. axe-core WCAG 2.1 AA: 0 violations on `<Venta />` wizard (per-step focus management, paso indicator visible, all fields have labels).

## 12. Next Steps

1. **sdd-spec** (`fase-9-1-venta-suscripcion`): author the delta spec for `openspec/specs/operations/spec.md` (append REQ-OPS-191..195 with Given/When/Then/And scenarios): REQ-OPS-191 `Venta` wizard 4 pasos + per-step Zod + PagoModal reuse, REQ-OPS-192 `useVentaSuscripcion` SWR mutation with `Idempotency-Key` SHA-256 + 401/422 error mapping, REQ-OPS-193 `ventaSuscripcionApi` Zod schema mirror of F1.12 `VentaSuscripcionCreate` + `VentaSuscripcionResponse` with `extra='forbid'`, REQ-OPS-194 `calcularMontoProporcional` pure helper (A-09 mirror), REQ-OPS-195 4 e2e scenarios (cliente nuevo + cliente existente + plan mismo_tipo + placa duplicada).
2. **sdd-design**: technical design for the wizard state machine + per-step Zod validation + PagoModal composition + useVentaSuscripcion SWR mutation mirror + prorrateo client-side helper. Cite F7.2 `useRegistrarSalida` + F8.1 `useRegistrarPago` patterns verbatim. Show canonical `VentaStepState` + `VentaSuscripcionError` hierarchy shapes.
3. **sdd-tasks**: 5-commit plan from §10.2 mapped to T-HU-F9.1-1..N task IDs with RED/GREEN/REFACTOR phases per commit. Flag `size:exception` for 940 LOC vs 800 (R1 in §6, F7.1 + F8.1 precedents ratified 2026-09-17/19).
4. **sdd-apply**: implement + verify + merge to `dev` per AGENTS.md gitflow + override rule. Notify F9.2 developer that `useSuscripcionesList.ts` no longer exposes the stub.
5. **sdd-verify**: run verification per §10.4 success criteria; produce `verify-report.md` with drift-guard grep outputs (Venta + useVentaSuscripcion + ventaSuscripcionApi + prorrateo atomicity, 4 e2e scenarios, F8.1 12 tests still pass, F9.2 unaffected, 0 axe-core violations).
6. **sdd-archive**: sync delta specs to `openspec/specs/operations/spec.md` (canonical), archive the change folder.

---

**End of proposal — HU-F9.1.**