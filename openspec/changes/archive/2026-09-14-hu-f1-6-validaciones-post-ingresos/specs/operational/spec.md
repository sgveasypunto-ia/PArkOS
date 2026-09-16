# Spec Delta: hu-f1-6-validaciones-post-ingresos

> **Change**: `hu-f1-6-validaciones-post-ingresos`
> **Capability**: `operational`
> **Date**: 2026-09-14
> **Source of truth**: `openspec/changes/hu-f1-6-validaciones-post-ingresos/proposal.md`
> (D-HU-F1.6-1..13, 10 KDs adopted), `exploration.md` (16 sections, V1..V9 +
> KD-FORZADO-01, files-to-touch §15), `plan.md` (HU-F1.6 lines 786–798,
> DEC-SUC-11 línea 426, DEC-SUC-21 línea 590, DEC-SUC-22 línea 595,
> KD-FORZADO A-04 addendum #4), `modelo_datos_er.mmd` (tables `ingreso`
> 577–596 `[L-E]`, `cantidad_vehiculos_sucursal` 428–446 `[V]`,
> `tipos_vehiculo` 87–104 `[V]`, `tarifas_sucursal` 406–426 `[V]`,
> `subscripciones_cliente` `[V]`, `subscripcion_vehiculos` `[V]`,
> `vehiculos` `[V]`, `alerta` `[L-W]`, `mv_ocupacion_diaria` post-F1.5).
>
> **Precedente upstream**: this delta extends the `operational` capability
> already consolidated in `openspec/specs/operations/spec.md` (last
> REQ-OPS-NNN vigente: REQ-OPS-033 after the merge of HU-F1.5 in commit
> `fc72adb`). HU-F1.6 introduces 8 new requirements (REQ-OPS-034..041)
> covering V1, V2, V3, V4, V5, V6, V8, and V9+KD-FORZADO-01; REQ-OPS-001..033
> remain unchanged. V7 (bi-temporal canónico) inherits from F1.4 / F1.5
> base capability and is documented in `design.md` as an implementation
> invariant (no new REQ needed).

## Purpose

HU-F1.6 closes the server-side validation prerequisite for F6 — Ingreso
vehicular (CU-01) by moving all four client-side validations from
`web_sucursal/src/lib/validation/placa.ts` (A-03) into the backend
handler `POST /api/v1/operacion/ingresos`. Today the handler
(`api/v1/operacion.py:92-114`) is a thin pass-through to
`repo.event.record_event`: it accepts whatever the Pydantic schema allows
and inserts the `[L-E]` event without any business validation, violating
the corpus rule "single source of truth" and exposing `prod.ingreso` to
stale clients, alternate consumers, and missing-CUPO enforcement.

The change enforces 9 server-side validations (V1..V9) plus the
KD-FORZADO-01 bypass contract — `[FORZADO: <motivo ≥10 chars>]` parsed
from `observaciones` (A-04) — as the only operational bypass for
V1/V2/V3/V6. The endpoint URL stays unchanged (backwards compatible
with F1.5's PR5); only the response body gains `tipo_entrada`,
`forzado_en_creacion`, `motivo_forzado` and the error body gains typed
422 / 409 discriminators.

`tipo_entrada` (`MENSUALIDAD | ROTACION`) is derived server-side from
`uuid_subscripcion_cliente` (DEC-SUC-21), returned in the response, and
NEVER persisted in `prod.ingreso`. Cupo is always queried through
`prod.mv_ocupacion_diaria` (DEC-SUC-11, F1.5). Regex placa uses exact
patterns (DEC-SUC-22, no O↔0 / I↔1 tolerance — that lives in
`buscarIngresoTolerante` F1.7). Defense in depth (D-HU-F1.6-7):
4 layers (regex server-side + KD-FORZADO chain + alerta INSERT same-TX +
AST walk ordering gate) so no single failure can bypass the whole.

## ADDED Requirements

### REQ-OPS-034 — V1: `cupo_no_configurado` returns 422 with `forzado_permitido: true`

**Given** branch `X` has `prod.tipos_vehiculo(Auto)` vigente
(`vigente_hasta IS NULL AND estado='activo'`) but NO row in
`prod.cantidad_vehiculos_sucursal(X, Auto)` (admin has not configured
capacity) and a JWT request reaches `POST /api/v1/operacion/ingresos`
with valid KD-3 tenant context resolved for `X`
**When** the dedicated handler `create_ingreso` invokes
`repo/ocupacion.py::validar_cupo_disponible(session, *, uuid_sucursal=X,
uuid_tipo_vehiculo=T_auto, forzado=false)` after V5 regex has derived
`T_auto` from the placa
**Then** the helper MUST return a result indicating
`cupo_no_configurado=true` (no `cantidad_vehiculos_sucursal` row for
`(X, T_auto)`)
**And** the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"cupo_no_configurado", "forzado_permitido": True})`
**And** no INSERT into `prod.ingreso` MUST occur
**And** the response MUST include the header `Cache-Control: no-store`
(consistent with F1.3 / F1.5 / F1.8 R8).
**RFC 2119**: MUST (422 shape, `forzado_permitido: true` literal,
no INSERT, header).

#### Scenario: operador posts valid placa on unconfigured branch without forzado returns 422

**Given** an `operador-` JWT with `ctx.sucursal_uuid = X`, branch X has
`tipos_vehiculo(Auto)` vigente and 0 `cantidad_vehiculos_sucursal` rows
**When** the operator POSTs `{"placa": "ABC123"}` (no `forzado`,
no `observaciones`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "cupo_no_configurado", "forzado_permitido": true}`
**And** `prod.ingreso` MUST have no new rows.

#### Scenario: admin posts valid placa on unconfigured branch with forzado bypass returns 201 (no alerta, V1 alone)

**Given** the same unconfigured branch state
**When** the admin POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: branch sin cupo configurado por admin nuevo]"}`
**Then** the response MUST be `201 Created` with the happy-path body
**And** `prod.alerta` MUST NOT receive a new `capacidad_agotada_forzado`
row (R2 mitigation: alerta only when V2 was bypassed, not V1 — V1 bypass
is "cupo missing", not "cupo full").

### REQ-OPS-035 — V2: `motivo_forzado_requerido` returns 422 with `cupo_maximo` / `activos`; forzado bypass INSERTs + emits alerta

**Given** branch `X` has `prod.cantidad_vehiculos_sucursal(X, Auto)` with
`cantidad = 50` and `prod.mv_ocupacion_diaria` (refreshed within the
last `2 × refresh_interval_s = 20s`, F1.5) reports `activos = 50` for
`(X, Auto)` (cupo agotado) and a JWT request reaches
`POST /api/v1/operacion/ingresos` with KD-3 chain resolved for `X`
**When** the handler invokes
`repo/ocupacion.py::validar_cupo_disponible(session, *, uuid_sucursal=X,
uuid_tipo_vehiculo=T_auto, forzado=false)`
**Then** the helper MUST return `cupo_no_configurado=false,
cupo_agotado=true, cupo_maximo=50, activos=50`
**And** the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"motivo_forzado_requerido", "cupo_maximo": 50, "activos": 50})`
**And** no INSERT into `prod.ingreso` MUST occur
**And** no `prod.alerta` row MUST be inserted (R2 — V2 was not bypassed).
**RFC 2119**: MUST (422 shape with literal keys, `cupo_agotado` detection,
no INSERT, no alerta on rejection).

#### Scenario: cupo agotado sin forzado returns 422 with cupo_maximo + activos

**Given** the cupo-agotado state above
**When** the operator POSTs `{"placa": "ABC123"}` (no `forzado`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "motivo_forzado_requerido", "cupo_maximo": 50, "activos": 50}`
**And** `prod.ingreso` MUST have no new rows.

#### Scenario: cupo agotado con forzado válido returns 201 and emits `capacidad_agotada_forzado` alerta same TX

**Given** the cupo-agotado state above
**When** the operator POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: cliente con cita medica urgente 2026-09-14]"}`
**Then** the handler MUST pass V2 (`cupo_result.cupo_agotado=true AND
forzado=true` ⇒ bypass, `bypass_reason="cupo_agotado"`) and proceed to
the INSERT path
**And** the handler MUST INSERT a row into `prod.ingreso` (`[L-E]`)
**And** the handler MUST INSERT a row into `prod.alerta` with
`tipo_alerta='capacidad_agotada_forzado'`, `estado='abierta'`,
`datos_nuevos` carrying the motivo string (jsonb)
**And** both INSERTs MUST commit in the SAME `await session.commit()`
call (R5 — no huérfanas)
**And** the response MUST be `201 Created` with `IngresoReadForzado`
**And** `Cache-Control: no-store` MUST be present.

### REQ-OPS-036 — V3: `tarifa_vigente_no_encontrada` returns 422 unless `forzado=true` (bi-temporal canónico from F1.4)

**Given** no row in `prod.tarifas_sucursal(X, T_auto)` satisfies the
bi-temporal canónico predicate
`vigente_desde <= NOW() AND (vigente_hasta IS NULL OR vigente_hasta >
NOW()) AND estado='activo'` (F1.4 `bitemporal_vigente_predicate`,
`repo/tarifas_vigencia.py` constant) at `datetime.now(UTC)`
**When** the handler invokes
`repo/tarifas_vigencia.py::validar_tarifa_vigente(session, *,
uuid_sucursal=X, uuid_tipo_vehiculo=T_auto, at=now(UTC),
forzado=bypass_reason)`
**Then** the helper MUST return `vigente=false`
**And** the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"tarifa_vigente_no_encontrada"})`
**And** no INSERT into `prod.ingreso` MUST occur.
**RFC 2119**: MUST (bi-temporal predicate reuse from F1.4, 422 shape,
no INSERT).

#### Scenario: tarifa no vigente sin forzado returns 422

**Given** `prod.tarifas_sucursal(X, Auto)` has only one row with
`vigente_hasta = '2025-01-01'` (already expired) and the request has
`forzado=false`
**When** the operator POSTs `{"placa": "ABC123"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "tarifa_vigente_no_encontrada"}`.

#### Scenario: tarifa no vigente con forzado válido bypasses V3

**Given** the same expired-tarifa state
**When** the operator POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: tarifa en renegociacion con operador X]"}`
**Then** the handler MUST pass V3 (forzado bypass) and proceed; no alerta
is emitted for V3 bypass (R2 — alerta only for V2 bypass).

### REQ-OPS-037 — V4: `tipo_vehiculo_invalido` returns 422; no bypass (catalog bug, not operational)

**Given** the `uuid_tipo_vehiculo` derived by V5 regex resolution maps
to either (a) no row in `prod.tipos_vehiculo` with that UUID, or (b) a
row with `vigente_hasta IS NOT NULL` (tipo dado de baja) or
`estado='inactivo'`
**When** the handler invokes
`repo/ingreso.py::validar_tipo_vehiculo_vigente(session, *,
uuid_tipo_vehiculo=T)`
**Then** the helper MUST return `False`
**And** the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"tipo_vehiculo_invalido"})`
**And** the handler MUST NOT honor `forzado=true` for V4 — V4 is a
catalog integrity defect (R-KD-V3): the operator cannot force a catalog
fix by stamping `forzado`
**And** no INSERT into `prod.ingreso` MUST occur.
**RFC 2119**: MUST (422 shape, `False` detection on missing OR
`vigente_hasta IS NOT NULL` OR `estado='inactivo'`, no bypass on
`forzado=true`).

#### Scenario: catalog missing the regex-derived tipo returns 422

**Given** `prod.tipos_vehiculo` has NO row with `tipo='Auto'` even
though `FORMATO_AUTO` regex matches the placa `ABC123`
**When** the handler invokes `validar_tipo_vehiculo_vigente(...)`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "tipo_vehiculo_invalido"}`
**And** the handler MUST NOT proceed even with `forzado=true`.

#### Scenario: tipo dado de baja (`vigente_hasta IS NOT NULL`) returns 422

**Given** `prod.tipos_vehiculo` has `tipo='Auto'` with
`vigente_hasta = '2026-01-01'`
**When** the operator POSTs `{"placa": "ABC123"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "tipo_vehiculo_invalido"}`.

### REQ-OPS-038 — V5: regex placa Colombia server-side + `placa_formato_invalido` 422 + `uuid_tipo_vehiculo` derivado y sobreescrito (BR2 CU-01)

**Given** the request body contains `placa` as a string (after V5
sequence begins; this is V5's input)
**When** the handler invokes
`repo/placa.py::detectar_tipo_vehiculo(placa)` with the regex constants
`FORMATO_AUTO = r"^[A-Z]{3}[0-9]{3}$"` (Auto) and
`FORMATO_MOTO = r"^[A-Z]{3}[0-9]{2}[A-Z]$"` (Moto), lazy lookup against
`prod.tipos_vehiculo(tipo)` vigente
**Then** if the regex matches `FORMATO_AUTO`, the helper MUST return the
UUID of `tipos_vehiculo` where `tipo='Auto'` AND
`vigente_hasta IS NULL AND estado='activo'`
**And** if the regex matches `FORMATO_MOTO`, the helper MUST return the
UUID of `tipos_vehiculo` where `tipo='Moto'` AND vigente
**And** if neither regex matches, the helper MUST return `None`
**And** if the helper returns `None`, the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"placa_formato_invalido", "formatos_aceptados": ["ABC123", "ABC12D"]})`
**And** the handler MUST overwrite the client-supplied
`uuid_tipo_vehiculo` with the regex-derived UUID before passing to V4
(BR2 CU-01, D-HU-F1.6-6 — defense in depth against stale client).
**RFC 2119**: MUST (regex constants at module level, lazy UUID lookup,
422 shape with literal `formatos_aceptados`, server-side overwrite);
SHALL (the regex constants live in `repo/placa.py` as module-level
constants so a future HU can swap them in one place).

#### Scenario: placa Auto `ABC123` deriva `tipo='Auto'` UUID y sobreescribe cliente

**Given** a valid JWT, `tipos_vehiculo(Auto)` vigente, and the request
carries `{"placa": "ABC123", "uuid_tipo_vehiculo":
"<uuid_moto_incorrecto>"}` (client bug)
**When** the operator POSTs the payload
**Then** the handler MUST use the `Auto` UUID (regex-derived) and
overwrite the Moto UUID before V4 — the operator sees 201, not 422.

#### Scenario: placa `abc123` (lowercase) returns 422 `placa_formato_invalido`

**Given** the lowercase string does not match `FORMATO_AUTO`
**When** the operator POSTs `{"placa": "abc123"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "placa_formato_invalido", "formatos_aceptados":
["ABC123", "ABC12D"]}`.

#### Scenario: placa `AB12C` (4 chars / mixed) returns 422

**Given** neither regex matches `AB12C`
**When** the operator POSTs `{"placa": "AB12C"}`
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "placa_formato_invalido", "formatos_aceptados":
["ABC123", "ABC12D"]}`.

### REQ-OPS-039 — V6: `subscripcion_inactiva_o_vencida` returns 422 unless `forzado=true` (walk-in auditado)

**Given** the request body contains
`uuid_subscripcion_cliente = S` (non-None)
**When** the handler invokes
`repo/subscripcion_activa.py::validar_subscripcion_vigente(session, *,
uuid_subscripcion_cliente=S, forzado=bypass_reason)` which checks
`vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >=
NOW()` against `prod.subscripciones_cliente`
**Then** if all three predicates hold, the helper MUST return
`vigente=true`
**And** if any predicate fails, the helper MUST return `vigente=false`
**And** when `vigente=false` AND `forzado=false`, the handler MUST raise
`HTTPException(status_code=422, detail={"error":
"subscripcion_inactiva_o_vencia"})`
**And** when `vigente=false` AND `forzado=true`, the handler MUST accept
the request as a walk-in auditado (D-HU-F1.6-2 + KD-V3 — vencida is
operational, not catalog) and proceed; no alerta is emitted for V6
bypass (R2).
**RFC 2119**: MUST (three predicates AND-ed, 422 shape, no alerta on
V6 bypass).

#### Scenario: subscripcion vigente procede sin forzado

**Given** `prod.subscripciones_cliente(S)` has
`vigente_hasta IS NULL`, `estado='activo'`,
`fecha_vencimiento = '2026-12-31'` (future)
**When** the operator POSTs `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S"}` (no `forzado`)
**Then** the handler MUST pass V6 and proceed to V8 / INSERT.

#### Scenario: subscripcion vencida sin forzado returns 422

**Given** `prod.subscripciones_cliente(S)` has
`fecha_vencimiento = '2026-01-01'` (past)
**When** the operator POSTs `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S"}` (no `forzado`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "subscripcion_inactiva_o_vencida"}`.

#### Scenario: subscripcion inactiva (`estado='inactivo'`) sin forzado returns 422

**Given** `prod.subscripciones_cliente(S)` has `estado='inactivo'`
**When** the operator POSTs `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S"}` (no `forzado`)
**Then** the response MUST be `422 Unprocessable Entity` with body
`{"error": "subscripcion_inactiva_o_vencida"}`.

#### Scenario: subscripcion vencida con forzado válido walks-in

**Given** the past-vencimiento state above
**When** the operator POSTs `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S", "forzado": true,
"observaciones": "[FORZADO: cliente pago en efectivo tras vencer 2026-01-15]"}`
**Then** the handler MUST pass V6 (walk-in auditado) and proceed to V8 /
INSERT — the resulting ingreso is `MENSUALIDAD` (V9 derivation,
REQ-OPS-041) for ops reconciliation in F7.

### REQ-OPS-040 — V8: `ingreso_activo_existente` returns 409 with `uuid_ingreso_existente`; `EXISTS` directo a tablas (no MV, no lock)

**Given** the request body has reached V8 (all prior validations passed)
**When** the handler invokes
`repo/ingreso.py::existe_ingreso_activo(session, *, uuid_sucursal=X,
placa=P)` which executes `EXISTS (SELECT 1 FROM prod.ingreso i WHERE
i.uuid_sucursal=X AND i.placa=P AND NOT EXISTS (SELECT 1 FROM
prod.salidas s WHERE s.uuid_ingreso=i.uuid AND
s.uuid_sucursal=i.uuid_sucursal) AND NOT EXISTS (SELECT 1 FROM
prod.anulaciones a WHERE a.uuid_ingreso=i.uuid AND a.estado='ejecutada'
AND a.tipo_anulable IN ('ingreso','salida')))`
**Then** if the predicate returns a row, the helper MUST return the
`uuid` of the existing active ingreso
**And** the handler MUST raise
`HTTPException(status_code=409, detail={"error":
"ingreso_activo_existente", "uuid_ingreso_existente": "<uuid>"})`
**And** the handler MUST NOT acquire any `SELECT … FOR UPDATE/SHARE`
lock — KD-V4 eventual consistency via `mv_ocupacion_diaria` is
acceptable for V2 (R8); V8 goes directly to the authoritative tables
(< 50ms p99 expected; EXPLAIN ANALYZE confirmed in design.md).
**RFC 2119**: MUST (predicate shape with two `NOT EXISTS` clauses, 409
with literal `uuid_ingreso_existente` key, no pessimistic lock).

#### Scenario: placa activa sin salida ni anulación returns 409

**Given** `prod.ingreso` already contains `(uuid_sucursal=X,
placa=ABC123)` with no row in `prod.salidas` and no row in
`prod.anulaciones` with `estado='ejecutada'`
**When** the operator POSTs `{"placa": "ABC123"}` (all prior V
validations pass)
**Then** the response MUST be `409 Conflict` with body
`{"error": "ingreso_activo_existente", "uuid_ingreso_existente":
"<existing_uuid>"}`
**And** `prod.ingreso` MUST have no new rows.

#### Scenario: placa con salida previa no anulada permite nuevo ingreso

**Given** the existing `(X, ABC123)` ingreso has a non-anulada row in
`prod.salidas` (the previous ciclo closed)
**When** the operator POSTs `{"placa": "ABC123"}`
**Then** `existe_ingreso_activo` MUST return `None` (the previous activo
was eliminated by the salida) and the handler MUST proceed to INSERT a
new `prod.ingreso` row.

#### Scenario: placa con anulación ejecutada permite nuevo ingreso

**Given** the existing `(X, ABC123)` ingreso has a row in
`prod.anulaciones` with `estado='ejecutada' AND
tipo_anulable='ingreso'`
**When** the operator POSTs `{"placa": "ABC123"}`
**Then** `existe_ingreso_activo` MUST return `None` and the handler
MUST proceed to INSERT.

### REQ-OPS-041 — V9 + KD-FORZADO-01: `tipo_entrada` derivado server-side (nunca persistido) + bypass contract + alerta `capacidad_agotada_forzado`

This requirement bundles three related contracts that share the same
INVOCATION path through the handler:

**(A) V9 — `tipo_entrada` derivación server-side (DEC-SUC-21)**:
**Given** the INSERT path has reached the response-build step (all V
validations passed)
**When** the handler derives `tipo_entrada`
**Then** the handler MUST set `tipo_entrada = "MENSUALIDAD"` if and only
if `payload.uuid_subscripcion_cliente is not None` (the `forzado` flag
is irrelevant — a walk-in with `forzado=true` still resolves to
`MENSUALIDAD` if a `uuid_subscripcion_cliente` was provided), else
`"ROTACION"`
**And** the handler MUST include `tipo_entrada` in the
`IngresoReadForzado` response body
**And** the handler MUST NOT persist `tipo_entrada` in any column of
`prod.ingreso` (DEC-SUC-21 — derived value, not a column).

**(B) KD-FORZADO-01 — bypass contract (A-04)**:
**Given** the request body carries `observaciones` (possibly None) and
`forzado` (bool)
**When** the handler invokes
`repo/ingreso.py::validar_kd_forzado(observaciones, forzado)` (the
prefix constant `FORZADO_PREFIX = "[FORZADO: "` and
`FORZADO_MIN_MOTIVO_CHARS = 10` live at module level)
**Then** the helper MUST enforce exactly three discriminators:

1. If `forzado=false` AND `observaciones` starts with `FORZADO_PREFIX`,
   the helper MUST raise `HTTPException(status_code=422, detail={"error":
   "forzado_contradiccion"})` — D-HU-F1.6-5 defense in depth (the
   prefix is the source of truth, not the bool flag).
2. If `forzado=true` AND `observaciones` is None OR does not start with
   `FORZADO_PREFIX`, the helper MUST raise `HTTPException(status_code=422,
   detail={"error": "motivo_forzado_requerido"})`.
3. If `forzado=true` AND `observaciones` starts with `FORZADO_PREFIX` AND
   the motivo (substring after `FORZADO_PREFIX`, `rstrip("]")`) has
   `len(motivo.strip()) < FORZADO_MIN_MOTIVO_CHARS = 10`, the helper MUST
   raise `HTTPException(status_code=422, detail={"error":
   "motivo_forzado_insuficiente", "min_chars": 10})`.

**And** on a valid `forzado=true` + valid prefix + motivo ≥10 chars, the
helper MUST return the stripped motivo string (and the handler records
`forzado_en_creacion=true` + `motivo_forzado=<motivo>` in the response).

**(C) Alerta `capacidad_agotada_forzado` same-TX INSERT (R2 + R5)**:
**Given** the INSERT step for `prod.ingreso` is reached AND
`bypass_reason == "cupo_agotado"` (V2 was bypassed)
**When** the handler invokes `repo/event.record_event` for the `[L-E]`
insert
**Then** the handler MUST immediately afterwards (in the same
transaction) invoke
`repo/alerta.py::insertar_alerta_forzado(session, *, uuid_sucursal=X,
uuid_ingreso=new_row.uuid, actor_uuid=ctx.actor_uuid, motivo=<motivo>)`
which INSERTs into `prod.alerta` with
`tipo_alerta='capacidad_agotada_forzado'`, `estado='abierta'`, and the
motivo in `datos_nuevos` (jsonb)
**And** both INSERTs MUST commit in ONE `await session.commit()` call —
no `INSERT` for alerta without a corresponding `INSERT` for ingreso
(no huérfanas, R5 mitigation)
**And** if `bypass_reason != "cupo_agotado"` (for example, V1, V3, or V6
bypassed), the handler MUST NOT INSERT a `capacidad_agotada_forzado`
alerta — R2 mitigation (alerta only on V2 bypass, not other bypasses).
**RFC 2119**: MUST (V9 derivation rule, prefix constants, three
discriminators with literal key names, alerta only on V2 bypass, single
commit for ingreso + alerta).

#### Scenario: V9 happy path MENSUALIDAD con subscripcion vigente

**Given** the request carries `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S"}` and V6 passed
**When** the handler builds the response
**Then** the response MUST be `201 Created` with
`IngresoReadForzado` carrying
`{"tipo_entrada": "MENSUALIDAD", "forzado_en_creacion": false,
"motivo_forzado": null, …}`
**And** a `SELECT tipo_entrada FROM prod.ingreso WHERE uuid=<new>`
MUST error with "column does not exist" (DEC-SUC-21 — never persisted).

#### Scenario: V9 happy path ROTACION sin subscripcion

**Given** the request carries `{"placa": "ABC123"}` (no
`uuid_subscripcion_cliente`)
**When** the handler builds the response
**Then** the response MUST be `201 Created` with
`{"tipo_entrada": "ROTACION", "forzado_en_creacion": false,
"motivo_forzado": null, …}`.

#### Scenario: KD-FORZADO-01 `forzado_contradiccion` when forzado=false with prefix

**Given** the request carries `{"placa": "ABC123", "forzado": false,
"observaciones": "[FORZADO: prueba cliente]"}`
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"forzado_contradiccion"})` (the bool flag contradicts the prefix).

#### Scenario: KD-FORZADO-01 `motivo_forzado_requerido` when forzado=true without prefix

**Given** the request carries `{"placa": "ABC123", "forzado": true,
"observaciones": "cliente sin placa"}` (no prefix)
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"motivo_forzado_requerido"})`.

#### Scenario: KD-FORZADO-01 `motivo_forzado_insuficiente` when motivo <10 chars

**Given** the request carries `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: a b]"}` (motivo "a b" = 3 chars after
prefix + rstrip)
**When** the handler invokes `validar_kd_forzado(observaciones, forzado)`
**Then** the helper MUST raise `HTTPException(422, {"error":
"motivo_forzado_insuficiente", "min_chars": 10})`.

#### Scenario: KD-FORZADO-01 valid bypass on cupo agotado emits alerta same TX as ingreso

**Given** cupo agotado for `(X, Auto)` (REQ-OPS-035 scenario)
**When** the operator POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: cliente con cita medica urgente 2026-09-14]"}`
**Then** `validar_kd_forzado` returns the stripped motivo
**And** V2 is bypassed with `bypass_reason="cupo_agotado"`
**And** the `prod.ingreso` INSERT and the `prod.alerta` INSERT both commit
in ONE `await session.commit()` (verified by integration test
`test_ingreso_create_db.py::T1`)
**And** the response carries `{"tipo_entrada": "ROTACION",
"forzado_en_creacion": true, "motivo_forzado": "cliente con cita
medica urgente 2026-09-14", …}`.

#### Scenario: KD-FORZADO-01 valid bypass on V1 (cupo no configurado) does NOT emit alerta

**Given** branch X has no `cantidad_vehiculos_sucursal` for Auto
(REQ-OPS-034 scenario)
**When** the operator POSTs `{"placa": "ABC123", "forzado": true,
"observaciones": "[FORZADO: branch sin cupo configurado por admin nuevo]"}`
**Then** the handler MUST proceed (V1 bypassed) and commit the ingreso
INSERT
**And** the handler MUST NOT call `insertar_alerta_forzado` — R2
mitigation (alerta only on V2 bypass)
**And** `prod.alerta` MUST have no new rows for this UUID.

#### Scenario: V9 `tipo_entrada=MENSUALIDAD` is derived even when forzado=true

**Given** the request carries `{"placa": "ABC123",
"uuid_subscripcion_cliente": "S", "forzado": true,
"observaciones": "[FORZADO: cliente pago en efectivo tras vencer 2026-01-15]"}`
(REQ-OPS-039 walk-in auditado scenario)
**When** the handler builds the response
**Then** the response MUST carry `{"tipo_entrada": "MENSUALIDAD",
"forzado_en_creacion": true, "motivo_forzado": "cliente pago en
efectivo tras vencer 2026-01-15", …}` — `tipo_entrada` is keyed on
`uuid_subscripcion_cliente`, NOT on `forzado` (V9 invariant).

## Modified Capabilities

The archive phase merges the following 10 F1.6 deltas into
`openspec/specs/operations/spec.md`:

- **V1 — `cupo_no_configurado` con `forzado_permitido: true`** —
  handler `create_ingreso` aplica V1 antes de V2; sin INSERT; bypass
  con `forzado=true` válido NO emite alerta (R2).
  (REQ-OPS-034)
- **V2 — `motivo_forzado_requerido` con `cupo_maximo`/`activos` + alerta
  `capacidad_agotada_forzado` same-TX** — `repo/ocupacion.py::validar_cupo_disponible`
  reusando `get_ocupacion_puros_activos` (post-F1.5, KD-V4 eventual
  consistency ≤10s). Bypass emite alerta; rechazo no emite.
  (REQ-OPS-035)
- **V3 — `tarifa_vigente_no_encontrada` 422 + bi-temporal canónico F1.4**
  — `repo/tarifas_vigencia.py::validar_tarifa_vigente` reusando
  `bitemporal_vigente_predicate` (`vigente_desde <= NOW() AND
  (vigente_hasta IS NULL OR vigente_hasta > NOW()) AND estado='activo'`).
  Bypass con `forzado=true` válido NO emite alerta (R2).
  (REQ-OPS-036)
- **V4 — `tipo_vehiculo_invalido` 422 sin bypass** — defensa contra
  catalog defect (UUID inexistente o `vigente_hasta IS NOT NULL` o
  `estado='inactivo'`). `forzado=true` NO honra V4 — KD-V3.
  (REQ-OPS-037)
- **V5 — Regex placa Colombia server-side + `placa_formato_invalido` +
  `uuid_tipo_vehiculo` derivado y sobreescrito (BR2 CU-01)** —
  `repo/placa.py` con `FORMATO_AUTO = r"^[A-Z]{3}[0-9]{3}$"` y
  `FORMATO_MOTO = r"^[A-Z]{3}[0-9]{2}[A-Z]$"` como constantes de
  módulo; `detectar_tipo_vehiculo(placa)` con lazy lookup contra
  `prod.tipos_vehiculo`. Server sobreescribe cliente (D-HU-F1.6-6).
  (REQ-OPS-038)
- **V6 — `subscripcion_inactiva_o_vencida` 422 + walk-in auditado** —
  `repo/subscripcion_activa.py::validar_subscripcion_vigente` con
  `vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >=
  NOW()`. Bypass con `forzado=true` válido NO emite alerta (R2).
  (REQ-OPS-039)
- **V8 — `ingreso_activo_existente` 409 con `uuid_ingreso_existente`** —
  `repo/ingreso.py::existe_ingreso_activo` con `EXISTS` directo a
  `prod.ingreso` + `NOT EXISTS` salidas + `NOT EXISTS` anulaciones
  ejecutadas; SIN lock pesimista (KD-V4). Authoritative, va a tablas
  no a la MV.
  (REQ-OPS-040)
- **V9 — `tipo_entrada` derivación server-side, nunca persistido** —
  `MENSUALIDAD` iff `uuid_subscripcion_cliente is not None`, sino
  `ROTACION`. Devuelto en `IngresoReadForzado`; DEC-SUC-21 veda columna
  en `prod.ingreso`. Keyed on subscripcion, NOT on `forzado`.
  (REQ-OPS-041.A)
- **KD-FORZADO-01 — bypass contract con prefijo `[FORZADO: <motivo
  ≥10 chars>]`** — único bypass operacional a V1/V2/V3/V6. Tres
  discriminadores tipados (`forzado_contradiccion`,
  `motivo_forzado_requerido`, `motivo_forzado_insuficiente`). Constantes
  `FORZADO_PREFIX = "[FORZADO: "` y `FORZADO_MIN_MOTIVO_CHARS = 10` a
  nivel de módulo. Defense in depth: el prefijo es la fuente de verdad,
  NO el flag bool.
  (REQ-OPS-041.B)
- **KD-FORZADO-01.alerta — `capacidad_agotada_forzado` INSERT same-TX
  con ingreso, solo cuando V2 fue bypassed** — `repo/alerta.py::insertar_alerta_forzado`
  con `tipo_alerta='capacidad_agotada_forzado'`, `estado='abierta'`,
  motivo en `datos_nuevos` (jsonb). Un solo `await session.commit()` —
  no huérfanas (R5). R2: alerta SOLO si `bypass_reason == "cupo_agotado"`.
  (REQ-OPS-041.C)

### Files affected (F1.6 delta)

- `backend/packages/parkos_core/src/parkos_core/repo/placa.py` (NUEVO,
  ~30 LOC) — regex constants + `detectar_tipo_vehiculo`.
- `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py`
  (NUEVO, ~180 LOC) — 8 funciones de validación V1..V9 (V1+V2 re-export
  via `repo/ocupacion.py`; V3 re-export via `repo/tarifas_vigencia.py`;
  V4 + V6 + V8 + V9 propias) + `validar_kd_forzado` +
  `crear_ingreso_evento` thin wrapper de `record_event` +
  `insertar_alerta_forzado` re-export.
- `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py`
  (NUEVO, ~50 LOC) — extrae `resolve_active_subscription_for_exit`
  (post-PR5) + check `fecha_vencimiento >= NOW()`; usado por V6 y
  reutilizado por F7.
- `backend/packages/parkos_core/src/parkos_core/repo/alerta.py` (NUEVO,
  ~60 LOC) — `insertar_alerta_forzado` puro.
- `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py`
  (MODIFICAR, +40 LOC) — `validar_cupo_disponible` reusando
  `get_ocupacion_puros_activos`.
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py`
  (MODIFICAR, +30 LOC) — `validar_tarifa_vigente` reusando
  `bitemporal_vigente_predicate`.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py`
  (MODIFICAR, replace `create_ingreso` líneas 92-114 → ~232 LOC) —
  handler dedicado con las 9 validaciones + KD-FORZADO-01 + derivación
  `tipo_entrada`. Mantiene KD-3 chain (`_ingreso_issuer_dep`,
  `get_tenant_ctx`), `response_model=IngresoReadForzado`,
  `status_code=201`, `Cache-Control: no-store`. `api/v1/__init__.py` y
  `router_factory.py` intactos.
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py`
  (MODIFICAR, +80 LOC) — `IngresoCreateForzado` (entrada con `forzado`),
  `IngresoReadForzado` (salida con `tipo_entrada`,
  `forzado_en_creacion`, `motivo_forzado`), 7 clases de error tipadas
  (`CupoNoConfiguradoError`, `MotivoForzadoRequeridoError`,
  `TarifaVigenteNoEncontradaError`, `PlacaFormatoInvalidoError`,
  `SubscripcionInactivaOVencidaError`, `IngresoActivoExistenteError`,
  `TipoVehiculoInvalidoError`). Mantiene `IngresoCreate` / `IngresoRead`
  como alias deprecated (sin breaking change). `extra='forbid'`
  heredado de `_Base`.
- `openspec/specs/operations/spec.md` (raíz) — gana REQ-OPS-034..041
  (8 requirements nuevos) + entrada en `## Modified Capabilities`. Sin
  cambio sobre REQ-OPS-001..033.

## Out of Scope

- **Workflow de anulación** (`prod.anulaciones` workflow para revertir
  ingreso post-creación). DEC-ANUL-01 delega a Fase 7+. `ingreso` nunca
  UPDATE post-creación; `repo/ingreso.py::crear_ingreso_evento` thin
  wrapper de `record_event`, sin UPDATE path. (KD-V5)
- **`correlacion_id`** en el payload. DEC-IDEM-01 delega idempotencia
  al header `Idempotency-Key` (PR2 middleware). (KD-V6)
- **Regex configurable** (catálogo, settings, JSON, BD). A-03 / KD-V2
  hardcoded para MVP; configurable en HU futura con cat tabla. (R3)
- **Lock pesimista** (`SELECT … FOR UPDATE/SHARE`) sobre `prod.ingreso`
  / `prod.salidas` / `prod.anulaciones` desde el endpoint. KD-V4
  eventual consistency aceptable (RIESGO-SUC-02 del corpus).
  (D-HU-F1.6-3)
- **Versionado de UI cliente** (Fase 2 frontend — `web_sucursal` debe
  desactivar `lib/validation/placa.ts` A-03 cuando este endpoint esté en
  producción). F1.6 **NO** modifica el cliente; el cleanup del cliente
  es post-archive.
- **`CHECK constraint`** sobre `prod.ingreso.placa`. A-03 descarta
  CHECK rígida; bloquearía migración nacional futura.
- **Endpoint `GET /operacion/ingresos/{uuid}/validar`** (preview sin
  insertar). Sale del scope: el handler hace insert o 422, sin preview.
- **Alertas adicionales** (`placa_no_reconocida_forzado`,
  `subscripcion_sin_vehiculo`). Solo se inserta
  `capacidad_agotada_forzado` (R2 mitigation); otras alertas son
  operacionales y salen del scope de F1.6.
- **Permisos RBAC diferenciados para `forzado`** (e.g. "solo admin-").
  KD-V8 acepta ambos `operador-` y `admin-` para MVP; check dedicado en
  HU futura.
- **Migración nacional de formatos de placa** (e.g. Mercosur 2027).
  KD-V2 hardcoded para MVP; sale del scope.
- **Métricas / observabilidad del handler** (contador de `forzado=true`
  por día, latencia p99 de `create_ingreso`). Sale del scope; alineado
  con HU-F1.X de observabilidad (futuro).