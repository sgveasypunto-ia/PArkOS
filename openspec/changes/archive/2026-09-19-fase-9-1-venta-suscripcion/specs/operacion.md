# Delta Spec: HU-F9.1 — Venta de suscripción desde caja (wizard 4 pasos)

> **Change**: `fase-9-1-venta-suscripcion` | **Phase**: sdd-spec | **HU**: HU-F9.1 (Fase 9 — CU-06)
> **Base spec**: `openspec/specs/operations/spec.md` (REQ-OPS-001..175). **Next free gap**: 176..180.
> **Preflight**: pace=`auto`, artifact=`hybrid`, budget=`800 LOC` (forecast ~940 → `size:exception` pending).
> **Drift anchor**: F1.12 atomic backend (REQ-OPS-083..090 + XR5) + F8.1 `<PagoModal />` (REQ-OPS-162) + F7.2 `buildIdempotencyKey`. F9.1 is **renderer-only** — consumes F1.12 endpoint + reuses F8.1 PagoModal. F9.2 stub at `useSuscripcionesList.ts:80-98` MOVED into dedicated module (single responsibility).

## Context

Wizard 4 pasos (cliente → vehículos → plan → pago) from the caja screen. Calls `POST /api/v1/clientes/venta-suscripcion` (F1.12 single-commit, KD-VENTA-01) via `useVentaSuscripcion` SWR mutation; step 4 reuses F8.1 `<PagoModal />`. Prorrateo (A-09, DEC-VENTA-03) mirrored client-side via pure helper that verbatim mirrors F1.12 `calcular_prorrateo`. NO backend changes — F1.12 owns atomicity.

**NOTA DE ALCANCE** (`plan.md:2016`): F9.1 is a **producto amplificación**, NOT a literal CU-06 requirement (corpus describes admin-only sin cobro).

## ADDED Requirements

### REQ-OPS-176 — `<Venta />` wizard 4 pasos con RHF + Zod por paso

System SHALL export `<Venta />` from `apps/electron-sucursal/src/features/suscripciones/pages/Venta.tsx` as a 4-step wizard con `useState<{paso, cliente, placas, plan, medio_pago}>`. Cada step MUST `safeParse` BEFORE `setPaso(paso + 1)`: step 1 `cliente{nit,nombre,email}`; step 2 `placas: z.array(z.string()).min(1).max(2)`; step 3 `uuid_tipo_subscripcion: string.uuid()`; step 4 `medio_pago: z.enum(['efectivo','datafono'])` (F8.1 PagoModal reuse). [Cite: plan.md:2022-2023]

#### Scenario: step 1 NIT corto bloquea avance
- **Given** operador types `cliente` with `nit: '123'`
- **When** "Siguiente" fires
- **Then** form MUST NOT advance to step 2
- **And** MUST render the inline Zod error

#### Scenario: step 2 sin placas bloquea avance
- **Given** operador reaches step 2 con `placas: []`
- **When** "Siguiente" fires
- **Then** step 2 MUST NOT advance to step 3

### REQ-OPS-177 — `useVentaSuscripcion` SWR mutation with Idempotency-Key

System SHALL export `useVentaSuscripcion()` from `apps/electron-sucursal/src/features/suscripciones/hooks/useVentaSuscripcion.ts` as `useSWRMutation`. `trigger({cliente, placas, plan, medio_pago, cobrar_ahora})` MUST POST to `/api/v1/clientes/venta-suscripcion` con body `{cliente, placas, uuid_tipo_subscripcion, medio_pago, cobrar_ahora}` and header `Idempotency-Key: <SHA-256>` via F7.2 `buildIdempotencyKey`. The stub at `useSuscripcionesList.ts:80-98` MUST be MOVED here. [Cite: plan.md:2031]

#### Scenario: 201 atómico + cliente nuevo
- **Given** wizard submits cliente nuevo + 2 placas + plan + efectivo
- **When** backend returns 201
- **Then** `trigger()` MUST return `{uuid_subscripcion, uuid_cliente, uuid_vehiculos, uuid_factura, monto_prorrateado?}`
- **And** `bridge.imprimir('recibo_pago', payload)` MUST fire via `queueMicrotask` (F8.1 pattern)

#### Scenario: 401 dispara F3.1 logout invariant
- **Given** wizard submits with expired JWT
- **When** backend returns 401
- **Then** `useAuthStore.clear()` MUST fire
- **And** `parkos:auth:cleared` MUST dispatch on `window`

### REQ-OPS-178 — Prorrateo display client-side mirror (DEC-VENTA-03, A-09)

System SHALL export `calcularMontoProporcional(plan, fecha)` from `apps/electron-sucursal/src/features/suscripciones/lib/prorrateo.ts` as a pure helper. Formula: `valor_dia = plan.valor / plan.duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes` ONLY IF `fecha.day > 15` ELSE `null`. Wizard step 4 MUST display "Monto prorrateado: $X" badge when `monto_proporcional !== null`. [Cite: plan.md:2027 + F1.12 REQ-OPS-090]

#### Scenario: prorrateo mostrado cuando day > 15
- **Given** `plan={valor:30000, duracion_dias:30}` and `fecha=2026-09-19`
- **When** prorrateo evalúa
- **Then** MUST show `monto_proporcional = (30000/30) * 11 = 11000`
- **And** label MUST be "Monto prorrateado: $ 11.000"

#### Scenario: prorrateo null cuando day ≤ 15
- **Given** `fecha=2026-09-10`
- **When** prorrateo evalúa
- **Then** MUST return `null`
- **And** step 4 MUST NOT render the badge

### REQ-OPS-179 — Error mapping: 3 códigos backend en step 2

System SHALL define typed `VentaSuscripcionError` subclasses (or tagged union) for the 3 backend 422 codes. Wizard step 2 MUST render the inline message y MUST NOT advance:

- `suscripcion_duplicada_placa` → "Esta placa ya tiene una suscripción vigente"
- `tipo_vehiculo_incompatible` → "Este plan exige que todas las placas sean del mismo tipo"
- `cantidad_maxima_excedida` → bloquea agregar más placas que `plan.cantidad_maxima_vehiculos`

[Cite: plan.md:2037-2043 + F1.12 REQ-OPS-087..088 + REQ-OPS-089]

#### Scenario: placa duplicada en step 2
- **Given** operador types placa with vigente suscripción en esta sucursal
- **When** "Siguiente" fires
- **Then** step 2 MUST render the inline error
- **And** MUST NOT advance to step 3

#### Scenario: tipo_vehiculo_incompatible bloquea avance
- **Given** plan `mismo_tipo_vehiculo=true` + placas mixed auto/moto
- **When** "Siguiente" fires
- **Then** step 2 MUST render "Este plan exige que todas las placas sean del mismo tipo"

### REQ-OPS-180 — PagoModal reuse (F8.1) dentro de step 4

System SHALL reuse `<PagoModal />` from F8.1 inside wizard step 4. Step 4 IS the PagoModal con un "Confirmar venta" wrapper. Después de pago + venta 201, el wizard MUST close y navigate to `/suscripciones`. [Cite: OD-2 ratified]

#### Scenario: PagoModal montado en step 4
- **Given** operador llega a step 4 con todos los datos validados
- **When** step 4 mounts
- **Then** PagoModal MUST render con `total = monto_proporcional ?? plan.valor`
- **And** on pago 201 the wizard MUST close + navigate to `/suscripciones`

## REMOVED / RENAMED Requirements

None — F9.1 is a renderer-only consumer; F1.12 contract (REQ-OPS-083..090 + XR5) remains UNCHANGED.