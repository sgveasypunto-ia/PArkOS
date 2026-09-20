# Delta Spec: HU-F8.1 — Modal de pago (efectivo/datáfono) con FE

> **Change**: `fase-8-1-pago-modal-fe` | **Phase**: sdd-spec | **HU ID**: HU-F8.1 (Fase 8 — CU-04 + CU-05)
> **Base spec**: `openspec/specs/operations/spec.md` (REQ-OPS-001..160; F7.2=152..157, F7.3=158..160). **Next free REQ-OPS gap**: 161..165.
> **Preflight**: pace=`auto`, artifact=`hybrid`, delivery=`single-pr`, budget=`800 LOC`, strict_tdd=`true`. **Artifact language**: English.
> **Drift anchor**: F7.2+F7.3 on `dev` ship `useRegistrarSalida` + `buildIdempotencyKey` + `escposBuilder.build('salida', ...)` + 4-tipo dispatcher. F8.1 EXTRACTS PagoModal out of `<PagoSheet />`, mirrors SWR pattern, ADDS 5th `'recibo_pago'` case.

## Context

HU-F8.1 closes F7.2 → CU-04 + CU-05 pivot on renderer. From confirmed salida rotación (F7.2 `tipo_salida='ROTACION'`), operator opens `pago` drawer via `useDashboardDrawerStore.open('pago', pagoAnchorId)`; `<PagoModal />` renders RHF+Zod form. On submit, `useRegistrarPago()` fires two POSTs (`/facturacion/factura` then `/facturacion/factura-pagos`) with `Idempotency-Key` SHA-256 (F7.2 helper), receives 201, then fires `bridge.imprimir('salida', ...)` (CU-15S, F7.3 builder) followed by `bridge.imprimir('recibo_pago', ...)` (new 5th dispatcher case). FE a consumidor final por defecto; FE con datos propios opcional con validación cliente-side (NIT módulo 11 + email RFC 5322). Pago SIEMPRE se registra; FE SIEMPRE se genera (BR1 CU-04).

**Drift reconciliation**: (1) `<PagoSheet />` scaffold on `dev` (240 LOC, 5 P1..P5 tests) — F8.1 EXTRACTS inner form into `<PagoModal />`, reduces sheet to 60-LOC shell; 5 P1..P5 MUST still pass. (2) `escposBuilder` 4-tipo exists — F8.1 ADDS 5th `'recibo_pago'` case. (3) DEC-SUC-28 numeration OWNED by F1.10 `assign_consecutivo`; renderer NEVER invents. (4) F7.3 `salidaPayloadSchema.medioPago` already present — F8.1 only POPULATES it. (5) F8.2 polling/retry on `dev` — F8.1 wires `useState<uuid_fe>` so F8.2 can take over.

## New requirements

### REQ-OPS-161 — `validarNitModulo11(input, dv)` with raw + normalized NIT support

System SHALL export `validarNitModulo11(input, dv)` from `apps/electron-sucursal/src/lib/validation/nit.ts`. Function MUST normalize input (strip non-digits), compute módulo 11 verification digit using weights `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59]` (DIAN Res. 000175/2021), and return `{ ok: true }` when `dv === dvEsperado`, else `{ ok: false, dvEsperado: string }`. Pure — no DOM, no `new Date()`, no `fetch`.

#### Scenario: reference NIT `800.123.456-7` módulo 11 verification
- **Given** `validarNitModulo11('800.123.456', '7')` is called
- **When** the function returns
- **Then** it MUST return `{ ok: true }`
- **And** `validarNitModulo11('800.123.456', '1')` MUST return `{ ok: false, dvEsperado: '7' }`
- **And** `validarNitModulo11('800123456', '7')` (digits-only) MUST return `{ ok: true }` (normalization)

### REQ-OPS-162 — `<PagoModal />` RHF + Zod discriminated union + vueltos en vivo + FE consumidor-final default

System SHALL export `<PagoModal uuidSalida total onConfirmado onCancelar />` from `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx`. Form MUST use discriminated union: `{ medio: 'efectivo', monto_recibido: number }` (`monto_recibido` MUST be ≥ `total`) | `{ medio: 'datafono', voucher: string }` (`voucher` MUST have `min(1)`). Optional `fe: { enabled: false } | { enabled: true, nit, dv, nombre, email }` defaulting to `enabled: false` (consumidor final NIT `222222222222222` per DEC-SUC-04 + BR2). Vueltos MUST compute `monto_recibido - total` via `useMemo` and format via `formatCOP` (F4.2). Copy "Factura a nombre del cliente (opcional); por defecto, factura a consumidor final" MUST appear next to FE checkbox (verbatim `plan.md:1845`). When `fe.enabled === true`, superRefine MUST call `validarNitModulo11(nit, dv)` and add custom Zod issue on path `['dv']` with message `nit_invalido:dv_esperado_<dvEsperado>`.

#### Scenario: vueltos en vivo + FE consumidor final default
- **Given** operator selects `medio: 'efectivo'` + `monto_recibido=100000` + `total=48790`
- **When** vueltos are computed
- **Then** display MUST show `vueltos = 51210` formatted via `formatCOP`
- **And** FE MUST default to consumidor final (NIT `222222222222222`) regardless of checkbox state (BR2)
- **And** "Confirmar pago" MUST be disabled when `medio === 'efectivo' && monto_recibido < total`, or when `medio === 'datafono' && voucher.trim() === ''`

### REQ-OPS-163 — `useRegistrarPago` two-step SWR mutation with `Idempotency-Key` SHA-256

System SHALL export `useRegistrarPago()` from `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` as `useSWRMutation` returning `{ trigger, isMutating, error }`. `trigger({ uuidSalida, payload })` MUST compute `Idempotency-Key` via `buildIdempotencyKey` (F7.2), POST to `/api/v1/facturacion/factura`, then on 201 POST a SECOND distinct `Idempotency-Key` (different `path` — server-side dedup per-path per F1.6) to `/api/v1/facturacion/factura-pagos`. Parse 201 with Zod mirror of `FacturaRead` (F1.9). On `401` → `useAuthStore.getState().clear()` + dispatch `parkos:auth:cleared` (F3.1). On `409 numeracion_agotada` → throw typed `NumeracionAgotadaError` (the ONLY FE error path that surfaces, per `plan.md:1956`). Other 4xx/5xx MUST be rethrown as `ParkosHttpError`.

#### Scenario: in-flight disable + 401 logout + numeracion_agotada banner
- **Given** operator confirms pago and `trigger()` fires
- **When** in-flight
- **Then** `isMutating` MUST be `true` and "Confirmar pago" MUST be disabled
- **And** on `401`, hook MUST call `useAuthStore.getState().clear()` + dispatch `parkos:auth:cleared`
- **And** on `409 numeracion_agotada`, hook MUST throw `NumeracionAgotadaError`; other 4xx/5xx propagate via `ParkosHttpError`
- **And** the two `Idempotency-Key` values MUST differ (per-path dedup)

### REQ-OPS-164 — CU-15S + recibo de pago print triggers after pago 201 (DEC-SUC-27 + DEC-SUC-28)

System SHALL trigger `bridge.imprimir('salida', payload)` (F7.3 builder) THEN `bridge.imprimir('recibo_pago', payload)` (F8.1 5th escposBuilder case) after successful pago 201. CU-15S MUST fire first (DEC-SUC-27 sequence). Both calls MUST be deferred via `queueMicrotask` and wrapped in try/catch — printer failure MUST `console.warn` and MUST NOT throw (F7.3 precedent at `SalidaMensualidad.tsx:66-81`). Recibo de pago payload MUST include `numero_recibo` from backend 201 (numeración propia `sucursal-YYYYMMDD-NNNNNN` per DEC-SUC-28 — backend F1.10 owns counter via `assign_consecutivo`; renderer NEVER invents).

#### Scenario: print sequence + recibo payload + printer failure isolation
- **Given** pago 201 returns `{ uuid_factura, uuid_factura_electronica, estado_fe, numero_recibo, ... }`
- **When** the trigger resolves
- **Then** `bridge.imprimir('salida', payload)` MUST fire first (CU-15S), then `bridge.imprimir('recibo_pago', { numero_recibo, ... })` fires second (5th escposBuilder case)
- **And** both calls MUST be deferred via `queueMicrotask` and wrapped in try/catch
- **And** printer failure MUST log `console.warn` and MUST NOT throw to React error boundary
- **And** `numero_recibo` MUST be the literal string from backend 201 — renderer MUST NOT compute/invent

### REQ-OPS-165 — FE failure isolation (BR5)

System SHALL NOT reverse the cobro if FE TopPoint fails. Backend (F1.10) returns 201 even when FE asynchronous dispatch fails — FE failure flows through `envio_dian` (cloud-side). Renderer MUST treat any 201 response as pago confirmed. The ONLY FE error path that surfaces to UI is `409 numeracion_agotada` (alerta `fe_numbering_exhausted` already seeded per `plan.md:1956`); other FE failures fall through silently and are re-queued by cloud sync worker. `<PagoModal />` MUST close and trigger print sequence after any 201 response. `FacturaDetalle` (F8.2) handles eventual `estado_fe` update via polling.

#### Scenario: FE failure does not block pago UI
- **Given** pago 201 returns `{ uuid_factura, uuid_factura_electronica, estado_fe: 'pendiente' }`
- **When** the trigger resolves
- **Then** `<PagoModal />` MUST close and print sequence (CU-15S + recibo de pago) MUST fire
- **And** `FacturaDetalle` (F8.2) handles eventual `estado_fe` update via polling — F8.1 does NOT block on FE state
- **And** `409 numeracion_agotada` MUST surface as a visible alerta; other FE failures fall through silently
- **And** drift guard `tests/static/test_pago_doesnt_block_on_fe.py` MUST assert `useRegistrarPago` does NOT retry on FE state changes (BR5)

## Drift reconciliation traceability

| Existing capability | Status | F8.1 delta |
|---|---|---|
| `<PagoSheet />` scaffold (240 LOC, 5 P1..P5 tests) | EXISTS | EXTRACTS inner form into `<PagoModal />`; sheet becomes 60-LOC shell. 5 P1..P5 MUST still pass. |
| `escposBuilder` 4-tipo dispatcher | UNCHANGED | ADDS 5th `'recibo_pago'` case — no modification of existing. |
| `useRegistrarSalida` SWR mutation (F7.2) | UNCHANGED | `useRegistrarPago` mirrors verbatim. |
| `buildIdempotencyKey` SHA-256 (F7.2) | UNCHANGED | F8.1 reuses as-is. |
| `useVueltos` hook (`plan.md:1853`) | DOES NOT EXIST | F8.1 inlines `useMemo(() => Math.max(0, recibido - total), [recibido, total])`. ABIERTO-200 follow-up. |
| `useCountdown` (F3.2) | REUSED F7.1/F7.2 | Not required by F8.1 — vueltos is pure arithmetic. |
| `useFacturaElectronica` + `FacturaElectronicaRetryPanel` (F8.2) | EXISTS on `dev` | F8.1 sets `useState<uuid_fe>` so F8.2 wires polling. NOT touched. |
| `formatCOP` (F4.2) | UNCHANGED | F8.1 reuses for vueltos display. |

## Out of scope

HU-F8.2 (FE polling — F8.2 owns). HU-F8.3 (reimpresión con costo). Backend FE numeration (F1.10). Backend TopPoint (cloud-only, PR11). SDK datáfono (BR6). Pago mixto (`plan.md:1875` OOS). Backend changes (zero — F1.9 ya cierra).

## Acceptance

F8.1 PR is mergeable when ALL hold: `validarNitModulo11('800.123.456', '7')` → `{ ok: true }`; `'1'` → `{ ok: false, dvEsperado: '7' }`; `'800123456'` → `{ ok: true }`. [REQ-OPS-161] `<PagoModal />` renders RHF + Zod discriminated union + vueltos en vivo + FE checkbox. [REQ-OPS-162] `useRegistrarPago` triggers `/factura` then `/factura-pagos` with TWO distinct `Idempotency-Key` SHA-256 closures. [REQ-OPS-163] After 201, `bridge.imprimir('salida', ...)` fires FIRST then `bridge.imprimir('recibo_pago', { numero_recibo, ... })` fires SECOND, both deferred + try/catch. Printer failure logs `console.warn` only. [REQ-OPS-164] FE failure does NOT reverse cobro; 201 with `estado_fe='pendiente'` closes modal + fires prints; `409 numeracion_agotada` surfaces a banner. [REQ-OPS-165] The 5 `<PagoSheet />` P1..P5 tests still pass. `e2e/pago.spec.ts` 6 scenarios pass. Drift guards `test_pago_form_is_atomic.py` + `test_pago_doesnt_block_on_fe.py` pass. `pnpm --filter electron-sucursal lint`, `typecheck`, `test` exit 0. axe-core WCAG 2.1 AA: 0 violations. Final diff `size:exception` (~1140 LOC > 800 budget) — user ratified at proposal §8.