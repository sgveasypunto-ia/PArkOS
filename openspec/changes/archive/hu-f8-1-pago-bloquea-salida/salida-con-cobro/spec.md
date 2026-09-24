# salida-con-cobro Specification

## Purpose

Define the atomic combined salida+factura+pago endpoint (rotación)
and the mensualidad branch with explicit operator confirmation. The
flow MUST guarantee `prod.salidas` and `prod.facturas` are born
together or not at all — closing the operator gap where an unpaid
vehiculo was recorded as exited and the cupo released.

## Requirements

### Requirement: REQ-SCC-001 — Atomic handler `create_salida_con_cobro` (rotación)

The system SHALL expose `POST /api/v1/operacion/salida-con-cobro`
executing a 16-step handler in ONE `await session.commit()`:
KD-3 → V1 → tenant → V2-V5 → KD-S7 `SELECT … FOR SHARE` on
`prod.tarifas_sucursal` → pre-mint `salidas.uuid` AND `facturas.uuid`
(bidirectional) → INSERT `prod.facturas(uuid_salida=pre-mint)` →
INSERT `prod.factura_detalle` (N) → INSERT `prod.factura_impuestos` →
INSERT `prod.factura_pagos` → INSERT `prod.salidas(uuid_factura=pre-mint)`
→ single `session.commit()` → MV refresh try/log/continue → response.

#### Scenario: rotación happy path returns 201

- GIVEN open `ingreso`, vigente `tarifas_sucursal`, IVA configured, `cobrar:true` from F1.8
- WHEN the operator POSTs `{"uuid_ingreso":":p","medio_pago":"efectivo","items":[{...}],"subtotal":5000,"total":5950}` with `Idempotency-Key: <uuid>`
- THEN one row MUST be INSERTed in each of `prod.salidas`, `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos` in ONE commit
- AND the response MUST be `201` with `{uuid_factura, uuid_salida, numero_recibo, items, total, cotizacion_snapshot}` and `Cache-Control: no-store`.

#### Scenario: rollback at any INSERT step leaves zero rows

- GIVEN `factura_detalle.uuid_tarifa_sucursal` references a missing row
- WHEN the handler reaches the `factura_detalle` INSERT
- THEN Postgres MUST raise FK violation; the handler MUST NOT call `commit()`
- AND all 5 tables MUST have zero new rows for `:p`.

### Requirement: REQ-SCC-002 — Idempotency via F7.2 middleware

The system MUST reuse F7.2 `IdempotencyKeyMiddleware` with
`buildIdempotencyKey` SHA-256 from request body. Retries with the
same key MUST return the cached one.

#### Scenario: retry with same `Idempotency-Key` returns cached 201

- GIVEN a successful prior POST with `Idempotency-Key: <k>`
- WHEN the client retries with the same key
- THEN the cached `201` MUST be returned verbatim.

### Requirement: REQ-SCC-003 — V5 cotización guard for rotación

The handler MUST reject rotación when F1.8 returns
`{cobrar:false,motivo:"mensualidad_vigente"}`. The client MUST be
told to use `/salida-mensualidad`.

#### Scenario: rotación request for monthly subscriber returns 409

- GIVEN F1.8 returns `{cobrar:false}`
- WHEN the operator POSTs `/salida-con-cobro`
- THEN the response MUST be `409 Conflict` with body `{"error":"mensualidad_no_aplica"}`
- AND `prod.salidas`, `prod.facturas`, `prod.factura_pagos`, `prod.alerta` MUST have zero new rows.

### Requirement: REQ-SCC-004 — Mensualidad branch with explicit confirmation

The system SHALL expose `POST /api/v1/operacion/salida-mensualidad`
with body field `confirmado_operador_explicit: bool = False`. When
`false` or absent, reject `409 {"error":"confirmacion_operador_requerida"}`.
When `true`, INSERT one `prod.salidas` row AND one `prod.alerta`
(`tipo_alerta='confirmacion_explicit_mensualidad'`) in ONE commit.

#### Scenario: mensualidad without flag returns 409

- GIVEN `confirmado_operador_explicit` is `false` or absent
- WHEN the operator POSTs `/salida-mensualidad`
- THEN the response MUST be `409` with `{"error":"confirmacion_operador_requerida"}`
- AND `prod.salidas`, `prod.alerta` MUST have zero new rows.

#### Scenario: mensualidad with flag inserts salida + alerta same-TX

- GIVEN an open `ingreso` with active subscription and `confirmado_operador_explicit=true`
- WHEN the operator POSTs
- THEN one row MUST be INSERTed in `prod.salidas` and one in `prod.alerta` (`tipo_alerta='confirmacion_explicit_mensualidad'`)
- AND both MUST commit in ONE `await session.commit()`.

### Requirement: REQ-SCC-005 — DIAN FE numbering deferred

The handler MUST NOT call `assign_consecutivo` and MUST NOT INSERT
into `prod.factura_electronica` or `prod.envio_dian`. FE numbering
is the cloud dispatcher's responsibility post-sync.

#### Scenario: handler does not block on DIAN emission

- GIVEN the combined insert committed
- WHEN the handler returns `201`
- THEN `prod.factura_electronica` MUST have zero new rows for `:f`.

### Requirement: REQ-SCC-006 — Cupo released at commit

Cupo is released ONLY when `session.commit()` succeeds. MV
`prod.mv_ocupacion_diaria` is refreshed post-commit
(try/log/continue). Commit failure leaves `V_INGRESO_ESTADO=Activo`.

#### Scenario: commit failure leaves cupo unchanged

- GIVEN an `ingreso` counting toward the cupo
- WHEN the handler rolls back (any INSERT failed before `commit()`)
- THEN `prod.mv_ocupacion_diaria` MUST NOT show the ingreso as finalized
- AND `V_INGRESO_ESTADO` MUST remain `Activo` for `:p`.