# Delta Spec: HU-F7.2 — Registrar salida (rotación + mensualidad) — UI integration

> **Change**: `fase-7-2-registrar-salida`
> **Phase**: sdd-spec
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-apply`
> **HU ID**: HU-F7.2 (Fase 7 — Salida y cálculo de tarifa, UI pivot)
> **Base spec**: `openspec/specs/operations/spec.md` (canonical, requires REQ-OPS-001..151)
> **Next free REQ-OPS gap**: 152..157 (REQ-OPS-143..151 are taken by F7.1 per `2026-09-19-fase-7-1-busqueda-tolerante-cotizacion` archive). F7.2 starts at REQ-OPS-152.
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC`, strict_tdd=`true`, chain_strategy=`n/a`
> **Git identity**: `Parkos Dev <dev@parkos.local>` per AGENTS.md gitflow. No AI attribution in commits.
> **Artifact language**: English (SDD canon); user-facing i18n keys in `operacion.json` stay in Spanish es-CO.
> **Skills loaded**: `sdd-spec` (this phase), `_shared/sdd-phase-common` (Section B/C/D envelope).
> **Drift anchor**: F1.7 DEC-MONO-01 (single endpoint `POST /operacion/salidas`, server-side `tipo_salida` derivation). F7.2 honors the live backend reality; the `plan.md` block that references `POST /operacion/salidas/mensualidad` and `mensualidad_no_vigente` is treated as stale — see §Drift reconciliation traceability below.

## Context

HU-F7.2 closes the F7.1 → CU-04 pivot: from a confirmed cotización
(rotación) or mensualidad detection, the operator confirms the salida.
The backend `POST /operacion/salidas` (F1.7, REQ-OPS-042..052, already
shipped on `dev`) performs the append-only INSERT into `prod.salidas`
with server-side `tipo_salida` derivation, releases the cupo immediately
via `cantidad_vehiculos_sucursal` recompute, and returns `uuid_salida`
+ `tipo_salida` to the renderer. F7.2 wires the F7.1
`<CotizacionPanel onConfirmar />` callback to that endpoint with
`Idempotency-Key` per DEC-SUC-04.

F7.2 handles BOTH rotación and mensualidad through this single endpoint
— F1.7 DEC-MONO-01 collapsed the two paths into one (`tipo_salida =
'ROTACION' | 'MENSUALIDAD'` derived server-side from F1.8's `cobrar`
flag). The renderer is **indifferent** to the path: it calls the same
endpoint, reads `response.tipo_salida`, and routes downstream UX
(PagoModal for rotación per HU-F8.1, CU-15SM print for mensualidad per
HU-F7.3). The user-facing payoff: from a confirmed cotización, one
click fires a backend mutation that releases the cupo, persists the
lifecycle event without ever persisting the monetary amount
(DEC-SUC-23 verbatim — the `salidas` table has NO `valor` column;
INSERT-only at F7.2; the `estado='PAGADO'` UPDATE is owned by Fase 8),
and routes the operator to the next step without page navigation.

For rotación: response `tipo_salida='ROTACION'` → proceed to PagoModal
(HU-F8.1, separate change — F7.2 only fires the
`useDashboardDrawerStore.open('pago', pagoAnchorId)` trigger preserving
REQ-OPS-138 single-drawer invariant). For mensualidad: response
`tipo_salida='MENSUALIDAD'` → print tiquete CU-15SM immediately
(HU-F7.3, separate change — F7.2 only emits the typed
`bridge.imprimir('salida_mensualidad', payload)` event envelope; F7.3
fills the payload shape and the `escposBuilder`). DEC-SUC-27 invariant
preserved: tiquete CU-15S prints **after** pago (Fase 8), not at salida;
tiquete CU-15SM prints immediately at salida mensualidad.

Doble clic en "Confirmar salida" es safe por el `Idempotency-Key` de 24h
del server (F1.6 `IdempotencyKeyMiddleware`, PR2) + UI in-flight disable
via `useSWRMutation`'s `isMutating` flag (CotizacionPanel disables the
Confirm button while the mutation is in flight). F7.2 ships ZERO backend
changes — F1.7 already ships the canonical endpoint + `SalidaReadForzado`
schema + V1..V5 validations + DEC-MONO-01 single-endpoint consolidation
+ partial unique index `one_exit_per_ingreso` for the 409 mapping.

## New requirements

### REQ-OPS-152 — `SalidaFlow` mount + confirmar rotación

The system SHALL render
`<SalidaFlow uuidIngreso={uuid} cotizacion={cot} onConfirmado={fn} />`
as a wrapper over `<CotizacionPanel />` for the rotación path. When the
operator confirms, the system SHALL call `POST /api/v1/operacion/salidas`
with body `{ uuid_ingreso }` and header
`Idempotency-Key: SHA-256('POST' + '/api/v1/operacion/salidas' + canonicalJson(body))`
(via `canonicalJson.ts` RFC 8785 normalization — F7.1 shipped the
canonical JSON serializer). The backend returns `201 Created` with a
`SalidaReadForzado` payload; the renderer stores `uuid_salida` and
`estado='PENDIENTE_PAGO'` in UI state and proceeds to PagoModal (Fase 8 —
out of scope here, but `SalidaFlow.onConfirmado` callback is the
integration point). [Cite: proposal §3 Path 1 + §6 R1 + DEC-SUC-23]

#### Scenario: rotación confirmación → 201 + estado `PENDIENTE_PAGO`

- **Given** operator confirms a rotación cotización (`cotizacion.cobrar === true`)
- **When** `POST /api/v1/operacion/salidas` is invoked
- **Then** the renderer MUST send
  `Idempotency-Key: SHA-256(...)` header (RFC 8785 normalized via
  `canonicalJson.ts`)
- **And** the renderer MUST disable the "Confirmar salida" button during
  in-flight via `useSWRMutation`'s `isMutating` flag (no doble POST)
- **And** the renderer MUST NOT call `pagos` or `factura` endpoints —
  those are Fase 8 (HU-F8.1 owns the modal lifecycle)
- **And** the renderer MUST release the cupo immediately (visible via
  `useOcupacion` polling within the 10s window per REQ-OPS-157)
- **And** the renderer MUST NOT update the SWR cache for
  `useOcupacion` optimistically (server-driven recompute only)

### REQ-OPS-153 — `SalidaMensualidad` atajo + confirmar mensualidad

The system SHALL render
`<SalidaMensualidad uuidIngreso={uuid} onConfirmado={fn} />` as a
1-screen page (no wizard, no stepper) when `Cotizacion.cobrar === false`
(short-circuit per REQ-OPS-143 mensualidad branch). The system SHALL call
the same `POST /api/v1/operacion/salidas` endpoint with `Idempotency-Key`
(identical scheme to REQ-OPS-152). The backend returns `201 Created` with
`tipo_salida='MENSUALIDAD'` and `estado='MENSUALIDAD_PAGO'`. The renderer
triggers CU-15SM print immediately (Fase 7.3 owns the print pipeline;
F7.2 only fires the typed `bridge.imprimir('salida_mensualidad', payload)`
event envelope — F7.3 fills the payload shape and the `escposBuilder`).
DEC-SUC-27 verbatim: CU-15SM prints immediately at salida mensualidad;
CU-15S prints after pago. [Cite: proposal §3 Path 2 + DEC-SUC-27]

#### Scenario: mensualidad confirmación → 201 + estado `MENSUALIDAD_PAGO` + CU-15SM trigger

- **Given** operator confirms a mensualidad cotización
  (`cotizacion.cobrar === false`)
- **When** `POST /api/v1/operacion/salidas` is invoked
- **Then** the renderer MUST send `Idempotency-Key` header (same scheme
  as REQ-OPS-152 — RFC 8785 normalized via `canonicalJson.ts`)
- **And** the backend response MUST include `tipo_salida: 'MENSUALIDAD'`
  and `estado: 'MENSUALIDAD_PAGO'`
- **And** the renderer MUST trigger CU-15SM print via
  `onConfirmado(uuidSalida)` callback (forward to HU-F7.3 — typed event
  envelope `bridge.imprimir('salida_mensualidad', { uuid_salida })`)
- **And** the renderer MUST NOT open PagoModal (no cobro — DEC-SUC-27
  invariant: mensualidad has no cash movement at exit; the fee is
  settled by the subscription)

### REQ-OPS-154 — `useRegistrarSalida` SWR mutation hook

The system SHALL export `useRegistrarSalida()` from
`apps/electron-sucursal/src/features/operacion/hooks/useRegistrarSalida.ts`
as a SWR mutation hook (`useSWRMutation`) returning
`{ trigger, isMutating, error }`. The `trigger(uuidIngreso)` function
MUST:
- Compute `Idempotency-Key` via `canonicalJson.ts` (RFC 8785)
- Call `POST /api/v1/operacion/salidas` with `{ uuid_ingreso }` body
- On `201`, return the parsed `SalidaReadForzado` payload
- On `409 salida_duplicada`, throw a typed `SalidaDuplicadaError` with
  the existing `uuid_salida` (from the 409 body — backend maps the
  partial unique index `one_exit_per_ingreso` violation to this 409)
- On `401`, call `useAuthStore.getState().clear()` AND dispatch the
  `parkos:auth:cleared` event (REQ-OPS-107..110 invariant preserved
  from F3.1; mirrored in `useCotizacion.ts:155-159`)

The hook MUST auto-detect `modo` from the input (no `modo` parameter
required by the caller — the renderer is path-indifferent per
DEC-MONO-01; downstream UX is discriminated by `response.tipo_salida`).
[Cite: proposal §3 Path 3 + §6 R5]

#### Scenario: hook cobertura — 3 tests + 401 invariant

- **Given** `useRegistrarSalida.test.ts` declares the canonical test set
- **When** `pnpm --filter electron-sucursal test -- --run useRegistrarSalida` executes
- **Then** the following 4 tests MUST pass:
  1. Rotación confirmation → `201` + payload shape
     (`SalidaReadForzado` with `tipo_salida='ROTACION'`,
     `estado='PENDIENTE_PAGO'`)
  2. Mensualidad confirmation → `201` + payload shape
     (`tipo_salida='MENSUALIDAD'`, `estado='MENSUALIDAD_PAGO'`)
  3. Doble-clic dedup: same `Idempotency-Key` → server returns cached
     `201` from `IdempotencyKeyMiddleware` (24h TTL) → no duplicate row
     in `prod.salidas`
  4. `401` logout invariant: hook MUST call `useAuthStore.getState().clear()`
     AND dispatch `parkos:auth:cleared` event (preserved F3.1 contract
     from REQ-OPS-107..110)

### REQ-OPS-155 — `Idempotency-Key` SHA-256 closure + drift guard

The system SHALL export
`useIdempotencyKey({method, path, body})` from
`apps/electron-sucursal/src/features/operacion/lib/idempotency.ts` as a
pure function returning `string` (hex SHA-256). The function MUST use
`canonicalJson.ts` (RFC 8785) to normalize the `body` parameter for
property-order independence — two consecutive calls with the same
`{method, path, body}` MUST return identical hex digests independent of
property order, whitespace, or platform byte-order. The renderer MUST
send this hex string as the `Idempotency-Key` HTTP header on every
mutant request to `POST /api/v1/operacion/salidas`.

The system SHALL block the drift that motivated F1.7 DEC-MONO-01
collapse: any future regression that reintroduces a
`POST /operacion/salidas/mensualidad` endpoint OR a
`mensualidad_no_vigente` error code MUST be caught by an AST walk that
fails CI. [Cite: proposal §3 Path 3 + §6 R2 + §8.4 drift guard]

#### Scenario: AST drift guard

- **Given** F7.2 lands on `dev` with a single `POST /operacion/salidas`
  endpoint and the `Idempotency-Key` SHA-256 closure
- **When** the CI drift guard runs
  (`grep -r 'POST.*salidas/mensualidad' apps/electron-sucursal/src`)
- **Then** the command MUST return 0 matches — F1.7 DEC-MONO-01
  collapsed the two endpoints into one; future regression MUST be
  blocked at AST level
- **And** the second guard
  (`grep -r 'mensualidad_no_vigente' apps/electron-sucursal/src`)
  MUST also return 0 matches — the error code never existed in the
  backend and MUST NOT leak into the renderer

### REQ-OPS-156 — `salida_duplicada` 409 handling

The system SHALL surface the `salida_duplicada` error from the backend
(HTTP 409 with body `{"error":"salida_duplicada","uuid_salida":"..."}`)
as a typed `SalidaDuplicadaError` thrown by
`useRegistrarSalida.trigger()`. The renderer MUST render the
`cotizar.errors.cotizacion_expirada` banner variant with the localized
text "Este ingreso ya tiene una salida registrada" and MUST NOT allow
re-submission. The renderer MAY reuse the returned `uuid_salida` to
navigate to a read-only detail view (out of scope for F7.2; navigation
is the caller's responsibility — the hook returns the existing
`uuid_salida` so the caller can chain). [Cite: plan.md:1724 + proposal §3 Path 1 + R1]

#### Scenario: doble POST dedup → 409 `salida_duplicada` (UI)

- **Given** an ingreso already has a salida no anulada (the partial
  unique index `one_exit_per_ingreso` from migration `0026` forbids a
  second non-anulada INSERT)
- **When** `useRegistrarSalida.trigger()` is called with the same
  `uuid_ingreso` (either doble-clic race, or operator navigation
  re-submit, or session replay)
- **Then** the hook MUST throw `SalidaDuplicadaError` with the existing
  `uuid_salida` (from the 409 body — backend maps the partial unique
  index violation to the `salida_duplicada` error code)
- **And** the renderer MUST NOT re-submit (button stays disabled)
- **And** the renderer MUST render the inline banner with localized
  text "Este ingreso ya tiene una salida registrada" (i18n key
  `salida.errors.salida_duplicada` in `operacion.json`)

### REQ-OPS-157 — Cupo release visible in `useOcupacion` polling

The system SHALL release the cupo (decrement active count) immediately
after the `POST /api/v1/operacion/salidas` returns 201. The
`useOcupacion` hook (F4.3, REQ-OPS-130) polls `mv_ocupacion_diaria`
every 10s (`OPERACION_REFRESH_INTERVAL_MS = 10_000`); the new cupo state
MUST be reflected within that 10s window. The renderer MUST NOT manually
update the occupancy cache — the server-driven recompute via
`cantidad_vehiculos_sucursal` view refresh is the only source of truth.
[Cite: plan.md:1771 + DEC-SUC-11]

#### Scenario: cupo visible en `useOcupacion` post-saida

- **Given** operator confirms a rotación salida (1 active ingreso → 0
  active for the `(uuid_sucursal, uuid_tipo_vehiculo)` tuple)
- **When** `POST /api/v1/operacion/salidas` returns 201 within 1s
- **Then** `useOcupacion` MUST reflect `activos -= 1` within 10s
  (`RefreshMvOcupacionWorker` from REQ-OPS-033 refreshes the MV at 10s
  cadence; `useOcupacion` polls at the same cadence)
- **And** the renderer MUST NOT bypass SWR to optimistically update the
  `useOcupacion` cache (server-driven recompute only — defends against
  client/server state divergence)

## Out of scope

- **HU-F8.1 — PagoModal (rotación → CU-04)**: separate change. F7.2 only
  triggers `open('pago', pagoAnchorId)` after a successful 201 with
  `tipo_salida='ROTACION'`; the modal lifecycle, payment processing,
  and the `salidas.estado='PAGADO'` UPDATE live in F8.1.
- **HU-F7.3 — Tiquetes CU-15S + CU-15SM print pipeline**: separate
  change. F7.2 only fires the typed `bridge.imprimir('salida_mensualidad', payload)`
  event envelope for the mensualidad branch; F7.3 owns the
  `escposBuilder.build('salida_mensualidad', payload)` + `bridge.imprimir`
  payload shape + DEC-SUC-27 verbatim reordering (CU-15S prints after
  pago, NOT at salida — F7.2 MUST NOT fire CU-15S).
- **Backend idempotency cache logic**: backend owns. F1.6
  `IdempotencyKeyMiddleware` (PR2) shipped the 24h TTL cache; F7.2 only
  sends the `Idempotency-Key` header. The server-side cache hashes raw
  request body bytes (not re-serialized JSON) as a fallback for client
  hash mismatch.
- **New `POST /operacion/salidas/mensualidad` endpoint**: does NOT exist
  and MUST NOT be created. Drift resolution: plan.md is stale; F1.7
  DEC-MONO-01 consolidates to ONE endpoint. The frontend calls the SAME
  endpoint for both modes; downstream UX is discriminated by
  `response.tipo_salida`.
- **`mensualidad_no_vigente` error code**: does NOT exist and MUST NOT
  be added. The backend returns `422 cotizacion_expirada` (V5) if the
  mensualidad lapsed mid-flow; the renderer treats that 422 as the
  "no longer mensualidad" path and surfaces the localized
  `cotizar.errors.cotizacion_expirada` banner.
- **Server-side `tipo_salida` derivation**: already in F1.7
  (DEC-MONO-01). The renderer is path-indifferent — it reads
  `response.tipo_salida` and routes.
- **`salidas.estado='PAGADO'` UPDATE**: owned by Fase 8. DEC-SUC-23
  verbatim — `salidas` has NO `valor` column; F7.2 only INSERTs.
- **Mensualidad detection client-side refactor**: F7.1 already
  short-circuits on `cobrar: false` (REQ-OPS-143). F7.2 only consumes
  that state via the `onConfirmar` callback.
- **`vigente_hasta` countdown re-validation on confirm**: F7.1's
  `useCountdown(15 * 60)` in `CotizacionPanel` (REQ-OPS-146) governs the
  operator UX. If the countdown hits 0 before the operator clicks
  Confirm, `CotizacionPanel` re-fetches via `onRecalcular`
  (REQ-OPS-145). Backend independently re-validates via V5
  (REQ-OPS-047) and returns `422 cotizacion_expirada` if stale.
- **Vite cache invalidation post-merge**: handled by AGENTS.md
  post-merge script (kill port 5173 + restart with `--force`); not part
  of the F7.2 PR.
- **Release branch + tag**: per gitflow, this change goes to `dev` only.

## Drift reconciliation traceability

The `plan.md` block for F7.2 (lines 1700-1741) mentions TWO endpoints
(`POST /operacion/salidas` and `POST /operacion/salidas/mensualidad`)
and a `mensualidad_no_vigente` error code. F1.7's DEC-MONO-01 (merged
2026-09-14, REQ-OPS-042..052 in `openspec/specs/operations/spec.md`)
consolidated to ONE endpoint with server-side `tipo_salida` derivation.
The drift is captured in the following traceability matrix. **The
canonical wire contract from F1.7 is the source of truth. F7.2 honors
the shipped reality.**

| `plan.md` claim | F1.7 reality | F7.2 resolution |
|---|---|---|
| `POST /operacion/salidas` (rotación) | exists (`operacion.py:322`) | use as canonical |
| `POST /operacion/salidas/mensualidad` | does NOT exist (`grep -r 'salidas/mensualidad' backend/` → 0 matches) | render and backend share `POST /operacion/salidas`; `tipo_salida` derived server-side from F1.8 `cobrar` flag |
| `mensualidad_no_vigente` error code (400) | does NOT exist (zero grep) | F1.7 returns `422 cotizacion_expirada` (V5) if mensualidad lapsed mid-flow; renderer surfaces `cotizar.errors.cotizacion_expirada` banner + re-derives flow from `Cotizacion.cobrar === false` at cotizar time |
| `tipo_salida` client-derived from pre-classification | server-derived from F1.8 `cobrar` flag (DEC-MONO-01) | client is **indifferent** to the path; reads `response.tipo_salida` and routes UX |
| 3-error-code surface (rotación/mensualidad/mensualidad_no_vigente) | F1.7 handler returns: `400 missing_sucursal_context`, `403 tenant_scope_violation`, `404 ingreso_no_encontrado`, `409 salida_duplicada`, `422` set (V2/V3/V4/V5), `500 iva_no_configurado` (pre-0026 only) | F7.2 UI error handler covers the F1.7 taxonomy; `mensualidad_no_vigente` MUST be removed from UI strings; AST guard at REQ-OPS-155 blocks reintroduction |

**WHY the drift exists**: the `plan.md` corpus was authored with a
2-endpoint mental model that F1.7 collapsed via DEC-MONO-01 for
atomicity (server-side derivation in a single transaction beats
client-side branch — concurrent operator actions on the same ingreso
cannot race because the server holds the lock until commit). The
`plan.md` text predates DEC-MONO-01 ratification; the merged `dev`
branch is authoritative.

**WHY F7.2 honors the merged reality (not the plan text)**: AGENTS.md
gitflow canon — `dev` is the integration branch and is always the
source of truth for downstream work. Re-introducing
`POST /operacion/salidas/mensualidad` would require a server-side
revert of DEC-MONO-01, which is out of scope for F7.2 and is not
justified by any documented operator requirement.

**Drift guard enforcement** (REQ-OPS-155): the AST walks below run in
the verify phase and MUST exit non-zero on any match — this blocks
silent regression to the 2-endpoint model in future PRs.

```bash
grep -r 'POST.*salidas/mensualidad' apps/electron-sucursal/src   # MUST return 0 matches
grep -r 'mensualidad_no_vigente' apps/electron-sucursal/src       # MUST return 0 matches
```

## Acceptance

F7.2 PR is mergeable when ALL of the following hold:

- `SalidaFlow` and `SalidaMensualidad` render their respective branches
  correctly (rotación path → PagoModal trigger; mensualidad path →
  CU-15SM print trigger). [REQ-OPS-152, REQ-OPS-153]
- `POST /api/v1/operacion/salidas` integration with `Idempotency-Key`
  works for both rotación and mensualidad from a single endpoint
  (server-side `tipo_salida` derivation). [REQ-OPS-152, REQ-OPS-153,
  REQ-OPS-154]
- Doble clic dedup is covered by the test (idempotency key uniqueness
  via RFC 8785 + UI in-flight disable via `useSWRMutation`'s
  `isMutating`). [REQ-OPS-154, REQ-OPS-156]
- `e2e/salida.spec.ts` 3 scenarios pass: rotación / mensualidad / doble
  clic idempotente. [REQ-OPS-154]
- AST drift guards return 0 matches:
  `grep -r 'POST.*salidas/mensualidad' apps/electron-sucursal/src` and
  `grep -r 'mensualidad_no_vigente' apps/electron-sucursal/src`.
  [REQ-OPS-155]
- `401` logout invariant preserved: hook calls
  `useAuthStore.getState().clear()` AND dispatches `parkos:auth:cleared`
  event. [REQ-OPS-154]
- Cupo release visible in `useOcupacion` within the 10s polling window.
  [REQ-OPS-157]
- `pnpm typecheck`, `pnpm lint`, `pnpm test` exit 0 across the full
  `electron-sucursal` workspace.
- `axe-core` reports 0 violations on `<SalidaFlow />` and
  `<SalidaMensualidad />` (WCAG 2.1 AA, RNF-022).
- All translation keys added to `operacion.json`:
  `salida.confirmar_rotacion`, `salida.confirmar_mensualidad`,
  `salida.errors.salida_duplicada`, `salida.errors.network`,
  `salida.errors.cotizacion_expirada`, `salida.success.uuid`
  (es-CO primary locale).
- Final diff `≤ 800 LOC` per the preflight budget — no
  `size:exception` needed (forecast ≈ 406 LOC per proposal §4).
