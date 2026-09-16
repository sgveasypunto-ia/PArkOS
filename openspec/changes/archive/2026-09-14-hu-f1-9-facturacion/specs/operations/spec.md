# Spec Delta: operations — hu-f1-9-facturacion

> **Delta for change**: `hu-f1-9-facturacion`
> **Capability**: `operational`
> **Date**: 2026-09-14
> **Source of truth**: `openspec/changes/hu-f1-9-facturacion/{exploration.md, proposal.md}`
> **Status**: draft (sdd-spec phase)
> **Precedente upstream**: this delta extends the `operational` capability already consolidated in `openspec/specs/operations/spec.md` (last REQ-OPS-NNN vigente: **REQ-OPS-052** after the merge of HU-F1.7 in commit `b4f1b45`). HU-F1.9 introduces **11 new requirements** (`REQ-OPS-053..063`) covering the consolidated single handler `POST /api/v1/facturacion/factura` (atomic 4-table insert), the secondary handler `POST /api/v1/facturacion/factura-pagos` (voucher validation), the 6 server-side validations V1..V6 (V1 salida facturable, V2 cliente cuando `fe_con_datos=true`, V3 IVA configurado, V4 detalle items coherentes, V5 NIT módulo 11 DIAN, V6 total coherente ±0.01 COP), the KD-FACT-01 single-commit invariant, the KD-FACT-02 `SELECT … FOR SHARE` per-row lock on `prod.tarifas_sucursal`, the DEC-FACT-06 server-derived `uuid_cliente`, and the DEC-FACT-04 no-retención / DEC-FACT-07 no-`forma_pago` catálogo decisions. REQ-OPS-001..052 remain unchanged.
>
> **Pre-apply verification findings** (incorporated into this delta):
>
> - **R2 RESOLVED**: `fn_facturas_inmutable` trigger is NOT needed because `prod.facturas` is `[L-E]` (bi-temporal versioning via composite PK `(uuid, fecha_retencion_hasta)`, NOT append-only immutability). DEC-FACT-01 reinterpreted: **F1.9 itself never UPDATEs rows in `prod.facturas`**; state transitions happen via NEW rows with composite PK per bi-temporal versioning. Defense in depth at handler + repo layers only — no DB trigger needed.
> - **R3 PARTIALLY RESOLVED**: `prod.facturas` is **NOT partitioned** (migration 0001 lines 607-626 have no `postgresql_partition_by`) → partial unique index `one_factura_per_salida ON prod.facturas (uuid_salida) WHERE uuid_salida IS NOT NULL` **IS feasible**. Closes TOCTOU between concurrent cajeros attempting to invoice the same `uuid_salida`. `prod.factura_pagos` **IS partitioned by `RANGE (fecha_retencion_hasta)`** (migration 0001 line 716) → partial unique index infeasible. Defense via BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness` analogía migration 0004 lines 35-66 (`fn_factura_pagos_reverso_uniqueness`).

## Purpose

HU-F1.9 closes the **billing** half of CU-04 by exposing two handlers that together materialize the internal `factura` lifecycle:

- `POST /api/v1/facturacion/factura` — atomic 4-table transaction (`prod.facturas` + `prod.factura_detalle` + `prod.factura_impuestos` + `prod.factura_pagos`) gated by 6 server-side validations V1..V6 and a single `await session.commit()` (KD-FACT-01).
- `POST /api/v1/facturacion/factura-pagos` — voucher validation for datáfono (`400 voucher_requerido` when `medio_pago='datafono'` without `referencia`).

The handler enforces NIT módulo 11 validation per DIAN Resolución 000175 de 2021 (DEC-FACT-09, Variant A canónica) via Pydantic v2 `@field_validator` on both `ClientesCreate.numero_identificacion` (always when `tipo_identificador='NIT'`) and `FacturaItemConDatosPropios.numero_identificacion` (only when `fe_con_datos=true`). `uuid_cliente` is **server-derived** in `FacturaRead` (DEC-FACT-06) — never persisted as a column. MVP applies **no retención** (DEC-FACT-04, deferred to Fase 4) and uses Pydantic `Literal[...]` for `medio_pago` (DEC-FACT-07 Opción A, no DB catalog).

**Defense in depth** has 5 layers (D-HU-F1.9-8): (a) DB partial unique index `one_factura_per_salida` on `prod.facturas` (closes TOCTOU between concurrent cajeros); (b) DB BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness` on `prod.factura_pagos` (closes TOCTOU on pagos); (c) repo typed exceptions (`SalidaNoFacturableError`, `ClienteNoEncontradoFacturaError`, `NitInvalidoError`, `TotalNoCoherenteError`, `VoucherRequeridoError`); (d) handler 12-step chain + single commit + tenant scope post-V1; (e) AST walk single-commit + step order.

> **Migration 0027 conditional**: introduced ONLY IF pre-apply verification finds both `fn_facturas_inmutable` trigger AND `one_factura_per_salida` partial unique index missing. Per R2 RESOLVED above, `fn_facturas_inmutable` is NOT required (bi-temporal versioning handles immutability); `one_factura_per_salida` partial unique index is the only DB-layer defense actually needed.

---

## ADDED Requirements

### REQ-OPS-053 — POST /api/v1/facturacion/factura contract: 12-step handler with KD-3 tenant scope, `Cache-Control: no-store`, Idempotency-Key header

**Given** the FastAPI router `api/v1/facturacion.py` is newly mounted via `r.include_router(facturacion.router)` in `api/v1/__init__.py`
**When** the handler `create_factura` is invoked with `payload: FacturaCreate`, `session: AsyncSession`, `ctx: TenantContext`, and `_claims: None = Depends(_facturacion_issuer_dep)` where `_facturacion_issuer_dep = requires_issuer("admin-", "cajero-")`
**Then** the handler MUST execute the strict 12-step order: (1) KD-3 issuer claims + `no_store_headers`; (2) V1 salida facturable SELECT; (3) tenant scope post-V1; (4) V2 cliente SELECT cuando `fe_con_datos=true`; (5) V3 IVA configurado; (6) V4 detalle items coherentes; (7) KD-FACT-02 `SELECT … FOR SHARE` per-row sobre `prod.tarifas_sucursal`; (8) V6 total recompute server-side (±0.01 COP); (9) INSERT `prod.facturas` [L-E]; (10) INSERT `prod.factura_detalle` (N rows) + `prod.factura_impuestos` (1 row) + `prod.factura_pagos` (1 row); (11) single `await session.commit()`; (12) response shape `FacturaRead`.
**And** the handler MUST respond `201 Created` with `FacturaRead` carrying `uuid`, `created_at`, `uuid_sucursal`, `uuid_ingreso`, `uuid_salida`, `subtotal`, `descuento`, `total`, `uuid_cliente` (server-derived, DEC-FACT-06), `items: list[FacturaItemRead]`, `estado: Literal["emitida","pagada","anulada"]` (derived from `V_FACTURA_ESTADO`).
**And** the handler MUST set the header `Cache-Control: no-store` on every 2xx, 4xx, and 5xx response.
**And** the handler MUST rely on the PR2 `Idempotency-Key` HTTP header for retry deduplication (DEC-IDEM-01 reuse from F1.6); the payload MUST NOT carry `correlacion_id` (rejected by `extra='forbid'`).
**RFC 2119**: MUST (12-step order, response shape, `Cache-Control: no-store`, issuer dep, Idempotency-Key delegation).

#### Scenario: T1 happy path ROTACION returns 201 with `estado="emitida"` and 4 tables populated atomically

**Given** an existing `prod.salidas` row with `uuid_salida=:p`, `uuid_ingreso=:i`, `uuid_sucursal=:s`, and no prior `prod.facturas` row referencing `:p`
**And** a vigente `prod.impuestos` row with `nombre='IVA'` and `porcentaje=0.19` (post-MIGRATION 0026 deploy)
**And** a `cajero-:s` JWT (or `admin-` with `:s` in `sucursales_permitidas`)
**When** the client sends `POST /api/v1/facturacion/factura` with
`{"uuid_salida":":p","items":[{"tipo":"servicio","concepto":"parqueo","cantidad":1,"valor_unitario":5000}],"subtotal":5000,"total":5950,"medio_pago":"efectivo","fe_con_datos":false}`
**Then** the server MUST insert one row in `prod.facturas`, one row in `prod.factura_detalle`, one row in `prod.factura_impuestos` (IVA snapshot), one row in `prod.factura_pagos`, all in a single `await session.commit()`.
**And** MUST respond `201 Created` with `FacturaRead{estado:"emitida", uuid_cliente:null, ...}` and `Cache-Control: no-store`.

#### Scenario: T2 happy path CONSUMIDOR_FINAL with `fe_con_datos=false` returns 201 sin cliente

**Given** an existing `prod.salidas` row with `uuid_salida=:p`
**When** the client sends `POST /facturacion/factura` with `fe_con_datos=false` (no `fe_datos_cliente`)
**Then** the server MUST respond `201 Created` with `FacturaRead{uuid_cliente:null, ...}`
**And** MUST NOT insert any row in `prod.clientes`.

#### Scenario: T8 atomicidad — INSERT `factura_detalle` FK violation rolls back `facturas` row

**Given** an existing `prod.salidas` row with `uuid_salida=:p`
**And** the payload contains an item with `uuid_tarifa_sucursal=:fake` referencing a non-existent `prod.tarifas_sucursal` row
**When** the handler reaches Step 10 `crear_factura_detalle_bulk`
**Then** PostgreSQL MUST raise a FK constraint violation (pgcode `23503`)
**And** the handler MUST NOT call `await session.commit()` (single-commit invariant, KD-FACT-01)
**And** on exit, `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos` MUST have zero new rows for `:p` (single TX rollback, no orphans).

### REQ-OPS-054 — V1: salida existe y es facturable

**Given** `FacturaCreate.uuid_salida` referencing a non-existent salida OR an already-facturada salida (a row in `prod.facturas` exists with `uuid_salida=:p` and estado derivado in `{emitida, pagada}`)
**When** `POST /facturacion/factura` is called
**Then** the handler MUST raise `HTTPException(status_code=404, detail={"error":"salida_no_encontrada", "uuid_salida":str(payload.uuid_salida)}, headers={"Cache-Control":"no-store"})`.
**And** the response body MUST NOT leak PostgreSQL error codes (pgcode `23505`, `23503`, etc.) or internal error codes.
**And** the handler MUST exit before Step 9; NO row MUST be inserted in any of the 4 tables.
**RFC 2119**: MUST (single 404 discriminator for "not found" and "already facturada", no pgcode leak, no INSERT on failure).

#### Scenario: salida inexistente returns 404 sin pgcode leak

**Given** no row in `prod.salidas` with `uuid=:p`
**When** the client sends `POST /facturacion/factura` with `{"uuid_salida":":p",...}`
**Then** the response MUST be `404 Not Found` with body `{"error":"salida_no_encontrada","uuid_salida":":p"}` and `Cache-Control: no-store`.
**And** the response body MUST NOT contain `"23503"`, `"23505"`, `"FOREIGN KEY"`, or any pgcode string.
**And** `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos` MUST have zero new rows.

#### Scenario: salida ya facturada returns 404 (DEC-FACT-01 unified discriminator)

**Given** `prod.salidas` with `uuid=:p` exists
**And** `prod.facturas` contains a row with `uuid_salida=:p` and `estado` derivado in `{emitida, pagada}`
**When** the client sends `POST /facturacion/factura` with `{"uuid_salida":":p",...}`
**Then** the response MUST be `404 Not Found` with body `{"error":"salida_no_encontrada","uuid_salida":":p"}` (operationally equivalent to "no existe").

### REQ-OPS-055 — V2: cliente existe cuando `fe_con_datos=true`

**Given** `FacturaCreate.fe_con_datos=true` AND `FacturaItemConDatosPropios.numero_identificacion` does not match any active row in `prod.clientes` (`estado='activo'` AND `vigente_hasta IS NULL`)
**When** `POST /facturacion/factura` is called
**Then** the handler MUST raise `HTTPException(status_code=404, detail={"error":"cliente_no_encontrado", "numero_identificacion":"..."}, headers={"Cache-Control":"no-store"})`.
**And** the handler MUST exit before Step 9; NO row MUST be inserted in any of the 4 tables.
**And** the handler MUST NOT auto-create the cliente — V2 returns 404 to caller; caller decides whether to POST `/clientes` first.
**RFC 2119**: MUST (V2 lookup miss → 404, no auto-create, no INSERT on failure).

#### Scenario: cliente no existe con `fe_con_datos=true` returns 404

**Given** no active row in `prod.clientes` with `numero_identificacion=:n` (any `tipo_identificador`)
**When** the client sends `POST /facturacion/factura` with `fe_con_datos=true` and `fe_datos_cliente.numero_identificacion=":n"`
**Then** the response MUST be `404 Not Found` with body `{"error":"cliente_no_encontrado","numero_identificacion":":n"}` and `Cache-Control: no-store`.
**And** `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos`, `prod.clientes` MUST have zero new rows.

#### Scenario: V2 SKIPPED cuando `fe_con_datos=false` (consumidor final)

**Given** `payload.fe_con_datos=false` (no `fe_datos_cliente`)
**When** the client sends `POST /facturacion/factura`
**Then** the handler MUST skip V2 entirely; MUST NOT query `prod.clientes`.
**And** MUST respond `201 Created` with `FacturaRead{uuid_cliente:null, ...}` (DEC-FACT-08 consumidor final).

### REQ-OPS-056 — V3: IVA configurado (defense-in-depth guard)

**Given** `prod.impuestos` does NOT contain a row with `nombre='IVA'` AND `estado='activo'` AND `porcentaje > 0` (KD-IVA blocker pre-MIGRATION 0026)
**When** `POST /facturacion/factura` is called
**Then** the handler MUST raise `HTTPException(status_code=500, detail={"error":"iva_no_configurado"}, headers={"Cache-Control":"no-store"})`.
**And** the handler MUST exit before Step 9; NO row MUST be inserted in any of the 4 tables.
**RFC 2119**: After MIGRATION 0026 (F1.7) is deployed, this 500 path **MUST NEVER** fire. This REQ serves as a defense-in-depth guard; the post-0026 runtime contract is `validar_iva_configurado() -> True` always.

#### Scenario: iva_no_configurado pre-MIGRATION 0026 deploy returns 500 (defense only)

**Given** `prod.impuestos` has NO row with `nombre='IVA'`
**When** the client sends `POST /facturacion/factura`
**Then** the response MUST be `500 Internal Server Error` with body `{"error":"iva_no_configurado"}` and `Cache-Control: no-store`.

#### Scenario: IVA configurado post-MIGRATION 0026 returns 201 (happy path proceeds)

**Given** `prod.impuestos` has a row with `nombre='IVA'`, `porcentaje=0.19`, `estado='activo'`, `vigente_desde <= NOW() < vigente_hasta` (post-MIGRATION 0026 deploy)
**When** the client sends `POST /facturacion/factura` (happy path)
**Then** V3 MUST return `True`; the handler MUST proceed to V4 and beyond.
**And** MUST respond `201 Created` (assuming all other validations pass).

### REQ-OPS-057 — V4: detalle items coherentes

**Given** `FacturaCreate.items=[]` OR any item with `cantidad <= 0` OR `valor_unitario < 0` OR `tipo not in {"servicio", "producto"}` OR `concepto` is empty
**When** `POST /facturacion/factura` is called
**Then** the handler MUST raise `HTTPException(status_code=422, detail={"error":"detalle_invalido", "min_items":1}, headers={"Cache-Control":"no-store"})` for the empty-items case, OR a per-item index error for granular cases.
**And** the handler MUST exit before Step 7 (no lock acquired); NO row MUST be inserted in any of the 4 tables.
**RFC 2119**: MUST (`items` MUST have `min_length=1` enforced at Pydantic schema level; `cantidad` MUST be `> 0`; `valor_unitario` MUST be `>= 0`; `tipo` MUST be one of `{servicio, producto}`).

#### Scenario: T5 items vacío returns 422 detalle_invalido

**Given** a valid `FacturaCreate` payload with `items=[]`
**When** the client sends `POST /facturacion/factura`
**Then** Pydantic MUST reject with `422 Unprocessable Entity` and body `{"error":"detalle_invalido","min_items":1}`.
**And** NO INSERT in any of the 4 tables.

#### Scenario: item con cantidad negativa returns 422 con item index

**Given** a valid payload where `items[0].cantidad=-1`
**When** the client sends `POST /facturacion/factura`
**Then** the response MUST be `422 Unprocessable Entity` with body referencing `items[0].cantidad`.

### REQ-OPS-058 — V5: NIT módulo 11 DIAN Resolución 000175 de 2021

**Given** `FacturaItemConDatosPropios.tipo_identificador="NIT"` AND `dv` mismatches the algorithm-computed DV per DIAN spec
**When** the Pydantic v2 `@field_validator("numero_identificacion")` runs (either via `FacturaItemConDatosPropios` in `/facturacion/factura` payload OR via `ClientesCreate` in any `/clientes` POST payload)
**Then** validation MUST raise a Pydantic validation error mapped to `HTTPException(status_code=422, detail={"error":"nit_invalido", "dv_esperado":<int>, "dv_recibido":"<string>"}, headers={"Cache-Control":"no-store"})`.
**And** the validator MUST NOT proceed to insert any row in `prod.clientes` or `prod.facturas`.
**RFC 2119**: MUST (Variant A canónica per DIAN Resolución 000175 de 2021; `dv_calculado = sum_ponderada % 11`; NO alternative algorithms; weights `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]` applied **right-to-left** over NIT digits without DV; NIT normalized: strip non-digits, strip leading zeros, minimum 5 digits).

**Algorithm** (canonical reference for `repo/nit_modulo11.py::validar_nit_modulo11`):

1. Strip non-digits from NIT (`"800.123.456-7"` → `"800123456"`).
2. Strip leading zeros (`"000123"` → `"123"`).
3. Compute weighted sum: `sum = Σ(d_i × w_i)` for `i=0..len-1`, where `d_i` is the i-th digit from RIGHT to LEFT, and `w_i` cycles through `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]`.
4. Compute `mod = sum % 11`.
5. `dv_calculado = mod` (Variant A canónica per DIAN, NOT `11 - mod` Variant B).
6. If `dv_calculado != int(dv_input)` → reject with `dv_esperado=dv_calculado`, `dv_recibido=dv_input`.

#### Scenario: T3 NIT válido `800.123.456-7` (DV=7) MUST pass

**Given** a `FacturaItemConDatosPropios` block with `tipo_identificador="NIT"`, `numero_identificacion="800.123.456-7"`, `dv="7"`
**When** Pydantic v2 validation runs
**Then** `validar_nit_modulo11("800.123.456-7", "7")` MUST return `True` (Variant A canónica).
**And** the request MUST proceed (assuming other validations pass).

#### Scenario: T4 NIT inválido `800.123.456-5` (DV=5) MUST fail con dv_esperado=7

**Given** a `FacturaItemConDatosPropios` block with `tipo_identificador="NIT"`, `numero_identificacion="800.123.456-5"`, `dv="5"`
**When** Pydantic v2 validation runs
**Then** validation MUST fail with body `{"error":"nit_invalido","dv_esperado":7,"dv_recibido":"5"}` and HTTP `422 Unprocessable Entity`.
**And** NO INSERT en `prod.clientes` o `prod.facturas`.

#### Scenario: edge — NIT con ceros a la izquierda normaliza

**Given** `numero_identificacion="000123-1"` (`tipo_identificador="NIT"`)
**When** validation runs
**Then** the helper MUST normalize to `"123"`, compute `dv_esperado("123")=1`, and `dv="1"` MUST pass.

#### Scenario: edge — NIT con guión y puntos normaliza

**Given** `numero_identificacion="800.123.456-7"`, `dv="7"`
**When** validation runs
**Then** the helper MUST strip non-digits to `"800123456"`, compute `dv_esperado("800123456")=7`, and `dv="7"` MUST pass.

#### Scenario: edge — DV no-dígito MUST reject

**Given** `numero_identificacion="800.123.456"`, `dv="X"` (non-digit)
**When** validation runs
**Then** validation MUST fail with `dv_recibido="X"` and HTTP `422`.

#### Scenario: V5 SKIPPED cuando `tipo_identificador="CC"` (no NIT)

**Given** a `FacturaItemConDatosPropios` block with `tipo_identificador="CC"` (no NIT)
**When** Pydantic v2 validation runs
**Then** the módulo 11 validator MUST NOT run; `dv` is optional for `CC`.
**And** the request MUST proceed (assuming other validations pass).

### REQ-OPS-059 — V6: total coherente ±0.01 COP

**Given** `FacturaCreate.total` differs from server-computed `total_server = subtotal_items + iva - retencion` by more than `Decimal("0.01")` COP
**When** `POST /facturacion/factura` is called (after V4 items validated, before Step 9 INSERT)
**Then** the handler MUST raise `HTTPException(status_code=422, detail={"error":"total_no_coherente", "total_recibido":"<decimal>", "total_calculado":"<decimal>", "diferencia":"<decimal>"}, headers={"Cache-Control":"no-store"})`.
**And** the handler MUST exit before Step 9; NO row MUST be inserted in any of the 4 tables.
**RFC 2119**: MUST (tolerance ±0.01 COP, i.e. 1 centavo colombiano; `iva = subtotal * porcentaje_iva` where `porcentaje_iva` comes from `prod.impuestos.IVA.porcentaje`; `retencion = Decimal("0")` per DEC-FACT-04 MVP).

#### Scenario: T6 total differs by >0.01 COP returns 422 total_no_coherente

**Given** items totaling `subtotal=5000`, IVA `= 950` (5000 × 0.19), so `total_server=5950`
**And** payload `total=6000` (differs by `Decimal("50")` from server-computed `5950`)
**When** the client sends `POST /facturacion/factura`
**Then** the response MUST be `422 Unprocessable Entity` with body `{"error":"total_no_coherente","total_recibido":"6000","total_calculado":"5950","diferencia":"50"}`.
**And** NO INSERT en cualquier de las 4 tablas.

#### Scenario: total exacto (diff=0) MUST pass V6

**Given** items totaling `subtotal=5000`, `total_server=5950`
**And** payload `total=5950` (differs by `Decimal("0")` from server-computed)
**When** the client sends `POST /facturacion/factura`
**Then** V6 MUST return `True`; handler proceeds to Step 9 (assuming all other validations pass).

#### Scenario: total differs by exactly 0.01 COP MUST pass V6 (tolerance boundary)

**Given** `total_server=5950`, payload `total=5950.01` (differs by `Decimal("0.01")`)
**When** the client sends `POST /facturacion/factura`
**Then** V6 MUST return `True` (boundary inclusive).

### REQ-OPS-060 — KD-FACT-01: single `await session.commit()` invariant

**RFC 2119**: The `create_factura` handler body in `api/v1/facturacion.py` MUST contain **EXACTLY ONE** `await session.commit()` call. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements **MUST NOT** appear anywhere in the handler body or its callees (KD-FACT-01 + DEC-FACT-01).

**Defense**: AST walk `tests/static/test_factura_handler_single_commit.py` parses the `create_factura` function body using `ast.walk` BFS via `iter_child_nodes` recursion (per F1.7 pattern) and asserts:

- `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and getattr(n.value.func, "attr", "") == "commit"]) == 1`.
- `len([n for n in ast.walk(body) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "begin_nested"]) == 0`.
- No `SAVEPOINT` or `RELEASE SAVEPOINT` string literals in the body.

#### Scenario: T10 AST walk enforces exactly 1 commit call

**Given** the source file `api/v1/facturacion.py` containing `create_factura`
**When** `tests/static/test_factura_handler_single_commit.py` runs
**Then** the AST walk MUST assert `commit_count == 1`; if multiple commits OR any `begin_nested` OR any `SAVEPOINT` is detected, the test MUST fail with a typed error referencing the offending AST node line number.

#### Scenario: handler with two `commit()` calls MUST fail AST walk

**Given** a hypothetical handler with `await session.commit()` at line 50 and `await session.commit()` at line 80
**When** the AST walk runs
**Then** `commit_count == 2` MUST trigger test failure with message `"KD-FACT-01 violation: expected 1 commit, found 2 at lines [50, 80]"`.

### REQ-OPS-061 — KD-FACT-02: `SELECT … FOR SHARE` per-row sobre `prod.tarifas_sucursal`

**Given** any `FacturaItemCreate.uuid_tarifa_sucursal IS NOT NULL` in `payload.items`
**When** `POST /facturacion/factura` is called (after V4 items validated, before Step 9 INSERT)
**Then** the handler MUST execute `SELECT … FOR SHARE` per-row on `prod.tarifas_sucursal` for each unique `uuid_tarifa_sucursal` referenced.
**And** the lock MUST be held until the single `await session.commit()` (KD-FACT-01) at Step 11.
**And** the lock MUST be per-row (NOT per-table) — only the referenced rows are locked, not all `tarifas_sucursal` rows.
**And** the handler MUST NOT acquire locks on `prod.salidas` (V1 read by PK) or `prod.clientes` (V2 read by UK).
**RFC 2119**: MUST (per-row `FOR SHARE` on every `uuid_tarifa_sucursal` referenced; lock held until `session.commit()`; per-row scope prevents global serialization).

#### Scenario: T9 concurrent TX cannot UPDATE locked `tarifas_sucursal` row

**Given** a `create_factura` handler holding `FOR SHARE` on `prod.tarifas_sucursal.uuid=:t` (locked by TX 1)
**When** a concurrent TX 2 attempts `UPDATE prod.tarifas_sucursal SET valor=999 WHERE uuid=:t`
**Then** TX 2 MUST block (FOR SHARE conflicts with FOR UPDATE / UPDATE).
**And** TX 2 MUST unblock only after TX 1 commits or rolls back.

#### Scenario: items sin `uuid_tarifa_sucursal` MUST skip lock acquisition

**Given** `payload.items=[]` is rejected by V4 (so this scenario starts post-V4 with valid items)
**And** items have `uuid_tarifa_sucursal=null` (no tarifa referenced)
**When** Step 7 executes
**Then** the handler MUST NOT execute any `SELECT … FOR SHARE` (no lock to acquire).
**And** MUST proceed to Step 8 (V6 recompute).

### REQ-OPS-062 — POST /api/v1/facturacion/factura-pagos: voucher_requerido

**Given** `FacturaPagoAdicionalCreate.medio_pago="datafono"` AND `referencia` is empty (length 0) OR missing (`None`)
**When** `POST /api/v1/facturacion/factura-pagos` is called
**Then** the handler MUST raise `HTTPException(status_code=400, detail={"error":"voucher_requerido"}, headers={"Cache-Control":"no-store"})`.
**And** the handler MUST NOT insert any row in `prod.factura_pagos`.
**RFC 2119**: MUST (`medio_pago="datafono"` REQUIRES non-empty `referencia`; `medio_pago in {"efectivo","tarjeta","transferencia","mixto"}` accepts `referencia=null`).

#### Scenario: T7 `medio_pago="datafono"` sin `referencia` returns 400 voucher_requerido

**Given** `FacturaPagoAdicionalCreate{medio_pago:"datafono", referencia:null, valor:5000, uuid_factura:":f"}`
**When** the client sends `POST /facturacion/factura-pagos`
**Then** the response MUST be `400 Bad Request` with body `{"error":"voucher_requerido"}` and `Cache-Control: no-store`.
**And** `prod.factura_pagos` MUST have zero new rows for `:f`.

#### Scenario: T7b `medio_pago="datafono"` con `referencia` returns 201

**Given** `FacturaPagoAdicionalCreate{medio_pago:"datafono", referencia:"VCHR-12345", valor:5000, uuid_factura:":f"}` and `prod.facturas` row `:f` exists with `estado="emitida"`
**When** the client sends `POST /facturacion/factura-pagos`
**Then** the response MUST be `201 Created` with `FacturaPagoRead`.

#### Scenario: T7c `medio_pago="efectivo"` sin `referencia` returns 201 (no voucher required)

**Given** `FacturaPagoAdicionalCreate{medio_pago:"efectivo", referencia:null, valor:5000, uuid_factura:":f"}`
**When** the client sends `POST /facturacion/factura-pagos`
**Then** the response MUST be `201 Created` (no voucher required for cash).

#### Scenario: T7d `medio_pago="datafono"` con `referencia=""` (empty string) returns 400

**Given** `FacturaPagoAdicionalCreate{medio_pago:"datafono", referencia:"", valor:5000, uuid_factura:":f"}`
**When** the client sends `POST /facturacion/factura-pagos`
**Then** the response MUST be `400 Bad Request` with body `{"error":"voucher_requerido"}` (empty string treated as missing).

### REQ-OPS-063 — DEC-FACT-06: `uuid_cliente` derivado server-side

**RFC 2119**: The `FacturaRead.uuid_cliente` field MUST be server-derived via lookup against `prod.clientes` by `numero_identificacion` provided in `fe_datos_cliente` when `fe_con_datos=true`. It MUST NOT be persisted as a column in `prod.facturas` (the table column does not exist in migration 0001 lines 607-654; 4FN design).

**Behavior**:

- When `fe_con_datos=true`: server resolves `cliente_uuid` via V2 lookup; `FacturaRead.uuid_cliente` MUST equal the resolved `cliente.uuid`.
- When `fe_con_datos=false`: `FacturaRead.uuid_cliente` MUST be `null`; the response MUST NOT include cliente data.
- The response MUST NEVER echo a client-supplied `uuid_cliente` field (rejected by `extra='forbid'`).
- Future HUs MAY add `prod.facturas.uuid_cliente` FK column and backfill; F1.9 does NOT create the FK.

#### Scenario: T1 cliente derivado server-side cuando `fe_con_datos=true`

**Given** `payload.fe_con_datos=true` AND `prod.clientes` has an active row with `numero_identificacion=":n"` and `uuid=:c`
**When** the client sends `POST /facturacion/factura` and V2 resolves `cliente_uuid=:c`
**Then** the response MUST be `201 Created` with `FacturaRead{uuid_cliente=":c", ...}`.

#### Scenario: T2 `uuid_cliente=null` cuando `fe_con_datos=false` (consumidor final)

**Given** `payload.fe_con_datos=false`
**When** the client sends `POST /facturacion/factura`
**Then** the response MUST be `201 Created` with `FacturaRead{uuid_cliente:null, ...}`.
**And** the response body MUST NOT include any `cliente` object.

#### Scenario: payload con `uuid_cliente` client-supplied MUST be rejected by `extra='forbid'`

**Given** a payload that includes `"uuid_cliente":":c"` (client attempts to inject)
**When** Pydantic v2 validation runs
**Then** validation MUST fail with HTTP `422 Unprocessable Entity` and message referencing `extra_forbidden`.

---

## Cross-Cutting Requirements

### REQ-OPS-XR1 — Defense in depth: 5 layers

**Given** the 4-table atomic insert + NIT validation + immutability invariants are critical to billing correctness
**When** any layer of the defense fails
**Then** the remaining 4 layers MUST contain the failure:

1. **(a) DB layer — partial unique index `one_factura_per_salida`**: `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_factura_per_salida ON prod.facturas (uuid_salida) WHERE uuid_salida IS NOT NULL` (closes TOCTOU between concurrent cajeros attempting the same `uuid_salida`; `prod.facturas` is NOT partitioned per migration 0001 lines 607-626, so the partial unique index is feasible). UniqueViolationError (pgcode `23505`) maps to 409 `factura_duplicada`.
2. **(b) DB layer — BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness`**: analogía `fn_factura_pagos_reverso_uniqueness` (migration 0004 lines 35-66). Closes TOCTOU on `prod.factura_pagos` rows where `tipo_movimiento='pago'`. `prod.factura_pagos` IS partitioned by `RANGE (fecha_retencion_hasta)` (migration 0001 line 716), so partial unique index is infeasible — BEFORE INSERT trigger is the only DB-layer defense.
3. **(c) Repo layer — typed exceptions**: `SalidaNoFacturableError(uuid_salida)`, `ClienteNoEncontradoFacturaError(numero_identificacion)`, `NitInvalidoError(dv_esperado, dv_recibido)`, `TotalNoCoherenteError(total_recibido, total_calculado, diferencia)`, `VoucherRequeridoError(medio_pago)`. Each exception maps to a typed HTTP error response; pgcode NEVER appears in response body, headers, or info+ logs.
4. **(d) Handler layer — 12-step chain + single `await session.commit()`**: `create_factura` enforces strict 12-step order (locked by AST walk `test_factura_handler_step_order.py`); single commit (KD-FACT-01, locked by AST walk `test_factura_handler_single_commit.py`); tenant scope check post-V1 (KD-S2 analog from F1.7); V6 total coherence ±0.01 COP before INSERT; KD-FACT-02 `FOR SHARE` lock acquired before bulk INSERT; `Cache-Control: no-store` on all 2xx/4xx/5xx responses.
5. **(e) AST walk layer — invariant enforcement**: `tests/static/test_factura_handler_single_commit.py` (~80 LOC) and `tests/static/test_factura_handler_step_order.py` (~80 LOC) enforce KD-FACT-01 + literal step order.

**RFC 2119**: MUST (each layer independently tested; failure of any one layer MUST be contained by the other 4).

#### Scenario: layer (a) — concurrent INSERT same `uuid_salida` raises `UniqueViolationError` → 409

**Given** `prod.facturas` row with `uuid_salida=:p` already exists
**When** concurrent TX attempts `INSERT INTO prod.facturas (uuid_salida, ...) VALUES (:p, ...)`
**Then** PostgreSQL MUST raise `UniqueViolationError` (pgcode `23505`).
**And** the handler MUST translate to `HTTPException(status_code=409, detail={"error":"factura_duplicada", "uuid_salida":":p"})`.

#### Scenario: layer (b) — BEFORE INSERT trigger rejects second `pago` for same `uuid_factura`

**Given** `prod.factura_pagos` already has a row with `uuid_factura=:f` and `tipo_movimiento='pago'`
**When** concurrent INSERT attempts a second `pago` row for `:f`
**Then** the BEFORE INSERT trigger MUST `RAISE EXCEPTION` with message `fn_factura_pagos_init_pago_uniqueness: pago duplicado para uuid_factura=:f`.
**And** the handler MUST translate to `HTTPException(status_code=409, detail={"error":"pago_duplicado", "uuid_factura":":f"})`.

### REQ-OPS-XR2 — `Cache-Control: no-store` header on all responses

**Given** billing responses must never be cached (defense in depth against cache poisoning)
**When** any handler under `/api/v1/facturacion/` responds (2xx, 4xx, or 5xx)
**Then** the response MUST carry `Cache-Control: no-store` header.

#### Scenario: 201 Created carries `Cache-Control: no-store`

**When** `POST /facturacion/factura` returns `201 Created`
**Then** the response MUST carry `Cache-Control: no-store`.

#### Scenario: 422 nit_invalido carries `Cache-Control: no-store`

**When** `POST /facturacion/factura` returns `422 nit_invalido`
**Then** the response MUST carry `Cache-Control: no-store`.

### REQ-OPS-XR3 — DEC-FACT-01 amended: F1.9 itself never UPDATEs rows in `prod.facturas`

**RFC 2119**: The F1.9 handler `create_factura` MUST perform only INSERT operations on `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, and `prod.factura_pagos`. State transitions on a `prod.facturas` row (e.g., `emitida → pagada`) MUST happen via NEW rows with the bi-temporal composite PK `(uuid, fecha_retencion_hasta)` — NOT via UPDATE.

**Behavior**:

- `prod.facturas` is `[L-E]` (bi-temporal versioning, migration 0001 lines 607-626); immutability is provided by the composite PK, NOT by an `fn_facturas_inmutable` DB trigger.
- `fn_factura_detalle_inmutable`, `fn_factura_impuestos_inmutable`, `fn_factura_pagos_inmutable` triggers (migration 0001 lines 2024-2088) still apply to the `[A]`-class detail/impuestos/pagos tables.
- Anulación (state `emitida → anulada`) is OUT OF F1.9 scope (deferred to HU-F1.13 via `prod.anulaciones` workflow — Fase 7+).
- F1.9 does NOT modify the `fn_*_inmutable` triggers and does NOT introduce `fn_facturas_inmutable` (R2 RESOLVED — bi-temporal PK handles immutability).

#### Scenario: state transitions happen via NEW rows con composite PK

**Given** a `prod.facturas` row with `uuid=:f, fecha_retencion_hasta=2028-01-01T00:00:00Z, estado=emitida`
**When** a future HU creates a state transition (e.g., `emitida → pagada`)
**Then** the future HU MUST INSERT a new row with `uuid=:f, fecha_retencion_hasta=2028-01-02T00:00:00Z` (different composite PK timestamp) and MUST NOT UPDATE the original row.

---

## Authoring & Test Inventory

- **Author**: Parkos Dev <dev@parkos.local>
- **Commits**: conventional commits in neutral Spanish, NO AI attribution (Co-Authored-By trailers forbidden per global project rules).
- **Tests**: ~16 tests across 6 files.
  - `tests/unit/test_facturacion_factura.py` (~400 LOC, **6 tests**: T1 ROTACION happy path, T2 consumidor final, T3 NIT válido `800.123.456-7`, T4 NIT inválido `800.123.456-5`, T5 detalle vacío, T6 total no coherente).
  - `tests/unit/test_validar_nit_modulo11.py` (~150 LOC, **4 tests**: DIAN reference case, DV mismatch, leading zeros, dots/dashes).
  - `tests/unit/test_facturacion_factura_pagos.py` (~150 LOC, **2 tests**: T7 voucher ausente, T7b voucher presente).
  - `tests/integration/test_factura_atomicidad_db.py` (~250 LOC, **2 tests**: T8 atomicidad rollback si detalle falla, T9 lock FOR SHARE sobre tarifas).
  - `tests/static/test_factura_handler_single_commit.py` (~80 LOC, **1 AST walk**: T10 KD-FACT-01 single-commit invariant).
  - `tests/static/test_factura_handler_step_order.py` (~80 LOC, **1 AST walk**: 12-step order).
- **Predecessor conventions reused**: F1.7 KD-FORZADO-01 verbatim, KD-7 pre-flight, 12-step handler chain, single-commit invariant, partial unique index pattern, AST walk pattern, `Idempotency-Key` header. F1.8 PL/pgSQL `calcular_cotizacion` `FOR SHARE` lock continuity (KD-1 analog → KD-FACT-02). F1.5 `repo/versioned.py::close_and_insert`. F1.4 bi-temporal `bitemporal_vigente_predicate`. F1.3 partial unique index pattern (`unique_active_sesion_per_user`).

## References

- `openspec/changes/hu-f1-9-facturacion/exploration.md` (16 sections, R1..R7)
- `openspec/changes/hu-f1-9-facturacion/proposal.md` (12 sections, DEC-FACT-01..09, KD-FACT-01..02, KD-NIT-01..07, 5-layer defense, 10 acceptance tests T1..T10)
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/specs/operational/spec.md` (canonical precedent, REQ-OPS-042..052)
- `openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/specs/operational/spec.md` (KD-FORZADO-01 verbatim reuso)
- `openspec/specs/operations/spec.md` (REQ-OPS-001..052 merged)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (lines 435-452 `clientes`, 607-654 `facturas`+`factura_detalle` `[L-E]` bi-temporal, 688-717 `factura_pagos` partitioned, 1378 `fk_facturas_uuid_salida`, 2024-2088 `fn_*_inmutable` triggers)
- `backend/packages/parkos_core/migrations/versions/0004_alertas_not_null.py` (lines 35-66 `fn_factura_pagos_reverso_uniqueness` analogía for `fn_factura_pagos_init_pago_uniqueness`)
- `plan.md` (HU-F1.9 lines 891-935 — 330 LOC, 4 tasks T1..T4)