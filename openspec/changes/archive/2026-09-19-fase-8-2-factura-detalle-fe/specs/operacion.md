# Delta Spec: HU-F8.2 — FacturaDetalle FE status + reintento

> **Change**: `fase-8-2-factura-detalle-fe` | **Phase**: sdd-spec | **HU ID**: HU-F8.2 (Fase 8 — CU-04 cierre DIAN)
> **Base spec**: `openspec/specs/operacion.md` (REQ-OPS-001..165; F8.1=161..165). **Next free REQ-OPS gap**: 166..170.
> **Preflight**: pace=`auto`, artifact=`hybrid`, delivery=`single-pr`, budget=`800 LOC`, strict_tdd=`true`. Artifact language: English.

## Context

F8.2 closes the F8.1 handoff: from pago `201`, the operator lands on `<FacturaDetalle />` (`/factura-electronica/:uuid`) showing `estado_dian` (`pendiente | enviado | aceptado | rechazado`) and CUFE when `aceptado`. Polls every 30s while not terminal; stops on both `aceptado` and `rechazado` (F1.10 DEC-FE-04). Reintentar fires `POST /factura-electronica/{uuid}/reintentar` — creates a NEW `envio_dian` row chained via `uuid_envio_padre`; NEVER UPDATE on `envio_dian` (F1.10 DEC-FE-02 + REQ-OPS-070). `409 numeracion_agotada` surfaces a `role="alert"` banner pointing at seeded `fe_numbering_exhausted` alerta (WCAG 2.1 AA).

## New requirements

### REQ-OPS-166 — `useFacturaElectronica` polling with terminal-state gating

`useFacturaElectronica(uuid)` SHALL poll `GET /api/v1/facturacion/factura-electronica/{uuid}` at `refreshInterval: (latest) => isTerminal(latest?.estado_dian) ? 0 : 30_000`. SWR treats `0` as "do not poll". Both `aceptado` and `rechazado` are terminal. [plan.md:1946-1947]

#### Scenario: polling stops on `aceptado`
- **Given** `latestData.estado_dian='aceptado'`
- **When** SWR re-evaluates `refreshInterval`
- **Then** callback MUST return `0` and polling MUST cease
- **And** operator MUST NOT see "Reintentar" (REQ-OPS-167 invariant)

### REQ-OPS-167 — `<FacturaDetalle />` routed page

`<FacturaDetalle />` at `pages/FacturaDetalle.tsx` SHALL mount at `<Route path="/factura-electronica/:uuid" element={<ProtectedRoute><FacturaDetalle/></ProtectedRoute>}>` in `App.tsx`. MUST render localized `estado` (`fe.estado.pendiente|enviado|aceptado|rechazado`), `cufe` when `aceptado` (hidden otherwise), and "Reintentar" button ONLY when `estado_dian === 'rechazado'`. Button MUST be disabled while `useSWRMutation.isMutating`. [plan.md:1948]

#### Scenario: rejected state shows reintentar
- **Given** `estado_dian='rechazado'`
- **When** `<FacturaDetalle />` renders
- **Then** "Reintentar" MUST be visible
- **And** clicking MUST call `useReintentarFE.trigger(uuid_fe)`

### REQ-OPS-168 — `useReintentarFE` `useSWRMutation`

`useReintentarFE()` SHALL be `useSWRMutation`. `trigger(uuid)` MUST compute `Idempotency-Key` via `buildIdempotencyKey` (F7.2) and POST `/api/v1/facturacion/factura-electronica/{uuid}/reintentar`. `201` parses to `{ uuid_envio, estado:'pendiente', uuid_envio_padre }`. `409 numeracion_agotada` throws typed `NumeracionAgotadaError` (the ONLY FE error UI surfaces per plan.md:1956). `401` clears auth (F3.1). Mirrors F7.2 `useRegistrarSalida.ts:73-101`.

#### Scenario: 409 `numeracion_agotada` surfaces alerta
- **Given** `estado_dian='rechazado'` and operator clicks "Reintentar"
- **When** backend returns `409 numeracion_agotada`
- **Then** hook MUST throw `NumeracionAgotadaError`
- **And** `<FacturaDetalle />` MUST render `fe.errors.numeracion_agotada` banner with `role="alert"`

### REQ-OPS-169 — Reintentar re-engages polling via SWR `mutate`

`useReintentarFE.trigger()` MUST `mutate('/facturacion/factura-electronica/{uuid}')` after `201` so SWR resumes `refreshInterval: 30_000` (new chain tip is `pendiente`, non-terminal). `mutate()` MUST be awaited before `trigger()` returns (R1). [proposal §3 Path 2]

#### Scenario: reintentar causes re-poll
- **Given** `estado_dian='rechazado'` and operator clicks "Reintentar"
- **When** backend returns `201` with `estado='pendiente'`
- **Then** `useFacturaElectronica` MUST revalidate within same commit
- **And** panel MUST resume 30s polling with `estado='pendiente'`

### REQ-OPS-170 — PagoSheet navigates to `<FacturaDetalle />` after pago 201

`PagoSheet.tsx` SHALL call `navigate('/factura-electronica/<uuid_fe>')` after pago `201` when `result.factura_electronica?.uuid` is a string. Closes F8.1 §3.5 handoff. `typeof` narrow MUST tolerate `z.unknown()` (ABIERTO-F8.2-01). [proposal §0]

#### Scenario: post-pago navigation
- **Given** operator confirms pago and `useRegistrarPago.trigger()` returns `201` with `factura_electronica.uuid`
- **When** trigger resolves
- **Then** PagoSheet MUST call `navigate('/factura-electronica/<uuid_fe>')`
- **And** `<FacturaDetalle />` MUST mount with `useParams().uuid`

## Drift reconciliation

| Capability | `dev` | F8.2 delta |
|---|---|---|
| `useFacturaElectronica` | EXISTS, no gating | Tighten `refreshInterval`; +2 tests (F4/F5) |
| `FacturaElectronicaRetryPanel` | EXISTS, inline fetch | Consume `useReintentarFE`; drop inline `parkosFetch` |
| PagoSheet navigate-after-201 | NOT BUILT | Add `navigate('/factura-electronica/<uuid>')` after 201 |
| `App.tsx` route | NOT BUILT | Add `<Route>` + `<ProtectedRoute>` wrapper |
| `FacturaReadSchema.factura_electronica: z.unknown()` | KEPT | **ABIERTO-F8.2-01** follow-up (F8.3 or F8.x) |
| i18n `fe.estado.*` | Single key | Split into 4 estados; add `fe.errors.numeracion_agotada` |
| `e2e/fe.spec.ts` | NOT BUILT | NEW 3 scenarios: estado / polling+stops / reintentar |

## Out of scope

HU-F8.3 (reimpresión con costo). Backend FE state machine (F1.10). Cloud TopPoint (cloud-only). Strongly typing `FacturaReadSchema.factura_electronica` (ABIERTO-F8.2-01). Vite cache invalidation. Release branch + tag. Backend changes: zero.

## Acceptance

F8.2 PR mergeable when ALL hold: polling stops on BOTH terminal states (F4/F5); `<FacturaDetalle />` renders estado + CUFE if `aceptado` + "Reintentar" if `rechazado`; `useReintentarFE` POSTs with `Idempotency-Key` (`201` → `{uuid_envio, estado:'pendiente', uuid_envio_padre}`; `409` → `NumeracionAgotadaError`; `401` → auth cleared); `mutate()` re-engages polling after `201`; PagoSheet navigates to `/factura-electronica/{uuid_fe}` after pago `201`; `App.tsx` route registered; `e2e/fe.spec.ts` 3 pass; `pnpm typecheck`/`lint`/`test`/`e2e -- fe.spec.ts` exit 0; axe-core WCAG 2.1 AA: 0 violations; diff ≤ 800 LOC.