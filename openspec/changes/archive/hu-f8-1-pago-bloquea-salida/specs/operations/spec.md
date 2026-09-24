# Delta for Operations

Change `hu-f8-1-pago-bloquea-salida` RE-DELTs `operations`: Step 8
INSERT of `prod.salidas` moves to post-pago commit (atomic combined
endpoint, approach (a) ratified 2026-09-23). V1-V5 validations and
`one_exit_per_ingreso` index preserved — only the *order* of writes
changes.

## ADDED Requirements

### Requirement: REQ-OPS-053 — Legacy rotación returns 410 Gone

`POST /api/v1/operacion/salidas` SHALL return `410 Gone` body
`{"error":"endpoint_deprecated","replacement":"POST
/api/v1/operacion/salida-con-cobro"}` when rotation is requested.

#### Scenario: legacy rotación POST returns 410

- GIVEN F1.8 yields `cobrar:true` for `:p`
- WHEN the client POSTs `{"uuid_ingreso":":p"}`
- THEN the response MUST be `410 Gone` with the replacement hint
- AND `prod.salidas` MUST have zero new rows.

### Requirement: REQ-OPS-054 — Mensualidad requires explicit confirmation + alerta

Handler MUST accept `confirmado_operador_explicit: bool = False`.
When `false` or absent, reject `409
{"error":"confirmacion_operador_requerida"}`. When `true`, INSERT
one `prod.salidas` row AND one `prod.alerta`
(`tipo_alerta='confirmacion_explicit_mensualidad'`, `estado='abierta'`)
in ONE commit. Catalog value added via migration
`0027_add_alert_type_mensualidad_confirmacion.py`.

#### Scenario: mensualidad without flag returns 409

- GIVEN `confirmado_operador_explicit=false`
- WHEN the operator POSTs `/operacion/salidas`
- THEN the response MUST be `409` with `{"error":"confirmacion_operador_requerida"}`
- AND `prod.salidas`, `prod.alerta` MUST have zero new rows.

#### Scenario: mensualidad with flag inserts salida + alerta same-TX

- GIVEN `confirmado_operador_explicit=true`
- WHEN the operator POSTs
- THEN one row MUST be INSERTed in `prod.salidas` AND one in `prod.alerta` (`tipo_alerta='confirmacion_explicit_mensualidad'`)
- AND both MUST commit in ONE `await session.commit()`.

### Requirement: REQ-OPS-055 — Combined 16-step handler with single commit

The combined handler `create_salida_con_cobro` MUST execute 16
steps in ONE `await session.commit()`. The `prod.salidas` INSERT
MUST run AFTER `prod.factura_pagos` to preserve the
"factura+salida born together" invariant. Legacy
`test_salida_handler_step_order.py` MUST be replaced by
`test_salida_con_cobro_handler_step_order.py`.

#### Scenario: 16-step handler AST walker asserts single commit

- GIVEN the combined handler registered
- WHEN `tests/static/test_salida_con_cobro_handler_step_order.py` runs
- THEN the AST walk MUST assert exactly ONE `await session.commit()`
- AND MUST assert: `factura_pagos INSERT` precedes `salidas INSERT` precedes `session.commit()`.

## MODIFIED Requirements

### Requirement: REQ-OPS-042 — POST /operacion/salidas: rotación retires (REQ-OPS-053); mensualidad gated (REQ-OPS-054)

(Previously: legacy 12-step handler INSERTed `prod.salidas` at Step
8 BEFORE any cobro — the operator gap. Legacy endpoint now retired
for rotación; mensualidad stays with explicit flag.)

Legacy `POST /api/v1/operacion/salidas` MUST delegate rotación to
`410 Gone` (REQ-OPS-053) and MUST gate mensualidad through
`confirmado_operador_explicit` (REQ-OPS-054). MUST set
`Cache-Control: no-store`, MUST be guarded by `_ingreso_issuer_dep =
requires_issuer("operador-","admin-")` (KD-3), MUST delegate retry
deduplication to the `Idempotency-Key` header (DEC-IDEM-01).
**RFC 2119**: MUST (410 Gone, explicit-confirmation gate, header,
issuer, idempotency).

#### Scenario: legacy rotación POST returns 410 Gone

- GIVEN F1.8 yields `cobrar:true` for `:p`
- WHEN the client POSTs `{"uuid_ingreso":":p"}`
- THEN the response MUST be `410 Gone` with the replacement hint
- AND `prod.salidas` MUST have zero new rows.

#### Scenario: mensualidad without explicit flag returns 409

- GIVEN `confirmado_operador_explicit` absent
- WHEN the client POSTs `/operacion/salidas`
- THEN the response MUST be `409 Conflict` with `{"error":"confirmacion_operador_requerida"}`
- AND `Cache-Control: no-store` MUST be present.

### Requirement: REQ-OPS-048 — INSERT `prod.salidas` `[A]` append-only; combined handler INSERTs LAST after `factura_pagos`

(Previously: Step 8 INSERT ran BEFORE the cobro. Combined handler
INSERTs `prod.salidas` LAST, after `factura_pagos`, in ONE commit.)

Combined handler MUST follow the write order in REQ-OPS-055
(facturas → factura_detalle → factura_impuestos → factura_pagos →
salidas, pre-mint UUIDs, ONE `session.commit()`). ALL inserts
MUST commit atomically (KD-FACT-01, KD-S7 lock continuity). Pre-mint
UUID pair resolved BEFORE first INSERT (no UPDATE on `prod.salidas`
— REVOKE + trigger + partial unique index respected). `tipo_salida`
MUST NOT be persisted (DEC-SUC-21-NEW). **RFC 2119**: MUST (write
order, single commit, bidirectional pre-mint, atomic rollback).

#### Scenario: rollback on `factura_detalle` FK violation

- GIVEN a bad `uuid_tarifa_sucursal`
- WHEN the handler reaches `factura_detalle` INSERT
- THEN Postgres MUST raise FK violation (pgcode `23503`)
- AND `commit()` MUST NOT be called
- AND all 5 tables MUST have zero new rows for `:p`.

## REMOVED Requirements

None — V1-V5 validations (REQ-OPS-043..047), `tipo_salida`
(REQ-OPS-049), alertas same-TX (REQ-OPS-050), `one_exit_per_ingreso`
index (REQ-OPS-051), and `impuestos.IVA` seed (REQ-OPS-052) all
remain binding; only the *order* of writes changed.